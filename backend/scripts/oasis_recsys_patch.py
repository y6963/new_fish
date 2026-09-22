"""
OASIS 推荐模型（Twitter/twhin-bert-base）加载优化补丁（模拟子进程专用）。

背景
----
OASIS 的 twitter 平台在 `oasis/environment/env.py:81` 里**硬编码**
`recsys_type="twhin-bert"`，项目侧无法通过配置覆盖。

推荐刷新链路：
    platform.py:362  update_rec_table()
      → recsys.py:419  rec_sys_personalized_twh()
        → recsys.py:431  if twhin_model is None or twhin_tokenizer is None:
                           get_recsys_model("twhin-bert")
                           → recsys.py:68/78  AutoTokenizer/AutoModel.from_pretrained(
                                                  "Twitter/twhin-bert-base")

两个叠加的问题：

1. **每次都要发网络**：`from_pretrained` 会向 huggingface.co 做 etag 校验。
   huggingface.co 不可达时，tokenizer（tokenizer_config.json）与模型
   （config.json）各重试 5 次（10s 超时、退避 1/2/4/8/8），
   单次刷新白等约 150 秒。

2. **失败不留痕**：`get_twhin_tokenizer()` / `get_twhin_model()` 用的是
   「全局变量为 None 才加载」的懒加载写法，而**加载失败时全局变量不会被赋值**，
   于是每一次推荐刷新都把 150 秒完整地重来一遍。

关键在于：`platform.py:372-375` 对加载失败的处理是

        except Exception as e:
            twitter_log.error(e)
            return          # 跳过本次推荐表更新

也就是说——**等 150 秒后失败，和立刻失败，结果完全一样**（都只是跳过更新）。
那些等待不产生任何价值，却把后续的 batch_interview（IPC 超时 180 秒）拖过了线。

方案
----
1. `local_files_only=True`：模型的加载只查本地缓存，不再发网络请求。
   - 没有缓存 → 立刻抛错（与原来的最终结果一致，只是不再浪费 150 秒）
   - **若把模型缓存放到 HF 缓存目录，会自动加载，功能完全恢复**（向上兼容）
2. 记住"本地不可用"，后续调用直接快速失败，不再重复探测同一目录。

可选（默认关闭）
----------------
`MIROFISH_TWITTER_RECSYS=twitter`：把 twitter 平台的推荐算法从 twhin-bert
换成 TF-IDF（`rec_sys_personalized_with_trace`，纯本地、无需任何模型）。
这样推荐表会被**真正更新**，而不是被 `except → return` 跳过。
注意这会改变推荐行为，仅在明确希望如此时启用。

排查开关：`OASIS_RECSYS_PATCH=0` 整体关闭。
"""

import os
import sys

_ENABLED = os.environ.get("OASIS_RECSYS_PATCH", "1") not in ("0", "false", "False")
_MODEL_NAME = "Twitter/twhin-bert-base"
_SWITCH_TO = (os.environ.get("MIROFISH_TWITTER_RECSYS") or "").strip() or None

_ORIGINAL = {}
_LOG_PREFIX = "[oasis_recsys_patch]"


def _log(message):
    sys.stderr.write(f"{_LOG_PREFIX} {message}\n")


class LocalModelUnavailable(RuntimeError):
    """本地无可用缓存，且已确认无需重试。"""


def _load_local_only(kind):
    """只从本地缓存加载；没有缓存则立刻失败（不发网络请求）。"""
    if kind == "tokenizer":
        from transformers import AutoTokenizer

        return AutoTokenizer.from_pretrained(
            _MODEL_NAME, model_max_length=512, local_files_only=True
        )

    import torch
    from transformers import AutoModel

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return AutoModel.from_pretrained(_MODEL_NAME, local_files_only=True).to(device)


def install_fast_loader(module, func_name, global_name, kind, state=None):
    """替换 recsys 模块里的懒加载函数：本地优先 + 失败记忆。

    `state` 可外部传入，便于测试观察；省略时在模块上挂一个字典。
    """
    state = {} if state is None else state
    original = getattr(module, func_name, None)
    if original is None:
        raise AttributeError(f"{module.__name__} 没有 {func_name}")

    def fast_loader(*args, **kwargs):
        cached = getattr(module, global_name, None)
        if cached is not None:
            return cached

        if state.get(func_name):
            raise LocalModelUnavailable(
                f"{_MODEL_NAME} 本地无缓存，已跳过重复加载"
            )

        try:
            loaded = _load_local_only(kind)
        except Exception as error:
            state[func_name] = True
            _log(
                f"{func_name}: 本地无 {_MODEL_NAME} 缓存，"
                f"后续调用直接跳过（{type(error).__name__}）"
            )
            raise
        setattr(module, global_name, loaded)
        _log(f"{func_name}: 已从本地缓存加载 {_MODEL_NAME}")
        return loaded

    fast_loader.__name__ = func_name
    setattr(module, func_name, fast_loader)
    _ORIGINAL[(module, func_name)] = original
    return state


def _install_recsys_switch(replacement):
    """把 twitter 平台的 recsys_type 从 twhin-bert 换成纯本地的实现。"""
    from oasis.social_platform.platform import Platform

    original = Platform.__init__

    def patched_init(self, *args, **kwargs):
        if kwargs.get("recsys_type") == "twhin-bert":
            kwargs["recsys_type"] = replacement
        return original(self, *args, **kwargs)

    patched_init.__name__ = "__init__"
    setattr(Platform, "__init__", patched_init)
    _ORIGINAL[(Platform, "__init__")] = original
    _log(f"twitter 推荐算法已切换为 {replacement!r}（不再依赖 twhin-bert）")


def apply(strict=False, recsys_module=None, switch_recsys=None):
    """安装补丁。幂等，失败可降级（绝不因补丁把模拟脚本拖崩）。"""
    if not _ENABLED:
        _log("已通过 OASIS_RECSYS_PATCH=0 关闭")
        return False

    if recsys_module is None:
        try:
            from oasis.social_platform import recsys as recsys_module
        except Exception as error:
            if strict:
                raise
            _log(f"跳过：无法导入 oasis.social_platform.recsys ({error})")
            return False

    if getattr(recsys_module, "_mirofish_fast_loader", False):
        return True

    try:
        state = getattr(recsys_module, "_mirofish_loader_state", None)
        if state is None:
            state = {}
            setattr(recsys_module, "_mirofish_loader_state", state)
        install_fast_loader(
            recsys_module, "get_twhin_tokenizer", "twhin_tokenizer", "tokenizer", state
        )
        install_fast_loader(
            recsys_module, "get_twhin_model", "twhin_model", "model", state
        )
        setattr(recsys_module, "_mirofish_fast_loader", True)
    except Exception as error:
        if strict:
            raise
        _log(f"跳过：安装失败 ({error})")
        return False

    replacement = switch_recsys if switch_recsys is not None else _SWITCH_TO
    if replacement:
        try:
            _install_recsys_switch(replacement)
        except Exception as error:
            if strict:
                raise
            _log(f"推荐算法切换失败，保持原样 ({error})")

    _log("已启用（模型只查本地缓存，失败不再重试）")
    return True


def revert():
    """回滚补丁，供测试使用。"""
    for (module, name), original in list(_ORIGINAL.items()):
        setattr(module, name, original)
        _ORIGINAL.pop((module, name), None)
    return True
