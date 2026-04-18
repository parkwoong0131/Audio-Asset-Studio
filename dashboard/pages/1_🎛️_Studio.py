"""Studio — 프로젝트 편집기. 에셋 그리드 + 인라인 편집 + 재생성."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dashboard.components import asset_card, knobs_sliders, prompt_suggester  # noqa: E402
from dashboard.runner import format_cmd, run_with_log  # noqa: E402
from dashboard.state import (  # noqa: E402
    daemon_badge, load_manifest, load_post_report, load_report, project_dir,
)

st.set_page_config(page_title="Studio", page_icon="🎛️", layout="wide")

project_name = st.session_state.get("active_project")
if not project_name:
    st.info("Home에서 프로젝트를 선택하세요.")
    st.page_link("app.py", label="← Home", icon="🏠")
    st.stop()

pdir = project_dir(ROOT, project_name)
input_guess = st.session_state.get(f"input_{project_name}") or str(ROOT / "config" / "examples" / "clicker_game.yaml")

# ----- sidebar -----
with st.sidebar:
    st.markdown(f"### 🎛️ {project_name}")
    st.markdown(daemon_badge())
    st.divider()
    st.markdown("**Run controls**")
    backend = st.selectbox("Backend", ["local", "warm", "runpod"], key="run_backend")
    engine = st.selectbox("Engine", ["unity", "unity_addr", "fmod", "wwise"], key="run_engine")
    loudness = st.selectbox("Loudness", ["mobile (-14)", "console (-16)", "pc (-18)", "broadcast (-23)"])
    loudness_val = {"mobile": -14, "console": -16, "pc": -18, "broadcast": -23}[loudness.split()[0]]
    st.divider()
    st.page_link("app.py", label="← All projects", icon="🏠")

# ----- header -----
col_l, col_r = st.columns([3, 2])
with col_l:
    st.title(project_name)
    st.caption(f"📁 `{pdir}`")
with col_r:
    st.text_input("Input YAML", value=input_guess, key=f"input_{project_name}")
    input_file = st.session_state[f"input_{project_name}"]

# ----- primary actions -----
st.divider()
bar = st.columns([1, 1, 1, 3])
run_full = bar[0].button("▶️ Run full pipeline", type="primary", use_container_width=True)
run_post = bar[1].button("🎚️ Re-run post only (5,6)", use_container_width=True)
run_force = bar[2].button("🔁 Regenerate all (force)", use_container_width=True)

log_area = st.empty()

def _do_run(**kwargs):
    st.toast(f"Running: {kwargs.get('phases') or 'all'}", icon="▶️")
    lines: list[str] = []
    def _cb(line: str):
        lines.append(line)
        log_area.code("\n".join(lines[-30:]), language="log")
    rc = run_with_log(ROOT, _cb, project=project_name, input_file=input_file,
                      backend=backend, engine=engine, loudness_target=loudness_val, **kwargs)
    if rc == 0:
        st.success("완료")
    else:
        st.error(f"종료 코드 {rc} — 로그 확인")
    time.sleep(0.2)
    st.rerun()

if run_full:
    _do_run()
if run_post:
    _do_run(phases="5,6")
if run_force:
    _do_run(force=True)

# ----- load state -----
manifest = load_manifest(pdir)
report = load_report(pdir)
post_report = load_post_report(pdir)

if not manifest:
    st.warning("아직 manifest가 없습니다. 먼저 full pipeline을 실행하세요.")
    st.stop()

# ----- KPIs -----
if report:
    stats = {"generated": 0, "cached": 0, "failed": 0}
    for r in report.get("results", []):
        stats[r.get("status", "?")] = stats.get(r.get("status", "?"), 0) + 1
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Generated", stats["generated"])
    k2.metric("Cached", stats["cached"])
    k3.metric("Failed", stats["failed"])
    bf = pdir / "budget.json"
    if bf.exists():
        b = json.loads(bf.read_text())
        k4.metric("Spent USD", f"${b.get('spent_usd', 0):.4f}")

# ----- asset grid -----
st.divider()
tab_assets, tab_edit, tab_raw = st.tabs(["🎧 Assets", "✏️ Edit prompts & knobs", "📄 Raw JSON"])

with tab_assets:
    if not report:
        st.info("아직 생성 결과가 없습니다.")
    else:
        post_lookup: dict[str, str] = {}
        for r in (post_report or {}).get("results", []):
            if r.get("status") == "processed":
                post_lookup[r["job_id"]] = r["processed"]

        # 필터
        f1, f2 = st.columns([2, 3])
        only_failed = f1.checkbox("실패/경고만", value=False)
        query = f2.text_input("asset_id 검색", value="")

        def _on_retake(asset_id: str) -> None:
            _do_run(phases="4,5,6", only=[asset_id], force=True)

        items = report.get("results", [])
        if only_failed:
            items = [r for r in items if r.get("status") == "failed" or (r.get("_tags") or {}).get("passed") is False]
        if query:
            items = [r for r in items if query.lower() in r.get("asset_id", "").lower()]

        grid = st.columns(2)
        for i, entry in enumerate(items):
            with grid[i % 2]:
                asset_card(entry, post_lookup, on_retake=_on_retake)

with tab_edit:
    st.caption("프롬프트/슬라이더를 수정하면 input YAML이 업데이트됩니다.")
    try:
        src = yaml.safe_load(Path(input_file).read_text())
    except Exception as e:
        st.error(f"YAML 로드 실패: {e}")
        st.stop()

    changed = False
    for asset in src.get("assets", []):
        aid = asset.get("asset_id", "?")
        cat = asset.get("category", "")
        with st.expander(f"{aid}  ·  {cat}", expanded=False):
            new_prompt = st.text_area(
                "Prompt", value=asset.get("prompt", ""), key=f"prompt_{aid}", height=80,
            )
            if new_prompt != asset.get("prompt"):
                asset["prompt"] = new_prompt
                changed = True

            # 프롬프트 추천
            if new_prompt and st.button("🔎 유사 프롬프트 찾기", key=f"sug_{aid}"):
                suggs = prompt_suggester(new_prompt, cat, k=5)
                if suggs:
                    for s in suggs:
                        st.caption(f"· ({s['similarity']:.2f}) {s['prompt']}")
                else:
                    st.caption("라이브러리에 비슷한 게 없습니다.")

            st.markdown("**Sound design knobs**")
            saved = asset.get("_knobs") or {}
            new_knobs = knobs_sliders(cat, saved)
            if new_knobs != saved:
                asset["_knobs"] = new_knobs
                changed = True

            cols = st.columns(3)
            var = cols[0].number_input("Variations", 1, 16, int(asset.get("variations", 1)), key=f"var_{aid}")
            if var != asset.get("variations", 1):
                asset["variations"] = int(var); changed = True
            farm = cols[1].number_input("Seed farming", 0, 12, int(asset.get("seed_farming", 0)), key=f"farm_{aid}")
            if farm != asset.get("seed_farming", 0):
                if farm: asset["seed_farming"] = int(farm)
                else: asset.pop("seed_farming", None)
                changed = True
            mux_str = cols[2].text_input(
                "Multiplex models (쉼표)", value=",".join(asset.get("multiplex") or []), key=f"mux_{aid}",
            )
            mux_list = [m.strip() for m in mux_str.split(",") if m.strip()]
            if mux_list != (asset.get("multiplex") or []):
                if mux_list: asset["multiplex"] = mux_list
                else: asset.pop("multiplex", None)
                changed = True

    if changed and st.button("💾 Save YAML", type="primary"):
        # preset knobs → prompt/cfg/layers 반영
        from shared.presets import apply_to_asset
        for asset in src.get("assets", []):
            if asset.get("_knobs"):
                applied = apply_to_asset({**asset}, asset["_knobs"])
                # 사용자가 편집한 prompt는 유지, knobs는 추가 cfg 등만 반영
                asset["cfg_scale"] = applied.get("cfg_scale")
                if applied.get("layers") and "layers" not in asset:
                    asset["layers"] = applied["layers"]
        Path(input_file).write_text(yaml.safe_dump(src, allow_unicode=True, sort_keys=False))
        st.success("저장됨 — 이제 ▶️ Run으로 반영")
        st.rerun()

with tab_raw:
    if report:
        st.json(report)
