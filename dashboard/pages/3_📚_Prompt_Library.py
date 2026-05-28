"""Prompt Library — 성공한 프롬프트를 검색/복사."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Prompt Library", page_icon="📚", layout="wide")
st.title("📚 Prompt Library")
st.caption("성공 프롬프트를 CLAP 임베딩으로 검색합니다. 비슷한 사운드를 찾고 싶을 때.")

from shared.prompt_library import PromptLibrary, prompt_library_status

status = prompt_library_status()
st.metric("Stored prompts", status["count"] if status["can_open"] else "unavailable")
st.caption(f"Storage: `{status['root']}`")

if not status["can_open"]:
    st.warning("Prompt Library 저장소를 지금은 열 수 없어요.")
    if status.get("missing"):
        st.caption(f"누락 의존성: {', '.join(status['missing'])}")
    if status.get("error"):
        st.caption(f"열기 실패: {status['error']}")
    st.caption("저장소 브라우징은 `chromadb`, 검색/추천과 자동 적재까지 쓰려면 `laion-clap`도 필요해.")
    st.code("pip install -r requirements.txt")
    st.caption("첫 성공 생성 후 자동으로 프롬프트가 쌓여.")
    st.stop()

if not status["can_search"]:
    st.info("저장된 프롬프트 열람은 가능하지만, 검색/추천은 `laion-clap`이 설치되기 전까지 비활성 상태야.")

lib = PromptLibrary()

top = st.columns([4, 1])
q = top[0].text_input("검색어", placeholder="예: 8-bit coin pickup")
cat = top[1].selectbox("카테고리", [
    "", "sfx_ui", "sfx_reward", "sfx_impact", "sfx_ambient",
    "sfx_character", "sfx_notification", "bgm_loop", "bgm_stinger", "bgm_adaptive",
])

if q:
    if not status["can_search"]:
        st.info("검색 기능은 현재 비활성 상태야. `laion-clap` 설치 후 다시 시도해줘.")
    else:
        results = lib.recommend(q, category=cat or None, k=10)
        if not results:
            st.info("일치하는 프롬프트가 없습니다.")
        for r in results:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**{r['prompt']}**")
                    st.caption(f"{r.get('category', '?')} · {r.get('model', '?')} · sim={r['similarity']:.2f} · score={r.get('score', 0):.2f}")
                    ap = r.get("audio_path")
                    if ap and Path(ap).exists():
                        st.audio(str(ap))
                with c2:
                    if st.button("📋 Copy", key=f"copy_{r['id']}"):
                        st.code(r["prompt"])
                        st.caption("↑ 복사하세요")
else:
    st.caption("검색어를 입력하거나 최근 적재된 프롬프트를 확인하세요.")
    for r in lib.recent(limit=12):
        with st.container(border=True):
            st.markdown(f"**{r['prompt']}**")
            meta = " · ".join(filter(None, [
                r.get("category", ""),
                r.get("model", ""),
                r.get("source", ""),
                r.get("project", ""),
            ]))
            if meta:
                st.caption(meta)
