"""Queue manager for background pipeline jobs."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dashboard.runner import format_cmd  # noqa: E402
from dashboard.state import load_project_config, project_dir  # noqa: E402
from shared.job_queue import (  # noqa: E402
    cancel_job,
    enqueue_job,
    load_queue,
    queue_summary,
    reconcile_queue,
    retry_job,
    start_worker,
    stop_worker,
    worker_alive,
)

st.set_page_config(page_title="Queue Manager", page_icon="🧵", layout="wide")

project_name = st.session_state.get("active_project")
if not project_name:
    st.info("Home에서 프로젝트를 선택하세요.")
    st.page_link("app.py", label="← Home", icon="🏠")
    st.stop()

pdir = project_dir(ROOT, project_name)
project_cfg = load_project_config(pdir)
input_file = st.session_state.get(f"input_{project_name}") or project_cfg.get("input")
if not input_file:
    st.error("프로젝트 input YAML을 찾을 수 없습니다.")
    st.stop()

LOUDNESS_OPTIONS = {
    "mobile (-14)": ("mobile", -14.0),
    "console (-16)": ("console", -16.0),
    "pc (-18)": ("pc", -18.0),
    "broadcast (-23)": ("broadcast", -23.0),
}

with st.sidebar:
    st.markdown(f"### 🧵 {project_name}")
    st.page_link("app.py", label="Home", icon="🏠")
    st.page_link("pages/1_🎛️_Studio.py", label="Studio", icon="🎛️")
    st.page_link("pages/5_🧮_Bulk_Authoring.py", label="Bulk Authoring", icon="🧮")
    st.page_link("pages/6_🧪_Review_Cockpit.py", label="Review Cockpit", icon="🧪")

st.title("Queue Manager")
st.caption("긴 배치를 백그라운드 큐로 쌓고 순차 실행합니다.")

queue_state = reconcile_queue(pdir, project_name)
summary = queue_summary(pdir)
running = worker_alive(pdir)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Queued", summary["queued"])
k2.metric("Running", summary["running"])
k3.metric("Done", summary["done"])
k4.metric("Failed", summary["failed"])
k5.metric("Worker", "running" if running else "idle")

st.subheader("Enqueue Job")
col_a, col_b, col_c = st.columns(3)
mode = col_a.selectbox("Preset", ["full", "post_only", "retake_only"])
backend = col_b.selectbox("Backend", ["local", "warm", "runpod"])
engine = col_c.selectbox("Engine", ["unity", "unity_addr", "fmod", "wwise"], index=["unity", "unity_addr", "fmod", "wwise"].index(project_cfg.get("engine", "unity")))

col_d, col_e, col_f = st.columns(3)
loudness_label = col_d.selectbox("Loudness", list(LOUDNESS_OPTIONS))
only_assets = col_e.text_input("Only assets (comma)", value="")
force = col_f.checkbox("Force regenerate", value=(mode == "retake_only"))

phases = None
label = "Full pipeline"
if mode == "post_only":
    phases = "5,6"
    label = "Post only"
elif mode == "retake_only":
    phases = "4,5,6"
    label = "Retake selected assets"

if st.button("Enqueue", type="primary"):
    loudness_platform, loudness_target = LOUDNESS_OPTIONS[loudness_label]
    item = enqueue_job(
        pdir,
        project_name,
        label=label,
        params={
            "project": project_name,
            "input_file": input_file,
            "phases": phases,
            "only": [s.strip() for s in only_assets.split(",") if s.strip()] or None,
            "force": force,
            "backend": backend,
            "engine": engine,
            "loudness_target": loudness_target,
            "loudness_platform": loudness_platform,
        },
    )
    st.success(f"Queued: {item['id']} · {item['label']}")
    st.rerun()

controls = st.columns(3)
if controls[0].button("Start Worker", use_container_width=True, disabled=running):
    start_worker(ROOT, pdir, project_name)
    st.success("Queue worker started")
    st.rerun()
if controls[1].button("Pause After Current", use_container_width=True, disabled=not running):
    stop_worker(pdir, immediate=False)
    st.info("Pause requested")
    st.rerun()
if controls[2].button("Stop Now", use_container_width=True, disabled=not running):
    stop_worker(pdir, immediate=True)
    st.warning("즉시 중지를 요청했어. 현재 실행 중인 잡은 워커 종료와 함께 다시 queued 로 돌아가.")
    st.rerun()

st.divider()
st.subheader("Queued Jobs")
items = list(reversed(queue_state.get("items", [])))
if not items:
    st.caption("큐가 비어 있습니다.")
else:
    for item in items:
        with st.container(border=True):
            st.markdown(f"**{item.get('label', '?')}** · `{item.get('id')}`")
            st.caption(f"status={item.get('status')} · created={item.get('created_at')}")
            st.code(format_cmd(**item.get("params", {})), language="bash")
            buttons = st.columns(3)
            if buttons[0].button("Retry", key=f"retry_{item['id']}", disabled=item.get("status") not in {"failed", "canceled", "done"}):
                retry_job(pdir, item["id"])
                st.rerun()
            if buttons[1].button("Cancel", key=f"cancel_{item['id']}", disabled=item.get("status") not in {"queued", "retry"}):
                cancel_job(pdir, item["id"])
                st.rerun()
            log_file = item.get("log_file")
            if log_file and Path(log_file).exists():
                with st.expander("Log tail", expanded=False):
                    lines = Path(log_file).read_text(encoding="utf-8", errors="ignore").splitlines()
                    st.code("\n".join(lines[-40:]), language="log")

worker = queue_state.get("worker", {})
if worker.get("log_file") and Path(worker["log_file"]).exists():
    st.divider()
    st.subheader("Worker Log")
    lines = Path(worker["log_file"]).read_text(encoding="utf-8", errors="ignore").splitlines()
    st.code("\n".join(lines[-60:]), language="log")
