"""
模拟子进程里 OASIS/CAMEL messages 规范化补丁的契约测试。

核心不变量：
1. 采访路径的「两条 system」必须收敛为一条，且保留 OASIS 想要的那条；
2. 对本来就合规的 messages（模拟阶段）必须是 no-op，不许改变既有行为；
3. 服务端连单条 system 都拒时，能降级为折叠进首条 user 并重试一次。
"""

import asyncio
import importlib.util
import os
import sys

import pytest

_SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")


def _load_module():
    """按文件路径加载补丁模块（它位于 scripts/，不在包内）。"""
    spec = importlib.util.spec_from_file_location(
        "oasis_message_patch", os.path.join(_SCRIPTS_DIR, "oasis_message_patch.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["oasis_message_patch"] = module
    spec.loader.exec_module(module)
    return module


patch = _load_module()


# --------------------------------------------------------------------------
# 1. 核心 bug：两条 system
# --------------------------------------------------------------------------

def test_interview_double_system_collapses_to_the_truncated_one():
    """OASIS 手工插入的 system 在前，记忆里的完整 system 在后。

    截断版是完整版的前缀，多出来的部分（# RESPONSE FORMAT 段）本就是
    原逻辑要丢弃的内容，所以必须保留截断版，而不是拼回去。
    """
    full = "你是西贝CEO。# RESPONSE FORMAT\n请按 JSON 输出。"
    truncated = full.split("# RESPONSE FORMAT")[0]

    messages = [
        {"role": "system", "content": truncated},   # OASIS 硬加的（截断版）
        {"role": "system", "content": full},        # 记忆里的完整版
        {"role": "user", "content": "发帖"},
        {"role": "assistant", "content": "好的"},
        {"role": "user", "content": "采访问题"},
    ]

    result = patch.normalize_messages(messages)

    assert [m["role"] for m in result] == ["system", "user", "assistant", "user"]
    assert result[0]["content"] == truncated
    assert "# RESPONSE FORMAT" not in result[0]["content"]


def test_system_always_ends_up_at_index_zero():
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "system", "content": "你是助手"},
        {"role": "assistant", "content": "hello"},
    ]
    result = patch.normalize_messages(messages)

    assert result[0]["role"] == "system"
    assert result[0]["content"] == "你是助手"
    assert [m["role"] for m in result[1:]] == ["user", "assistant"]


def test_independent_system_messages_are_concatenated_not_dropped():
    """互不包含的 system 不能静默丢弃，否则会丢指令。"""
    messages = [
        {"role": "system", "content": "你是记者"},
        {"role": "system", "content": "只说中文"},
        {"role": "user", "content": "提问"},
    ]
    result = patch.normalize_messages(messages)

    assert len(result) == 2
    assert "你是记者" in result[0]["content"]
    assert "只说中文" in result[0]["content"]


# --------------------------------------------------------------------------
# 2. 保护原有功能：合规输入必须是 no-op
# --------------------------------------------------------------------------

def test_single_leading_system_is_returned_unchanged():
    messages = [
        {"role": "system", "content": "你是西贝CEO"},
        {"role": "user", "content": "发帖"},
        {"role": "assistant", "content": "好的"},
    ]
    result = patch.normalize_messages(messages)

    assert result == messages          # 内容完全一致
    assert all(a is b for a, b in zip(result, messages))  # 连对象引用都不换


def test_messages_without_system_are_untouched():
    messages = [
        {"role": "user", "content": "发帖"},
        {"role": "assistant", "content": "好的"},
    ]
    assert patch.normalize_messages(messages) == messages


def test_empty_and_invalid_input_is_safe():
    assert patch.normalize_messages([]) == []
    assert patch.normalize_messages(None) is None


def test_empty_system_is_dropped():
    messages = [
        {"role": "system", "content": "   "},
        {"role": "user", "content": "提问"},
    ]
    result = patch.normalize_messages(messages)

    assert [m["role"] for m in result] == ["user"]


# --------------------------------------------------------------------------
# 3. 降级：服务端连单条 system 都拒
# --------------------------------------------------------------------------

def test_fold_system_into_first_user():
    messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "提问"},
    ]
    folded = patch.fold_system_into_user(messages)

    assert folded == [{"role": "user", "content": "你是助手\n\n提问"}]
    assert all(m["role"] != "system" for m in folded)


def test_fold_returns_none_when_impossible():
    assert patch.fold_system_into_user([{"role": "user", "content": "hi"}]) is None
    assert patch.fold_system_into_user([{"role": "system", "content": "x"}]) is None


def test_real_400_error_is_recognized():
    """日志里真实出现的那一条必须被识别。"""
    exc = Exception(
        "Error code: 400 - {'error': {'message': "
        "'System message must be at the beginning.', 'code': 400}}"
    )
    assert patch.is_system_role_error(exc) is True
    assert patch.is_system_role_error(Exception("Connection timeout")) is False


# --------------------------------------------------------------------------
# 4. 打补丁后确实生效（用真实的 ChatAgent 类做载体）
# --------------------------------------------------------------------------

class _FakeChatAgent:
    """替身载体：避免测试依赖能否 import camel（沙箱里 rpds 加载不了）。"""

    def __init__(self, responder):
        self.responder = responder

    async def _aget_model_response(self, *args, **kwargs):
        return await self.responder(self, *args, **kwargs)


def test_patch_normalizes_before_sending_and_falls_back():
    received = []

    async def responder(self, *args, **kwargs):
        messages = kwargs.get("openai_messages") or args[0]
        received.append(messages)
        if len(received) == 1:
            raise RuntimeError("400 System message must be at the beginning")
        return "ok"

    agent = _FakeChatAgent(responder)
    assert patch.apply(strict=True, target=_FakeChatAgent) is True

    sent = [
        {"role": "system", "content": "你是CEO"},
        {"role": "system", "content": "你是CEO。# RESPONSE FORMAT\nJSON"},
        {"role": "user", "content": "提问"},
    ]

    result = asyncio.run(agent._aget_model_response(openai_messages=sent))

    assert result == "ok"
    assert len(received) == 2
    # 第一次：已合并成单条 system
    assert [m["role"] for m in received[0]] == ["system", "user"]
    # 第二次：降级为折叠进 user，不再有 system
    assert all(m["role"] != "system" for m in received[1])
    assert "你是CEO" in received[1][0]["content"]

    assert patch.revert(target=_FakeChatAgent) is True


def test_apply_without_target_resolves_camel_chat_agent(monkeypatch):
    """target 省略时，应从 camel.agents.chat_agent 取 ChatAgent（真实入口路径）。"""
    import types

    class _CamelChatAgent:
        async def _aget_model_response(self, *args, **kwargs):
            return "ok"

    chat_agent_module = types.ModuleType("camel.agents.chat_agent")
    chat_agent_module.ChatAgent = _CamelChatAgent
    monkeypatch.setitem(sys.modules, "camel", types.ModuleType("camel"))
    monkeypatch.setitem(sys.modules, "camel.agents", types.ModuleType("camel.agents"))
    monkeypatch.setitem(sys.modules, "camel.agents.chat_agent", chat_agent_module)

    assert patch.apply(target=None) is True
    assert getattr(_CamelChatAgent._aget_model_response,
                   patch._APPLIED_FLAG, False) is True
    patch.revert(target=_CamelChatAgent)


def test_apply_is_safe_when_camel_is_unavailable(monkeypatch):
    """依赖缺失时必须静默降级，不能让模拟脚本启动失败。"""
    import types

    def _boom(name, *args, **kwargs):
        raise ImportError("camel 不可用")

    monkeypatch.setattr("builtins.__import__", _boom)
    assert patch.apply(target=None) is False


def test_patch_is_idempotent():
    async def responder(self, *args, **kwargs):
        return "ok"

    original = _FakeChatAgent._aget_model_response
    assert patch.apply(strict=True, target=_FakeChatAgent) is True
    first = _FakeChatAgent._aget_model_response
    assert patch.apply(strict=True, target=_FakeChatAgent) is True
    assert _FakeChatAgent._aget_model_response is first   # 没有套两层

    patch.revert(target=_FakeChatAgent)
    assert _FakeChatAgent._aget_model_response is original


def test_patch_retries_only_once_then_reraises():
    calls = []

    async def always_reject(self, *args, **kwargs):
        calls.append(kwargs.get("openai_messages") or args[0])
        raise RuntimeError("System message must be at the beginning")

    patch.apply(strict=True, target=_FakeChatAgent)
    agent = _FakeChatAgent(always_reject)

    with pytest.raises(RuntimeError, match="System message"):
        asyncio.run(
            agent._aget_model_response(
                openai_messages=[
                    {"role": "system", "content": "x"},
                    {"role": "system", "content": "x2"},
                    {"role": "user", "content": "提问"},
                ]
            )
        )

    assert len(calls) == 2          # 规范化一次 + 降级一次，不会无限重试
    patch.revert(target=_FakeChatAgent)


def test_unrelated_errors_are_not_retried():
    calls = []

    async def timeout(self, *args, **kwargs):
        calls.append(1)
        raise RuntimeError("Connection timeout")

    patch.apply(strict=True, target=_FakeChatAgent)
    agent = _FakeChatAgent(timeout)

    with pytest.raises(RuntimeError, match="timeout"):
        asyncio.run(
            agent._aget_model_response(
                openai_messages=[{"role": "system", "content": "x"},
                                 {"role": "user", "content": "hi"}]
            )
        )

    assert len(calls) == 1          # 非 system 错误不吃掉重试预算
    patch.revert(target=_FakeChatAgent)
