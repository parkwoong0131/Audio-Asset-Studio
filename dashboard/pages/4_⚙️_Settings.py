"""Settings — daemon / backend / 환경 점검."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
st.title("⚙️ Settings")


# ----- environment -----
st.subheader("Environment")
c1, c2, c3 = st.columns(3)
c1.metric("Python", platform.python_version())
c2.metric("OS", f"{platform.system()} {platform.release()}")
c3.metric("Arch", platform.machine())

def _has(pkg: str) -> bool:
    try:
        __import__(pkg.replace("-", "_"))
        return True
    except ImportError:
        return False

deps = {
    "torch": _has("torch"),
    "audiocraft": _has("audiocraft"),
    "soundfile": _has("soundfile"),
    "pyloudnorm": _has("pyloudnorm"),
    "laion-clap": _has("laion_clap"),
    "demucs": _has("demucs"),
    "chromadb": _has("chromadb"),
    "openpyxl": _has("openpyxl"),
    "streamlit": True,
    "ffmpeg (CLI)": shutil.which("ffmpeg") is not None,
}
st.markdown("**Dependencies**")
for name, ok in deps.items():
    st.markdown(f"{'✅' if ok else '❌'}  `{name}`")

if not all(deps.values()):
    if st.button("📦 pip install -r requirements.txt"):
        with st.spinner("설치 중..."):
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                cwd=str(ROOT), capture_output=True, text=True,
            )
        st.code(r.stdout + "\n" + r.stderr, language="log")


# ----- model_server -----
st.divider()
st.subheader("Model server (warm pool)")
from shared.daemon import ensure_running, status, stop

s = status()
sc1, sc2 = st.columns(2)
sc1.metric("Status", "🟢 running" if s["running"] else "⚪ idle")
sc2.metric("Endpoint", s["endpoint"])

b1, b2, b3 = st.columns(3)
if b1.button("▶️ Start"):
    try:
        with st.spinner("기동 중..."):
            ensure_running()
        st.success("running")
    except Exception as e:
        st.error(str(e))
if b2.button("⏹ Stop"):
    if stop():
        st.success("종료됨")
    else:
        st.info("이미 꺼져있음")
if b3.button("🔥 Warm (medium models)"):
    try:
        import requests
        ensure_running()
        r = requests.post(f"{s['endpoint']}/warm",
                          json={"models": ["musicgen-medium", "audiogen-medium"]}, timeout=900)
        st.code(r.text)
    except Exception as e:
        st.error(str(e))

st.caption(f"로그: `{s['log_file']}`")


# ----- cache -----
st.divider()
st.subheader("Cache & outputs")
out_dir = ROOT / "output"
total_files = sum(1 for _ in out_dir.rglob("*")) if out_dir.exists() else 0
st.metric("Output files", total_files)
confirm_key = "confirm_clear_outputs"
confirm_phrase_key = "confirm_clear_outputs_phrase"
if st.button("🗑️ Clear all outputs", type="secondary"):
    st.session_state[confirm_key] = True

if st.session_state.get(confirm_key):
    st.warning("`output/` 아래 생성물, 리포트, 큐 로그를 전부 지워. 되돌릴 수 없어.")
    st.text_input("확인 입력", key=confirm_phrase_key, placeholder="CLEAR")
    danger_cols = st.columns([1, 1, 2])
    if danger_cols[0].button(
        "정말 삭제",
        type="primary",
        disabled=st.session_state.get(confirm_phrase_key, "") != "CLEAR",
    ):
        if out_dir.exists():
            shutil.rmtree(out_dir)
        st.session_state[confirm_key] = False
        st.session_state.pop(confirm_phrase_key, None)
        st.success("지워짐 (다음 실행부터 재생성)")
        st.rerun()
    if danger_cols[1].button("취소"):
        st.session_state[confirm_key] = False
        st.session_state.pop(confirm_phrase_key, None)
        st.rerun()

prompt_lib_root = Path.home() / ".audio_asset_studio" / "prompt_library"
if prompt_lib_root.exists():
    st.caption(f"Prompt Library path: `{prompt_lib_root}`")
