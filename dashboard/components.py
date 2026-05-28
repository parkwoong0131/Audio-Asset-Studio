"""재사용 UI 컴포넌트 — 에셋 카드 / A/B 뷰어 / 파형 플롯 / 프롬프트 추천."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import streamlit as st


def wave_plot(audio_path: Path, compact: bool = False) -> None:
    try:
        import librosa
        import matplotlib.pyplot as plt
    except ImportError:
        st.caption("(librosa/matplotlib 미설치)")
        return
    try:
        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    except Exception as e:
        st.caption(f"(로드 실패: {e})")
        return
    if compact:
        fig, ax = plt.subplots(1, 1, figsize=(6, 0.8))
        ax.plot(np.linspace(0, len(y) / sr, len(y)), y, linewidth=0.4, color="#4a8df6")
        ax.axis("off")
    else:
        fig, axes = plt.subplots(2, 1, figsize=(7, 2.4))
        axes[0].plot(np.linspace(0, len(y) / sr, len(y)), y, linewidth=0.5, color="#4a8df6")
        axes[0].set_title("Waveform", fontsize=9)
        axes[0].set_xlim(0, len(y) / sr)
        axes[0].tick_params(labelsize=7)
        D = librosa.amplitude_to_db(np.abs(librosa.stft(y)), ref=np.max)
        axes[1].imshow(D, origin="lower", aspect="auto", cmap="magma")
        axes[1].set_title("Spectrogram", fontsize=9)
        axes[1].tick_params(labelsize=7)
    fig.tight_layout()
    st.pyplot(fig, clear_figure=True)


def status_badge(status: str) -> str:
    return {
        "generated": "🟢 generated",
        "cached":    "💾 cached",
        "processed": "🎚️ processed",
        "failed":    "🔴 failed",
    }.get(status, f"· {status}")


def warning_badges(entry: dict) -> list[str]:
    badges: list[str] = []
    tags = entry.get("_tags") or {}
    if tags and tags.get("passed") is False:
        badges.append("⚠️ tag mismatch")
    if entry.get("status") == "failed":
        badges.append("🔴 failed")
    if (entry.get("wall_sec") or 0) > 60:
        badges.append(f"⏱ {entry['wall_sec']:.0f}s")
    return badges


def asset_card(entry: dict, post_lookup: dict[str, str], on_retake) -> None:
    asset_id = entry.get("asset_id", "?")
    job_id = entry.get("job_id", "?")
    status = entry.get("status", "?")
    with st.container(border=True):
        top_l, top_r = st.columns([4, 1])
        with top_l:
            st.markdown(f"**{asset_id}** · `{job_id}`")
            st.caption(status_badge(status))
            for b in warning_badges(entry):
                st.caption(b)
        with top_r:
            if st.button("🔁 Retake", key=f"retake_{job_id}"):
                on_retake(asset_id)

        processed = post_lookup.get(job_id)
        audio_path = Path(processed) if processed else (
            Path(entry["files"][0]) if entry.get("files") else None
        )
        if audio_path and audio_path.exists():
            st.audio(str(audio_path))
            with st.expander("Waveform · Spectrogram", expanded=False):
                wave_plot(audio_path)
        else:
            st.caption("(오디오 파일 없음)")

        if entry.get("variant") in ("multiplex", "seed_farm"):
            with st.expander(f"🅰️🅱️ Candidates ({entry['variant']})", expanded=False):
                ab_viewer(entry)


def ab_viewer(entry: dict) -> None:
    """multiplex/seed_farm 후보를 수동 A/B."""
    cands = entry.get("candidates") or []
    picked = entry.get("picked_job_id")
    if not cands:
        st.caption("후보 없음")
        return
    for c in cands:
        files = c.get("files") or []
        label = c.get("model") or c.get("job_id", "?")
        is_pick = c.get("job_id") == picked
        suffix = " · 🎯 picked" if is_pick else ""
        st.markdown(f"**{label}**  score={c.get('score', 0):.3f}{suffix}")
        for f in files:
            fp = Path(f)
            if fp.exists():
                st.audio(str(fp))


def prompt_suggester(query: str, category: str | None, k: int = 5) -> list[dict]:
    """프롬프트 라이브러리에서 유사 프롬프트 top-k."""
    try:
        from shared.prompt_library import PromptLibrary, prompt_library_status

        status = prompt_library_status()
        if not status.get("can_search"):
            missing = ", ".join(status.get("missing") or [])
            st.caption(f"(prompt library 검색 비활성: {missing or 'laion-clap/chromadb 확인 필요'})")
            return []
        lib = PromptLibrary()
        return lib.recommend(query, category=category, k=k)
    except Exception as e:
        st.caption(f"(prompt library 미사용: {e})")
        return []


def knobs_sliders(asset_id: str, category: str, saved: dict[str, int] | None = None) -> dict[str, int]:
    """카테고리별 허용 축만 슬라이더로 노출."""
    from shared.presets import axes_for_category, default_knobs

    axes = axes_for_category(category)
    if not axes:
        return {}
    defaults = default_knobs(category)
    values: dict[str, int] = {}
    saved = saved or {}
    cols = st.columns(len(axes))
    for col, axis in zip(cols, axes):
        with col:
            values[axis] = st.slider(
                axis.capitalize(),
                min_value=0, max_value=10,
                value=int(saved.get(axis, defaults.get(axis, 5))),
                key=f"knob_{asset_id}_{category}_{axis}",
            )
    return values
