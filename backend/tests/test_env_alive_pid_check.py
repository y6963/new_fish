"""
`check_env_alive()` 的进程存活校验契约。

背景：`env_status.json` 由模拟脚本在命令循环开始时写 `alive`、退出时写
`stopped`。进程被强杀（OOM / kill -9 / 崩溃）时文件会**永远停在 alive**，
导致后续采访命令白等 180 秒才超时。

修复原则是「安全增强」：
- 只有能**明确断定**进程不存在时才判为不存活；
- 任何不确定（无进程号、无权限、平台不支持、异常类型未知）都必须沿用
  文件标记，避免误杀正常流程。
"""

import json
import os
import sys

import pytest

from app.services.simulation_ipc import SimulationIPCClient, _process_exists


def _client(tmp_path, status=None, run_state=None):
    if status is not None:
        (tmp_path / "env_status.json").write_text(
            json.dumps(status), encoding="utf-8"
        )
    if run_state is not None:
        (tmp_path / "run_state.json").write_text(
            json.dumps(run_state), encoding="utf-8"
        )
    return SimulationIPCClient(str(tmp_path))


def _kill_raises(exc):
    def fake_kill(pid, sig):
        raise exc

    return fake_kill


# --------------------------------------------------------------------------
# 原有行为必须保持不变
# --------------------------------------------------------------------------

def test_missing_status_file_is_not_alive(tmp_path):
    assert _client(tmp_path).check_env_alive() is False


def test_stopped_status_is_not_alive(tmp_path):
    client = _client(tmp_path, status={"status": "stopped"})
    assert client.check_env_alive() is False


def test_corrupt_status_file_is_not_alive(tmp_path):
    (tmp_path / "env_status.json").write_text("{ 坏掉的 json", encoding="utf-8")
    assert SimulationIPCClient(str(tmp_path)).check_env_alive() is False


def test_alive_without_any_pid_is_trusted(tmp_path, monkeypatch):
    """没有进程号可校验时，必须沿用文件标记。"""
    monkeypatch.setattr(os, "kill", _kill_raises(ProcessLookupError()))
    client = _client(tmp_path, status={"status": "alive"})
    assert client.check_env_alive() is True


# --------------------------------------------------------------------------
# 新增：进程号校验
# --------------------------------------------------------------------------

def test_alive_and_process_running_is_alive(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: calls.append(pid))
    client = _client(
        tmp_path,
        status={"status": "alive", "pid": 4321},
    )
    assert client.check_env_alive() is True
    assert calls == [4321]


def test_alive_but_process_gone_is_not_alive(tmp_path, monkeypatch):
    """核心修复：进程已死时不能再说存活，否则采访要白等 180 秒。"""
    monkeypatch.setattr(os, "kill", _kill_raises(ProcessLookupError()))
    client = _client(tmp_path, status={"status": "alive", "pid": 4321})
    assert client.check_env_alive() is False


def test_pid_falls_back_to_run_state(tmp_path, monkeypatch):
    """env_status.json 没写 pid 时，用 run_state.json 里的 process_pid。"""
    monkeypatch.setattr(os, "kill", _kill_raises(ProcessLookupError()))
    client = _client(
        tmp_path,
        status={"status": "alive"},
        run_state={"process_pid": 9876},
    )
    assert client.check_env_alive() is False


def test_status_pid_takes_precedence_over_run_state(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: calls.append(pid))
    client = _client(
        tmp_path,
        status={"status": "alive", "pid": 1111},
        run_state={"process_pid": 2222},
    )
    assert client.check_env_alive() is True
    assert calls == [1111]


def test_missing_run_state_is_tolerated(tmp_path):
    client = _client(tmp_path, status={"status": "alive"})
    assert client.check_env_alive() is True


# --------------------------------------------------------------------------
# 保守性：不确定的情况一律判活
# --------------------------------------------------------------------------

def test_permission_error_still_alive(tmp_path, monkeypatch):
    """进程存在但不属于当前用户 —— 必须当作存活。"""
    monkeypatch.setattr(os, "kill", _kill_raises(PermissionError()))
    client = _client(tmp_path, status={"status": "alive", "pid": 4321})
    assert client.check_env_alive() is True


def test_unknown_oserror_still_alive(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "kill", _kill_raises(OSError(5, "boom")))
    client = _client(tmp_path, status={"status": "alive", "pid": 4321})
    assert client.check_env_alive() is True


def test_windows_skips_pid_check(tmp_path, monkeypatch):
    """Windows 上 os.kill(pid, 0) 语义不同，不参与判定。"""

    def boom(pid, sig):
        raise AssertionError("Windows 下不应调用 os.kill")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "kill", boom)
    client = _client(tmp_path, status={"status": "alive", "pid": 4321})
    assert client.check_env_alive() is True


@pytest.mark.parametrize("bad_pid", ["abc", None, 0, -5, {}, ""])
def test_invalid_pid_is_treated_as_unknown(tmp_path, monkeypatch, bad_pid):
    def boom(pid, sig):
        raise AssertionError("非法进程号不应触发探测")

    monkeypatch.setattr(os, "kill", boom)
    client = _client(tmp_path, status={"status": "alive", "pid": bad_pid})
    assert client.check_env_alive() is True


# --------------------------------------------------------------------------
# 辅助函数本身
# --------------------------------------------------------------------------

def test_process_exists_helper(monkeypatch):
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)
    assert _process_exists(123) is True

    monkeypatch.setattr(os, "kill", _kill_raises(ProcessLookupError()))
    assert _process_exists(123) is False

    monkeypatch.setattr(sys, "platform", "win32")
    assert _process_exists(123) is True
