#!/usr/bin/env python3
"""Background queue worker for Audio Asset Studio."""
from __future__ import annotations

import argparse
import os
import subprocess
import signal
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.job_queue import (  # noqa: E402
    complete_job,
    job_log_path,
    load_queue,
    next_runnable_job,
    pipeline_cmd,
    reconcile_queue,
    requeue_job,
    set_worker_state,
)


ACTIVE_PROC: subprocess.Popen[str] | None = None
STOP_REQUESTED = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _terminate_active_proc() -> None:
    global ACTIVE_PROC

    proc = ACTIVE_PROC
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        try:
            proc.terminate()
        except OSError:
            return


def _handle_stop(signum, _frame) -> None:
    del signum
    global STOP_REQUESTED
    STOP_REQUESTED = True
    _terminate_active_proc()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audio Asset Studio queue worker")
    parser.add_argument("--project", required=True, help="project id")
    parser.add_argument("--root", default=str(ROOT), help="repo root")
    return parser.parse_args()


def main() -> int:
    global ACTIVE_PROC
    global STOP_REQUESTED

    args = parse_args()
    root = Path(args.root).resolve()
    project_dir = root / "output" / args.project
    project_dir.mkdir(parents=True, exist_ok=True)

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    set_worker_state(
        project_dir,
        running=True,
        pid=os.getpid(),
        current_job_id=None,
        current_run_pid=None,
        current_run_pgid=None,
        current_run_started_at=None,
        pause_requested=False,
        stop_requested=False,
    )
    try:
        while True:
            if STOP_REQUESTED:
                break
            reconcile_queue(project_dir, args.project)
            state = load_queue(project_dir, args.project)
            if state.get("worker", {}).get("pause_requested"):
                break

            item = next_runnable_job(project_dir)
            if not item:
                break

            log_path = job_log_path(project_dir, item["id"])
            log_path.parent.mkdir(parents=True, exist_ok=True)
            cmd = pipeline_cmd(root, item["params"])

            with log_path.open("a", encoding="utf-8") as log_f:
                log_f.write(f"$ {' '.join(cmd)}\n")
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(root),
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
                ACTIVE_PROC = proc
                set_worker_state(
                    project_dir,
                    current_run_pid=proc.pid,
                    current_run_pgid=proc.pid,
                    current_run_started_at=_now(),
                    stop_requested=False,
                )
                exit_code = proc.wait()
                ACTIVE_PROC = None

            if STOP_REQUESTED:
                requeue_job(project_dir, item["id"], error="worker stopped manually")
                break

            complete_job(
                project_dir,
                item["id"],
                exit_code=exit_code,
                log_file=log_path,
                error=None if exit_code == 0 else f"exit code {exit_code}",
            )
    except Exception:
        trace = traceback.format_exc()
        worker = load_queue(project_dir, args.project).get("worker", {})
        current_job_id = worker.get("current_job_id")
        if current_job_id:
            log_path = job_log_path(project_dir, current_job_id)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as log_f:
                log_f.write("\n[queue-worker exception]\n")
                log_f.write(trace)
            if STOP_REQUESTED:
                requeue_job(project_dir, current_job_id, error="worker stopped manually")
            else:
                complete_job(project_dir, current_job_id, exit_code=1, log_file=log_path, error="queue worker exception")
        ACTIVE_PROC = None
        set_worker_state(
            project_dir,
            running=False,
            pid=None,
            current_job_id=None,
            current_run_pid=None,
            current_run_pgid=None,
            current_run_started_at=None,
            pause_requested=False,
            stop_requested=False,
            last_exit_code=130 if STOP_REQUESTED else 1,
        )
        if STOP_REQUESTED:
            return 130
        print(trace, file=sys.stderr)
        return 1

    ACTIVE_PROC = None
    set_worker_state(
        project_dir,
        running=False,
        pid=None,
        current_job_id=None,
        current_run_pid=None,
        current_run_pgid=None,
        current_run_started_at=None,
        pause_requested=False,
        stop_requested=False,
        last_exit_code=130 if STOP_REQUESTED else 0,
    )
    return 130 if STOP_REQUESTED else 0


if __name__ == "__main__":
    sys.exit(main())
