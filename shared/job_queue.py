"""File-backed project queue for background pipeline jobs."""
from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


QUEUE_FILE = "job_queue.json"
QUEUE_LOCK_FILE = "job_queue.lock"
WORKER_LOG = "queue_worker.log"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def queue_path(project_dir: Path) -> Path:
    return project_dir / QUEUE_FILE


def queue_lock_path(project_dir: Path) -> Path:
    return project_dir / QUEUE_LOCK_FILE


def worker_log_path(project_dir: Path) -> Path:
    return project_dir / WORKER_LOG


def job_log_path(project_dir: Path, job_id: str) -> Path:
    return project_dir / "queue_logs" / f"{job_id}.log"


def _default_worker_state() -> dict[str, Any]:
    return {
        "running": False,
        "pid": None,
        "started_at": None,
        "current_job_id": None,
        "current_run_pid": None,
        "current_run_pgid": None,
        "current_run_started_at": None,
        "pause_requested": False,
        "stop_requested": False,
        "log_file": None,
        "last_exit_code": None,
    }


def _default_state(project_name: str = "") -> dict[str, Any]:
    return {
        "project": project_name,
        "items": [],
        "worker": _default_worker_state(),
    }


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@contextmanager
def _queue_lock(project_dir: Path) -> Iterator[None]:
    lock_path = queue_lock_path(project_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


def _merge_defaults(data: dict[str, Any], project_name: str = "") -> dict[str, Any]:
    state = dict(data)
    state.setdefault("items", [])
    worker = _default_worker_state()
    worker.update(state.get("worker") or {})
    state["worker"] = worker
    if project_name and not state.get("project"):
        state["project"] = project_name
    return state


def _load_queue_unlocked(project_dir: Path, project_name: str = "") -> dict[str, Any]:
    path = queue_path(project_dir)
    if not path.exists():
        return _default_state(project_name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_state(project_name)
    return _merge_defaults(data, project_name)


def load_queue(project_dir: Path, project_name: str = "") -> dict[str, Any]:
    return _load_queue_unlocked(project_dir, project_name)


def _save_queue_unlocked(project_dir: Path, state: dict[str, Any]) -> Path:
    path = queue_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _merge_defaults(state, state.get("project", ""))
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)
    return path


def save_queue(project_dir: Path, state: dict[str, Any]) -> Path:
    with _queue_lock(project_dir):
        return _save_queue_unlocked(project_dir, state)


def _reset_worker_runtime(worker: dict[str, Any], *, pause_requested: bool | None = None) -> None:
    worker["running"] = False
    worker["pid"] = None
    worker["current_job_id"] = None
    worker["current_run_pid"] = None
    worker["current_run_pgid"] = None
    worker["current_run_started_at"] = None
    worker["stop_requested"] = False
    if pause_requested is not None:
        worker["pause_requested"] = pause_requested


def _requeue_running_items(state: dict[str, Any], reason: str) -> None:
    for item in state.get("items", []):
        if item.get("status") == "running":
            item["status"] = "queued"
            item["started_at"] = None
            item["finished_at"] = None
            item["exit_code"] = None
            item["error"] = reason


def _reconcile_state(state: dict[str, Any]) -> dict[str, Any]:
    worker = state.setdefault("worker", _default_worker_state())
    pid = worker.get("pid")
    alive = _pid_alive(pid)
    if worker.get("running") and not alive:
        _requeue_running_items(state, "worker exited before completion")
        _reset_worker_runtime(worker, pause_requested=False)
        worker["last_exit_code"] = worker.get("last_exit_code", 1)
    return state


def _mutate_queue(
    project_dir: Path,
    project_name: str,
    mutator,
    *,
    reconcile: bool = True,
) -> tuple[dict[str, Any], Any]:
    with _queue_lock(project_dir):
        state = _load_queue_unlocked(project_dir, project_name)
        if reconcile:
            state = _reconcile_state(state)
        result = mutator(state)
        _save_queue_unlocked(project_dir, state)
    return state, result


def reconcile_queue(project_dir: Path, project_name: str = "") -> dict[str, Any]:
    state, _ = _mutate_queue(project_dir, project_name, lambda current: current)
    return state


def enqueue_job(project_dir: Path, project_name: str, *, label: str, params: dict[str, Any]) -> dict[str, Any]:
    def _mutator(state: dict[str, Any]) -> dict[str, Any]:
        item = {
            "id": uuid4().hex[:10],
            "label": label,
            "params": params,
            "status": "queued",
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "exit_code": None,
            "log_file": None,
            "error": None,
        }
        state["items"].append(item)
        return item

    _, item = _mutate_queue(project_dir, project_name, _mutator)
    return item


def update_job(project_dir: Path, job_id: str, **patch: Any) -> dict[str, Any] | None:
    def _mutator(state: dict[str, Any]) -> dict[str, Any] | None:
        for item in state.get("items", []):
            if item.get("id") == job_id:
                item.update(patch)
                return item
        return None

    _, item = _mutate_queue(project_dir, "", _mutator)
    return item


def set_worker_state(project_dir: Path, **patch: Any) -> dict[str, Any]:
    def _mutator(state: dict[str, Any]) -> dict[str, Any]:
        worker = state.setdefault("worker", _default_worker_state())
        worker.update(patch)
        return worker

    _, worker = _mutate_queue(project_dir, "", _mutator)
    return worker


def request_pause(project_dir: Path, pause: bool = True) -> dict[str, Any]:
    return set_worker_state(project_dir, pause_requested=pause)


def next_runnable_job(project_dir: Path) -> dict[str, Any] | None:
    def _mutator(state: dict[str, Any]) -> dict[str, Any] | None:
        worker = state.get("worker", {})
        if worker.get("pause_requested"):
            return None
        for item in state.get("items", []):
            if item.get("status") in {"queued", "retry"}:
                item["status"] = "running"
                item["started_at"] = _now()
                item["finished_at"] = None
                item["exit_code"] = None
                item["error"] = None
                worker["current_job_id"] = item["id"]
                return item
        return None

    _, item = _mutate_queue(project_dir, "", _mutator)
    return item


def requeue_job(project_dir: Path, job_id: str, *, error: str | None = None) -> dict[str, Any] | None:
    def _mutator(state: dict[str, Any]) -> dict[str, Any] | None:
        worker = state.setdefault("worker", _default_worker_state())
        for item in state.get("items", []):
            if item.get("id") == job_id:
                item["status"] = "queued"
                item["started_at"] = None
                item["finished_at"] = None
                item["exit_code"] = None
                item["error"] = error
                worker["current_job_id"] = None
                worker["current_run_pid"] = None
                worker["current_run_pgid"] = None
                worker["current_run_started_at"] = None
                return item
        return None

    _, item = _mutate_queue(project_dir, "", _mutator)
    return item


def complete_job(
    project_dir: Path,
    job_id: str,
    *,
    exit_code: int,
    log_file: Path,
    error: str | None = None,
) -> dict[str, Any] | None:
    def _mutator(state: dict[str, Any]) -> dict[str, Any] | None:
        worker = state.setdefault("worker", _default_worker_state())
        target = None
        for item in state.get("items", []):
            if item.get("id") == job_id:
                item["status"] = "done" if exit_code == 0 else "failed"
                item["finished_at"] = _now()
                item["exit_code"] = exit_code
                item["log_file"] = str(log_file)
                item["error"] = error
                target = item
                break
        worker["current_job_id"] = None
        worker["current_run_pid"] = None
        worker["current_run_pgid"] = None
        worker["current_run_started_at"] = None
        return target

    _, item = _mutate_queue(project_dir, "", _mutator)
    return item


def retry_job(project_dir: Path, job_id: str) -> dict[str, Any] | None:
    return update_job(
        project_dir,
        job_id,
        status="retry",
        started_at=None,
        finished_at=None,
        exit_code=None,
        error=None,
    )


def cancel_job(project_dir: Path, job_id: str) -> dict[str, Any] | None:
    return update_job(project_dir, job_id, status="canceled", finished_at=_now())


def queue_summary(project_dir: Path) -> dict[str, int]:
    state = reconcile_queue(project_dir)
    summary = {"queued": 0, "running": 0, "done": 0, "failed": 0, "canceled": 0}
    for item in state.get("items", []):
        status = item.get("status", "queued")
        summary[status] = summary.get(status, 0) + 1
    return summary


def pipeline_cmd(root: Path, params: dict[str, Any], python_exec: str | None = None) -> list[str]:
    cmd = [
        python_exec or sys.executable,
        str(root / "audio_studio.py"),
        "--project",
        params["project"],
        "--input",
        params["input_file"],
        "--backend",
        params.get("backend", "local"),
    ]
    if params.get("phases"):
        cmd += ["--phases", params["phases"]]
    if params.get("only"):
        cmd += ["--only", ",".join(params["only"])]
    if params.get("force"):
        cmd.append("--force")
    if params.get("engine"):
        cmd += ["--engine", params["engine"]]
    if params.get("loudness_target") is not None:
        cmd += ["--loudness-target", str(params["loudness_target"])]
    if params.get("loudness_platform"):
        cmd += ["--loudness-platform", params["loudness_platform"]]
    if params.get("output"):
        cmd += ["--output", params["output"]]
    return cmd


def worker_alive(project_dir: Path) -> bool:
    state = reconcile_queue(project_dir)
    worker = state.get("worker", {})
    return bool(worker.get("running") and _pid_alive(worker.get("pid")))


def start_worker(root: Path, project_dir: Path, project_name: str) -> dict[str, Any]:
    state = reconcile_queue(project_dir, project_name)
    worker = state.get("worker", {})
    if worker.get("running") and _pid_alive(worker.get("pid")):
        return worker

    log_path = worker_log_path(project_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log_f:
        proc = subprocess.Popen(
            [sys.executable, str(root / "scripts" / "queue_worker.py"), "--project", project_name, "--root", str(root)],
            stdout=log_f,
            stderr=log_f,
            cwd=str(root),
            start_new_session=True,
        )
    worker = set_worker_state(
        project_dir,
        running=True,
        pid=proc.pid,
        started_at=_now(),
        current_job_id=None,
        current_run_pid=None,
        current_run_pgid=None,
        current_run_started_at=None,
        pause_requested=False,
        stop_requested=False,
        log_file=str(log_path),
        last_exit_code=None,
    )
    return worker


def _signal_process_group(pgid: int | None, sig: signal.Signals) -> None:
    if not pgid:
        return
    try:
        os.killpg(pgid, sig)
    except OSError:
        return


def _signal_process(pid: int | None, sig: signal.Signals) -> None:
    if not pid or not _pid_alive(pid):
        return
    try:
        os.kill(pid, sig)
    except OSError:
        return


def stop_worker(project_dir: Path, *, immediate: bool = False) -> dict[str, Any]:
    state = reconcile_queue(project_dir)
    worker = state.get("worker", {})
    pid = worker.get("pid")
    run_pgid = worker.get("current_run_pgid")
    run_pid = worker.get("current_run_pid")

    if immediate:
        worker = set_worker_state(project_dir, pause_requested=False, stop_requested=True)
        _signal_process_group(run_pgid, signal.SIGTERM)
        if not run_pgid:
            _signal_process(run_pid, signal.SIGTERM)
        _signal_process(pid, signal.SIGTERM)
        return worker

    return set_worker_state(project_dir, pause_requested=True)
