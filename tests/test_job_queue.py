"""Background job queue helpers."""
from __future__ import annotations

import signal
from pathlib import Path

from shared.job_queue import (
    complete_job,
    enqueue_job,
    next_runnable_job,
    pipeline_cmd,
    queue_summary,
    reconcile_queue,
    save_queue,
    stop_worker,
    retry_job,
)


def test_queue_lifecycle(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    item = enqueue_job(
        project_dir,
        "proj",
        label="Full pipeline",
        params={"project": "proj", "input_file": "input.yaml", "backend": "local"},
    )
    assert item["status"] == "queued"

    running = next_runnable_job(project_dir)
    assert running is not None
    assert running["status"] == "running"

    log_path = project_dir / "queue_logs" / "job.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("ok", encoding="utf-8")
    complete_job(project_dir, running["id"], exit_code=1, log_file=log_path, error="boom")

    summary = queue_summary(project_dir)
    assert summary["failed"] == 1

    retried = retry_job(project_dir, running["id"])
    assert retried is not None
    assert retried["status"] == "retry"


def test_pipeline_cmd_builds_flags(tmp_path):
    root = tmp_path
    cmd = pipeline_cmd(
        root,
        {
            "project": "proj",
            "input_file": "input.yaml",
            "backend": "warm",
            "phases": "5,6",
            "only": ["sfx_click"],
            "force": True,
            "engine": "fmod",
            "loudness_target": -16.0,
            "loudness_platform": "console",
        },
        python_exec="python3",
    )
    joined = " ".join(cmd)
    assert "--phases 5,6" in joined
    assert "--only sfx_click" in joined
    assert "--engine fmod" in joined
    assert "--loudness-platform console" in joined


def test_reconcile_queue_requeues_running_job_when_worker_is_gone(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    save_queue(project_dir, {
        "project": "proj",
        "items": [
            {
                "id": "job_a",
                "label": "Full pipeline",
                "params": {},
                "status": "running",
                "created_at": "now",
                "started_at": "now",
                "finished_at": None,
                "exit_code": None,
                "log_file": None,
                "error": None,
            }
        ],
        "worker": {
            "running": True,
            "pid": 777,
            "current_job_id": "job_a",
            "current_run_pid": 888,
            "current_run_pgid": 888,
            "current_run_started_at": "now",
            "pause_requested": False,
            "stop_requested": False,
            "last_exit_code": None,
        },
    })
    monkeypatch.setattr("shared.job_queue._pid_alive", lambda pid: False)

    state = reconcile_queue(project_dir, "proj")

    assert state["items"][0]["status"] == "queued"
    assert state["items"][0]["started_at"] is None
    assert state["items"][0]["error"] == "worker exited before completion"
    assert state["worker"]["running"] is False
    assert state["worker"]["pid"] is None
    assert state["worker"]["current_run_pid"] is None


def test_stop_worker_immediate_signals_child_group_and_worker(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    save_queue(project_dir, {
        "project": "proj",
        "items": [],
        "worker": {
            "running": True,
            "pid": 111,
            "started_at": "now",
            "current_job_id": "job_a",
            "current_run_pid": 222,
            "current_run_pgid": 333,
            "current_run_started_at": "now",
            "pause_requested": False,
            "stop_requested": False,
            "log_file": None,
            "last_exit_code": None,
        },
    })
    monkeypatch.setattr("shared.job_queue._pid_alive", lambda pid: pid == 111)
    sent = {"kill": [], "killpg": []}

    def fake_kill(pid, sig):
        sent["kill"].append((pid, sig))

    def fake_killpg(pgid, sig):
        sent["killpg"].append((pgid, sig))

    monkeypatch.setattr("shared.job_queue.os.kill", fake_kill)
    monkeypatch.setattr("shared.job_queue.os.killpg", fake_killpg)

    worker = stop_worker(project_dir, immediate=True)

    assert worker["stop_requested"] is True
    assert sent["killpg"] == [(333, signal.SIGTERM)]
    assert sent["kill"] == [(111, signal.SIGTERM)]
