"""平台完成 → 图谱收尾 → 生成报告 的契约测试。

背景：模拟脚本默认以"等待命令模式"运行，跑完轮次后仍常驻以响应采访命令，
进程不会退出；而收尾逻辑原本挂在"进程退出"上，导致 Zep 写入的尾巴永远排不空、
报告生成被永久卡住（表现为 409 "Zep cloud processing in progress"）。

因此：
1. 平台全部完成时就要主动触发图谱写入收尾（不终止进程，保留采访能力）；
2. "能否生成报告"只依赖 runner_status 成功终态，或"平台完成 + 收尾完成"；
3. 单平台模拟不能被当成"另一个平台没完成"而永远挡住；
4. 收尾失败要能被拦住并可重试，而不是静默用半张图谱写报告。
"""

from types import SimpleNamespace

import pytest
from flask import Flask

from app.api import report as report_api
from app.models.project import ProjectStatus
from app.services import simulation_runner as runner_module
from app.services.simulation_manager import SimulationStatus
from app.services.simulation_runner import (
    RunnerStatus,
    SimulationRunState,
    SimulationRunner,
)
from app.utils.zep_lifecycle import get_graph_readers, unregister_graph_reader


def _json_result(result):
    if isinstance(result, tuple):
        response, status = result
    else:
        response, status = result, result.status_code
    return response.get_json(), status


class _SyncThread:
    """让图谱收尾在测试中同步执行，便于断言。"""

    started = []

    def __init__(self, *, target, args=(), daemon=None):
        self.target = target
        self.args = args

    def start(self):
        _SyncThread.started.append(self.target)
        self.target(*self.args)


def _run_report_api(monkeypatch, run_state, updater=None):
    """按最简桩跑一遍 /api/report/generate，返回 (body, status)。"""

    simulation = SimpleNamespace(
        simulation_id="sim-1",
        project_id="proj-1",
        graph_id="graph-1",
        status=SimulationStatus.RUNNING,
    )
    project = SimpleNamespace(
        project_id="proj-1",
        graph_id="graph-1",
        status=ProjectStatus.GRAPH_COMPLETED,
        simulation_requirement="mock requirement",
    )

    class Tasks:
        def create_task(self, **_kwargs):
            return "task-1"

        def update_task(self, *_args, **_kwargs):
            pass

        def complete_task(self, *_args, **_kwargs):
            pass

        def fail_task(self, *_args, **_kwargs):
            pass

    class ParkedThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            pass

    class Agent:
        def __init__(self, **_kwargs):
            pass

        def generate_report(self, *, progress_callback, report_id):
            return SimpleNamespace(
                report_id=report_id,
                status=report_api.ReportStatus.COMPLETED,
                error=None,
            )

    monkeypatch.setattr(
        report_api,
        "SimulationManager",
        lambda: SimpleNamespace(get_simulation=lambda _simulation_id: simulation),
    )
    monkeypatch.setattr(
        report_api.ProjectManager,
        "get_project",
        classmethod(lambda _cls, _project_id: project),
    )
    monkeypatch.setattr(
        report_api.SimulationRunner,
        "get_run_state",
        classmethod(lambda _cls, _simulation_id: run_state),
    )
    monkeypatch.setattr(
        report_api.ZepGraphMemoryManager,
        "get_updater",
        classmethod(lambda _cls, _simulation_id: updater),
    )
    monkeypatch.setattr(
        report_api.ReportManager,
        "get_report_by_simulation",
        classmethod(lambda _cls, _simulation_id: None),
    )
    monkeypatch.setattr(
        report_api.ReportManager,
        "save_report",
        classmethod(lambda _cls, _report: None),
    )
    monkeypatch.setattr(report_api, "TaskManager", Tasks)
    monkeypatch.setattr(report_api, "ReportAgent", Agent)
    monkeypatch.setattr(report_api.threading, "Thread", ParkedThread)

    app = Flask(__name__)
    report_id = None
    try:
        with app.test_request_context(
            "/api/report/generate",
            method="POST",
            json={"simulation_id": "sim-1"},
        ):
            body, status = _json_result(report_api.generate_report())
        report_id = body.get("data", {}).get("report_id")
        return body, status
    finally:
        if report_id:
            unregister_graph_reader("graph-1", report_id)


def test_report_ready_while_simulation_process_still_alive(monkeypatch):
    """平台完成 + 图谱收尾完成后，即使 runner_status 仍是 RUNNING 也能出报告。"""

    run_state = SimulationRunState(
        simulation_id="sim-1",
        runner_status=RunnerStatus.RUNNING,
        twitter_completed=True,
        reddit_completed=True,
        all_platforms_completed=True,
        graph_ingestion_status="completed",
    )

    body, status = _run_report_api(monkeypatch, run_state)

    assert status == 200
    assert body["success"] is True


def test_single_platform_simulation_can_generate_report(monkeypatch):
    """只启用一个平台时，另一个平台的完成标记恒为 False，不能因此被永久挡住。"""

    run_state = SimulationRunState(
        simulation_id="sim-1",
        runner_status=RunnerStatus.RUNNING,
        twitter_completed=True,
        reddit_completed=False,
        all_platforms_completed=True,
        graph_ingestion_status="completed",
    )

    body, status = _run_report_api(monkeypatch, run_state)

    assert status == 200
    assert body["success"] is True


def test_pending_graph_ingestion_blocks_report_with_visible_numbers(monkeypatch):
    """收尾没做完时必须挡住，并把还剩多少告诉前端。"""

    class _Queue:
        def qsize(self):
            return 3

    class _Updater:
        _activity_queue = _Queue()
        _pending_episode_uuids = ["e1", "e2"]

    run_state = SimulationRunState(
        simulation_id="sim-1",
        runner_status=RunnerStatus.RUNNING,
        all_platforms_completed=True,
        graph_ingestion_status="draining",
    )

    body, status = _run_report_api(monkeypatch, run_state, updater=_Updater())

    assert status == 409
    assert body["ingestion_pending"] is True
    assert body["queue_size"] == 3


def test_in_flight_ingestion_finalization_is_waited_for(monkeypatch, tmp_path):
    """收尾线程仍在跑（写入器刚被移除）时不能放行。"""

    simulation_id = "sim-finalizing"
    run_state = SimulationRunState(
        simulation_id=simulation_id,
        runner_status=RunnerStatus.RUNNING,
        all_platforms_completed=True,
        graph_ingestion_status="draining",
    )

    monkeypatch.setattr(
        SimulationRunner, "RUN_STATE_DIR", str(tmp_path)
    )
    SimulationRunner._run_states[simulation_id] = run_state
    SimulationRunner._ingestion_finalizers.add(simulation_id)

    try:
        body, status = _run_report_api(monkeypatch, run_state, updater=None)

        assert status == 409
        assert body["ingestion_pending"] is True
    finally:
        SimulationRunner._run_states.pop(simulation_id, None)
        SimulationRunner._ingestion_finalizers.discard(simulation_id)


def test_no_writer_left_after_restart_does_not_block_forever(monkeypatch, tmp_path):
    """后端重启后内存写入队列已丢失：平台完成且无写入器时应收敛，而不是永久 409。"""

    simulation_id = "sim-restarted"
    run_state = SimulationRunState(
        simulation_id=simulation_id,
        runner_status=RunnerStatus.RUNNING,
        twitter_completed=True,
        reddit_completed=True,
        all_platforms_completed=True,
        graph_ingestion_status="pending",
    )

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(
        runner_module.ZepGraphMemoryManager,
        "get_updater",
        classmethod(lambda _cls, _sim_id: None),
    )
    SimulationRunner._run_states[simulation_id] = run_state
    SimulationRunner._ingestion_finalizers.discard(simulation_id)

    try:
        body, status = _run_report_api(monkeypatch, run_state, updater=None)

        assert status == 200
        # 状态记账要跟着收敛，避免前端一直显示"写入中"
        assert run_state.graph_ingestion_status == "completed"
    finally:
        SimulationRunner._run_states.pop(simulation_id, None)
        SimulationRunner._ingestion_finalizers.discard(simulation_id)


def test_failed_graph_ingestion_blocks_report_and_marks_retryable(monkeypatch):
    run_state = SimulationRunState(
        simulation_id="sim-1",
        runner_status=RunnerStatus.RUNNING,
        all_platforms_completed=True,
        graph_ingestion_status="failed",
        graph_ingestion_error="Zep图谱写入未完整完成: timeout",
    )

    body, status = _run_report_api(monkeypatch, run_state)

    assert status == 409
    assert body["ingestion_failed"] is True
    assert "timeout" in body["error"]


def test_run_state_exposes_report_ready_flag():
    """report_ready 是前端判断"能不能进第四步"的唯一依据。"""

    not_ready = SimulationRunState(
        simulation_id="sim-1",
        runner_status=RunnerStatus.RUNNING,
        all_platforms_completed=True,
        graph_ingestion_status="draining",
    )
    assert not_ready.to_dict()["report_ready"] is False

    ready = SimulationRunState(
        simulation_id="sim-1",
        runner_status=RunnerStatus.RUNNING,
        all_platforms_completed=True,
        graph_ingestion_status="completed",
    )
    assert ready.to_dict()["report_ready"] is True

    terminal = SimulationRunState(
        simulation_id="sim-1", runner_status=RunnerStatus.COMPLETED
    )
    assert terminal.to_dict()["report_ready"] is True


def test_platform_completion_triggers_graph_ingestion_finalization(
    monkeypatch, tmp_path
):
    """平台跑完的那一刻就要开始排空图谱写入，而不是等进程退出。"""

    simulation_id = "sim-drain"
    sim_dir = tmp_path / simulation_id / "twitter"
    sim_dir.mkdir(parents=True)
    log_path = sim_dir / "actions.jsonl"
    log_path.write_text(
        '{"event_type":"simulation_end","total_rounds":1,"total_actions":0}\n',
        encoding="utf-8",
    )

    state = SimulationRunState(
        simulation_id=simulation_id,
        runner_status=RunnerStatus.RUNNING,
        twitter_running=True,
    )
    drained = []

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(runner_module.threading, "Thread", _SyncThread)
    monkeypatch.setattr(
        runner_module.ZepGraphMemoryManager,
        "stop_updater",
        classmethod(lambda _cls, sim_id: drained.append(sim_id)),
    )

    SimulationRunner._run_states[simulation_id] = state
    SimulationRunner._graph_memory_enabled[simulation_id] = True
    SimulationRunner._ingestion_finalizers.discard(simulation_id)
    _SyncThread.started = []

    try:
        SimulationRunner._read_action_log(str(log_path), 0, state, "twitter")

        assert state.twitter_completed is True
        assert state.all_platforms_completed is True
        # 进程仍存活，终态不提前发布
        assert state.runner_status == RunnerStatus.RUNNING
        # 但图谱写入已经排空并记账
        assert drained == [simulation_id]
        assert state.graph_ingestion_status == "completed"
        assert state.is_report_ready() is True
    finally:
        SimulationRunner._run_states.pop(simulation_id, None)
        SimulationRunner._graph_memory_enabled.pop(simulation_id, None)
        SimulationRunner._ingestion_finalizers.discard(simulation_id)


def test_graph_ingestion_is_not_finalized_twice(monkeypatch, tmp_path):
    """重复读到 simulation_end 事件不应重复排空。"""

    simulation_id = "sim-once"
    sim_dir = tmp_path / simulation_id / "twitter"
    sim_dir.mkdir(parents=True)
    log_path = sim_dir / "actions.jsonl"
    log_path.write_text(
        '{"event_type":"simulation_end","total_rounds":1,"total_actions":0}\n',
        encoding="utf-8",
    )

    state = SimulationRunState(
        simulation_id=simulation_id,
        runner_status=RunnerStatus.RUNNING,
    )
    drained = []

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(runner_module.threading, "Thread", _SyncThread)
    monkeypatch.setattr(
        runner_module.ZepGraphMemoryManager,
        "stop_updater",
        classmethod(lambda _cls, sim_id: drained.append(sim_id)),
    )

    SimulationRunner._run_states[simulation_id] = state
    SimulationRunner._graph_memory_enabled[simulation_id] = True
    SimulationRunner._ingestion_finalizers.discard(simulation_id)
    _SyncThread.started = []

    try:
        SimulationRunner._read_action_log(str(log_path), 0, state, "twitter")
        # 第二次仍从 0 读，模拟重复处理同一批事件
        SimulationRunner._read_action_log(str(log_path), 0, state, "twitter")

        assert drained == [simulation_id]
        assert len(_SyncThread.started) == 1
    finally:
        SimulationRunner._run_states.pop(simulation_id, None)
        SimulationRunner._graph_memory_enabled.pop(simulation_id, None)
        SimulationRunner._ingestion_finalizers.discard(simulation_id)


def test_retry_graph_ingestion_recovers_from_failure(monkeypatch, tmp_path):
    """收尾失败后可以重试，且不需要重跑模拟。"""

    simulation_id = "sim-retry"
    state = SimulationRunState(
        simulation_id=simulation_id,
        runner_status=RunnerStatus.RUNNING,
        all_platforms_completed=True,
        graph_ingestion_status="failed",
        graph_ingestion_error="Zep图谱写入未完整完成: timeout",
    )
    drained = []

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(runner_module.threading, "Thread", _SyncThread)
    monkeypatch.setattr(
        runner_module.ZepGraphMemoryManager,
        "get_updater",
        classmethod(lambda _cls, _sim_id: object()),
    )
    monkeypatch.setattr(
        runner_module.ZepGraphMemoryManager,
        "stop_updater",
        classmethod(lambda _cls, sim_id: drained.append(sim_id)),
    )

    SimulationRunner._run_states[simulation_id] = state
    SimulationRunner._graph_memory_enabled.pop(simulation_id, None)
    SimulationRunner._ingestion_finalizers.discard(simulation_id)

    try:
        assert SimulationRunner.retry_graph_ingestion(simulation_id) is True
        assert drained == [simulation_id]
        assert state.graph_ingestion_status == "completed"
        assert state.graph_ingestion_error is None
        assert state.is_report_ready() is True
    finally:
        SimulationRunner._run_states.pop(simulation_id, None)
        SimulationRunner._graph_memory_enabled.pop(simulation_id, None)
        SimulationRunner._ingestion_finalizers.discard(simulation_id)


def test_legacy_run_state_file_is_upgraded_without_lying(tmp_path, monkeypatch):
    """旧 run_state.json（没有新字段）不能被推断成"已就绪"。"""

    simulation_id = "sim-legacy"
    sim_dir = tmp_path / simulation_id
    sim_dir.mkdir(parents=True)
    (sim_dir / "run_state.json").write_text(
        '{"simulation_id": "sim-legacy", "runner_status": "running",'
        ' "twitter_completed": true, "reddit_completed": true}',
        encoding="utf-8",
    )

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    SimulationRunner._run_states.pop(simulation_id, None)

    state = SimulationRunner._load_run_state(simulation_id)

    assert state is not None
    assert state.all_platforms_completed is True
    # 旧文件没记录收尾，必须回到 pending，等真实排空
    assert state.graph_ingestion_status == "pending"
    assert state.is_report_ready() is False
