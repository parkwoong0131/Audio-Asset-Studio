"""Audio Asset Studio — Home.

실행:
    streamlit run dashboard/app.py
        또는
    ./studio

원칙:
  · 빈 상태엔 1개의 명확한 primary action ("새 프로젝트 만들기")
  · 설정/터미널 없이 대시보드만으로 끝까지 가능
  · CLI는 자동화용, 디자이너는 이 UI만 있으면 됨
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dashboard.state import daemon_badge, load_projects, recent_activity  # noqa: E402

st.set_page_config(
    page_title="Audio Asset Studio",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----- sidebar -----
with st.sidebar:
    st.markdown("### Audio Asset Studio")
    st.caption("프롬프트 기반 게임 오디오 에셋 파이프라인")
    st.divider()
    st.markdown(daemon_badge())
    st.divider()
    st.page_link("app.py", label="Home", icon="🏠")
    st.page_link("pages/1_🎛️_Studio.py", label="Studio", icon="🎛️")
    st.page_link("pages/2_🪄_New_Project.py", label="New Project", icon="🪄")
    st.page_link("pages/3_📚_Prompt_Library.py", label="Prompt Library", icon="📚")
    st.page_link("pages/5_🧮_Bulk_Authoring.py", label="Bulk Authoring", icon="🧮")
    st.page_link("pages/6_🧪_Review_Cockpit.py", label="Review Cockpit", icon="🧪")
    st.page_link("pages/7_🧵_Queue_Manager.py", label="Queue Manager", icon="🧵")
    st.page_link("pages/4_⚙️_Settings.py", label="Settings", icon="⚙️")

# ----- header -----
col_l, col_r = st.columns([3, 1])
with col_l:
    st.title("Projects")
    st.caption("프로젝트를 열거나 새로 만듭니다.")
with col_r:
    if st.button("＋ New Project", use_container_width=True, type="primary"):
        st.switch_page("pages/2_🪄_New_Project.py")

projects = load_projects(ROOT)

# ----- empty state -----
if not projects:
    st.divider()
    st.markdown(
        """
        #### 아직 프로젝트가 없습니다
        첫 프로젝트를 만들어 시작하세요. 장르/레퍼런스 게임만 고르면 SFX·BGM 명세가 자동 생성됩니다.
        """
    )
    if st.button("🪄 3-step 프로젝트 위저드 열기", type="primary"):
        st.switch_page("pages/2_🪄_New_Project.py")
    st.stop()

# ----- project cards -----
st.divider()
cols = st.columns(3)
for i, proj in enumerate(projects):
    with cols[i % 3]:
        with st.container(border=True):
            st.markdown(f"#### {proj['name']}")
            meta = proj.get("meta", {})
            if meta.get("palette"):
                st.caption(f"🎨 {meta['palette']}")
            st.caption(
                f"{proj['generated']} generated · "
                f"{proj['cached']} cached · "
                f"{proj['failed']} failed"
            )
            if proj.get("budget_spent") is not None:
                st.caption(f"💰 ${proj['budget_spent']:.2f} spent")
            st.caption(f"🕒 {proj['mtime_rel']}")
            if st.button("Open", key=f"open_{proj['name']}", use_container_width=True):
                st.session_state["active_project"] = proj["name"]
                input_path = meta.get("input")
                if input_path:
                    st.session_state[f"input_{proj['name']}"] = input_path
                st.switch_page("pages/1_🎛️_Studio.py")

# ----- recent activity -----
st.divider()
st.subheader("Recent activity")
activity = recent_activity(ROOT, limit=8)
if not activity:
    st.caption("아직 활동 내역이 없습니다.")
else:
    for a in activity:
        icon = {"generated": "✅", "cached": "💾", "failed": "⚠️", "processed": "🎚️"}.get(a["status"], "·")
        st.markdown(
            f"{icon} `{a['project']}` · **{a['asset_id']}** · {a['status']} · _{a['when']}_"
        )
