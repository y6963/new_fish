"""
OASIS / CAMEL 的 messages 结构规范化补丁（模拟子进程专用）。

背景
----
OASIS 的 `SocialAgent.perform_interview()` 和 `perform_test()` 会手工拼装
messages：在记忆上下文（第 0 条本来就是 system）之前**再插入一条 system**，
最终产生两条连续的 system：

    ['system', 'system', 'user', 'assistant', 'user']

开源模型（Qwen / Llama / ChatML 系）的 chat template 普遍强制
「system 只能出现一次，且必须位于开头」，服务端会在套用模板时直接拒绝：

    400 BadRequestError - System message must be at the beginning.

这个校验发生在**渲染 chat template 阶段**，由模型自带的模板规则决定，
不是推理框架（vLLM 等）的 bug，因此换用同一类开源模型通常仍然失败。

方案
----
在 CAMEL 的 `ChatAgent._aget_model_response()` 上做一层包装，发出请求前把
messages 规范化成「单条 system 位于开头」的通用形式：

1. 合并所有 system 消息为一条，置于 index 0；
2. 若服务端仍以 system 角色相关错误拒绝，降级为「把 system 折叠进第一条
   user 消息」再重试一次（兼容不支持 system role 的老模板）。

对本来就合规的 messages，规范化是 **no-op**，不会改变模拟阶段的既有行为。

用法（模拟脚本内，import oasis 之后调用一次即可）：

    import oasis_message_patch
    oasis_message_patch.apply()

可用环境变量 `OASIS_MESSAGE_NORMALIZE=0` 关闭整个补丁（排障用）。
"""

import os
import sys

_ENABLED = os.environ.get("OASIS_MESSAGE_NORMALIZE", "1") not in ("0", "false", "False")
_APPLIED_FLAG = "_mirofish_message_normalized"
_ORIGINAL = {}


# --------------------------------------------------------------------------
# 纯函数部分：不依赖 camel / oasis，可独立单测
# --------------------------------------------------------------------------

def _system_text(message):
    content = message.get("content")
    if isinstance(content, list):  # 多模态 content
        parts = [p.get("text", "") for p in content if isinstance(p, dict)]
        content = "\n".join(p for p in parts if p)
    return (content or "").strip() if isinstance(content, str) else ""


def merge_system_texts(texts):
    """把多条 system 内容合并成一条。

    关键约定：**以第一条为准**。OASIS 插入的那条是第一位的截断版
    （去掉了 `# RESPONSE FORMAT` 之后的格式说明），记忆里的完整版排在其后。
    所以当后者是前者的超集时，多出来的部分本来就是原逻辑要丢弃的内容，
    直接丢弃而不是拼接。
    """
    merged = ""
    for text in texts:
        if not text:
            continue
        if not merged:
            merged = text
        elif text in merged:
            continue          # 后者已被前者包含
        elif merged in text:
            continue          # 前者是后者的前缀，保留前者（截断版）
        else:
            merged = merged + "\n\n" + text
    return merged


def normalize_messages(messages):
    """规范化成「至多一条 system，且位于 index 0」。

    对已合规的输入原样返回（逐项仍是原对象引用），不改变既有行为。
    """
    if not isinstance(messages, (list, tuple)):
        return messages

    system_texts = []
    rest = []
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "system":
            text = _system_text(message)
            if text:
                system_texts.append(text)
            # 空 system 直接丢弃
        else:
            rest.append(message)

    if not system_texts:
        # 没有 system，或 system 已在首位且唯一 —— 原样返回
        if len(messages) == len(rest):
            return list(messages)
        return rest

    merged = merge_system_texts(system_texts)

    # 已经是「单条 system 在开头」→ no-op
    if (
        len(messages) == len(rest) + 1
        and isinstance(messages[0], dict)
        and messages[0].get("role") == "system"
        and _system_text(messages[0]) == merged
    ):
        return list(messages)

    return [{"role": "system", "content": merged}] + rest


def fold_system_into_user(messages):
    """降级方案：把开头的 system 折叠进第一条 user 消息。

    用于服务端连单条 system 都拒绝的场景（不支持 system role 的老模板）。
    没有 system 或没有 user 消息时返回 None，表示无法降级。
    """
    if not messages or not isinstance(messages[0], dict):
        return None
    if messages[0].get("role") != "system":
        return None

    system_text = _system_text(messages[0])
    if not system_text:
        return None

    for index in range(1, len(messages)):
        message = messages[index]
        if isinstance(message, dict) and message.get("role") == "user":
            folded = dict(message)
            existing = folded.get("content") or ""
            folded["content"] = (
                f"{system_text}\n\n{existing}" if existing else system_text
            )
            return list(messages[1:index]) + [folded] + list(messages[index + 1:])

    return None


def is_system_role_error(exc):
    """判断是否为 system 消息结构相关的服务端拒绝。"""
    text = f"{type(exc).__name__}: {exc}".lower()
    markers = (
        "system message",
        "system role",
        "at the beginning",
        "must be the first message",
    )
    return any(marker in text for marker in markers)


# --------------------------------------------------------------------------
# 打补丁部分：延迟导入 camel，模块本身可无依赖 import
# --------------------------------------------------------------------------

def _log(message):
    sys.stderr.write(f"[oasis_message_patch] {message}\n")


def build_wrapper(original):
    """把原 `_aget_model_response` 包一层规范化逻辑（不依赖 camel，可单测）。"""

    async def normalized_aget_model_response(self, *args, **kwargs):
        if "openai_messages" in kwargs and kwargs["openai_messages"] is not None:
            kwargs["openai_messages"] = normalize_messages(kwargs["openai_messages"])
        elif args and args[0] is not None:
            args = (normalize_messages(args[0]),) + args[1:]

        try:
            return await original(self, *args, **kwargs)
        except Exception as exc:
            if not is_system_role_error(exc):
                raise

            # 服务端连单条 system 都不要 —— 折叠进第一条 user 再试一次
            current = kwargs.get("openai_messages")
            if current is None and args:
                current = args[0]
            fallback = fold_system_into_user(normalize_messages(current or []))
            if fallback is None:
                raise

            _log("服务端拒绝 system 消息，降级为折叠进首条 user 后重试")
            if "openai_messages" in kwargs:
                kwargs["openai_messages"] = fallback
                return await original(self, **kwargs)
            return await original(self, fallback, *args[1:], **kwargs)

    normalized_aget_model_response.__name__ = getattr(
        original, "__name__", "_aget_model_response"
    )
    setattr(normalized_aget_model_response, _APPLIED_FLAG, True)
    return normalized_aget_model_response


def apply(strict=False, target=None):
    """给 ChatAgent（或指定类）装上规范化包装。幂等，失败可降级。"""
    if not _ENABLED:
        _log("已通过 OASIS_MESSAGE_NORMALIZE=0 关闭")
        return False

    if target is None:
        try:
            from camel.agents.chat_agent import ChatAgent
        except Exception as exc:  # 依赖缺失时不应让模拟脚本崩溃
            if strict:
                raise
            _log(f"跳过：无法导入 camel.agents.chat_agent ({exc})")
            return False
        target = ChatAgent

    original = getattr(target, "_aget_model_response", None)
    if original is None:
        if strict:
            raise RuntimeError("_aget_model_response 不存在")
        _log("跳过：_aget_model_response 不存在（camel 版本不兼容）")
        return False

    if getattr(original, _APPLIED_FLAG, False):
        return True

    _ORIGINAL[target] = original
    setattr(target, "_aget_model_response", build_wrapper(original))
    _log("已启用（合并重复 system，必要时降级折叠）")
    return True


def revert(target=None):
    """回滚补丁，供测试使用。"""
    if target is None:
        try:
            from camel.agents.chat_agent import ChatAgent
        except Exception:
            return False
        target = ChatAgent

    original = _ORIGINAL.pop(target, None)
    if original is None:
        return False
    setattr(target, "_aget_model_response", original)
    return True
