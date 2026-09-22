"""
OASIS 推荐模型加载优化的契约测试。

核心不变量：
1. 本地无缓存时，失败只尝试**一次**，后续调用立刻失败（不再重复等网络）；
2. 本地有缓存时正常加载，并写回 OASIS 的全局缓存变量（功能不变）；
3. 已有全局缓存时直接返回，不做任何文件/网络探测；
4. 可选的推荐算法切换只改 twhin-bert，不碰其他平台。
"""

import importlib.util
import os
import sys
import types

import pytest

_SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "oasis_recsys_patch", os.path.join(_SCRIPTS_DIR, "oasis_recsys_patch.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["oasis_recsys_patch"] = module
    spec.loader.exec_module(module)
    return module


patch = _load_module()


def _fake_recsys():
    module = types.ModuleType("fake_recsys")

    def get_twhin_tokenizer():
        return None

    def get_twhin_model(device):
        return None

    module.twhin_tokenizer = None
    module.twhin_model = None
    module.get_twhin_tokenizer = get_twhin_tokenizer
    module.get_twhin_model = get_twhin_model
    return module


def test_local_files_only_is_always_requested(monkeypatch):
    """加载必须带 local_files_only=True —— 这是不再等网络的关键。"""
    seen = {}

    class _Auto:
        @staticmethod
        def from_pretrained(name, **kwargs):
            seen["tokenizer"] = (name, kwargs)
            return "TOKENIZER"

    fake_transformers = types.ModuleType("transformers")
    fake_transformers.AutoTokenizer = _Auto
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    module = _fake_recsys()
    patch.install_fast_loader(
        module, "get_twhin_tokenizer", "twhin_tokenizer", "tokenizer"
    )

    assert module.get_twhin_tokenizer() == "TOKENIZER"
    name, kwargs = seen["tokenizer"]
    assert name == "Twitter/twhin-bert-base"
    assert kwargs.get("local_files_only") is True


def test_failed_load_is_attempted_only_once(monkeypatch):
    """网络不可达时：第一次失败后必须记住，不能每次刷新都重来。"""
    attempts = []

    def failing_load(kind):
        attempts.append(kind)
        raise OSError("找不到本地缓存")

    monkeypatch.setattr(patch, "_load_local_only", failing_load)

    module = _fake_recsys()
    patch.install_fast_loader(
        module, "get_twhin_tokenizer", "twhin_tokenizer", "tokenizer"
    )

    with pytest.raises(OSError):
        module.get_twhin_tokenizer()
    for _ in range(5):
        with pytest.raises(patch.LocalModelUnavailable):
            module.get_twhin_tokenizer()

    assert attempts == ["tokenizer"]      # 只真正尝试过一次


def test_failure_state_is_shared_between_tokenizer_and_model(monkeypatch):
    """tokenizer 与 model 共用一份状态，两个都失败后都不再重试。"""
    attempts = []

    def failing_load(kind):
        attempts.append(kind)
        raise OSError("nope")

    monkeypatch.setattr(patch, "_load_local_only", failing_load)

    module = _fake_recsys()
    state = patch.install_fast_loader(
        module, "get_twhin_tokenizer", "twhin_tokenizer", "tokenizer"
    )
    patch.install_fast_loader(module, "get_twhin_model", "twhin_model", "model", state)

    with pytest.raises(OSError):
        module.get_twhin_tokenizer()
    with pytest.raises(OSError):
        module.get_twhin_model("cpu")
    assert sorted(attempts) == ["model", "tokenizer"]

    with pytest.raises(patch.LocalModelUnavailable):
        module.get_twhin_tokenizer()
    with pytest.raises(patch.LocalModelUnavailable):
        module.get_twhin_model("cpu")


def test_successful_load_populates_oasis_global(monkeypatch):
    """有缓存时必须照常加载并写回全局变量，功能不能退化。"""
    monkeypatch.setattr(patch, "_load_local_only", lambda kind: f"LOADED-{kind}")

    module = _fake_recsys()
    patch.install_fast_loader(
        module, "get_twhin_tokenizer", "twhin_tokenizer", "tokenizer"
    )
    patch.install_fast_loader(module, "get_twhin_model", "twhin_model", "model")

    assert module.get_twhin_tokenizer() == "LOADED-tokenizer"
    assert module.twhin_tokenizer == "LOADED-tokenizer"
    assert module.get_twhin_model("cpu") == "LOADED-model"
    assert module.twhin_model == "LOADED-model"


def test_existing_global_short_circuits(monkeypatch):
    """OASIS 已经缓存过模型时，连探测都不该做。"""

    def boom(kind):
        raise AssertionError("不应触发加载")

    monkeypatch.setattr(patch, "_load_local_only", boom)

    module = _fake_recsys()
    module.twhin_tokenizer = "EXISTING"
    patch.install_fast_loader(
        module, "get_twhin_tokenizer", "twhin_tokenizer", "tokenizer"
    )

    assert module.get_twhin_tokenizer() == "EXISTING"


def test_missing_attribute_is_reported(monkeypatch):
    module = types.ModuleType("empty_recsys")
    with pytest.raises(AttributeError):
        patch.install_fast_loader(module, "get_twhin_tokenizer", "x", "tokenizer")


def test_apply_is_safe_when_oasis_unavailable(monkeypatch):
    monkeypatch.setattr("builtins.__import__", lambda *a, **k: (_ for _ in ()).throw(ImportError("no oasis")))
    assert patch.apply() is False


def test_recsys_switch_only_rewrites_twhin(monkeypatch):
    seen = {}

    class _Platform:
        def __init__(self, **kwargs):
            seen.clear()
            seen.update(kwargs)

    platform_module = types.ModuleType("oasis.social_platform.platform")
    platform_module.Platform = _Platform
    monkeypatch.setitem(sys.modules, "oasis", types.ModuleType("oasis"))
    monkeypatch.setitem(
        sys.modules, "oasis.social_platform", types.ModuleType("oasis.social_platform")
    )
    monkeypatch.setitem(sys.modules, "oasis.social_platform.platform", platform_module)

    patch._install_recsys_switch("twitter")

    _Platform(db_path="a.db", recsys_type="twhin-bert")
    assert seen["recsys_type"] == "twitter"

    _Platform(db_path="a.db", recsys_type="reddit")
    assert seen["recsys_type"] == "reddit"

    platform_module.Platform.__init__ = patch._ORIGINAL[(_Platform, "__init__")]
