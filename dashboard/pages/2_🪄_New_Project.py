"""3-step 프로젝트 위저드 — 장르 / 레퍼런스 / 플랫폼."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="New Project", page_icon="🪄", layout="centered")
st.title("🪄 New Project")
st.caption("3단계로 끝. 기본값만 잡아놔도 바로 생성 가능합니다.")

if "wiz" not in st.session_state:
    st.session_state["wiz"] = {"step": 1}
wiz = st.session_state["wiz"]


TEMPLATES: dict[str, dict] = {
    "clicker": {
        "label": "🍪 Clicker / Idle",
        "palette": "casual_fantasy",
        "reference": "cookie-clicker",
        "assets": [
            {"asset_id": "sfx_click", "category": "sfx_ui", "prompt": "satisfying soft click, bouncy"},
            {"asset_id": "sfx_coin", "category": "sfx_reward", "prompt": "coin pickup chime, metallic sparkle"},
            {"asset_id": "sfx_levelup", "category": "sfx_reward", "prompt": "positive level up fanfare"},
            {"asset_id": "bgm_main", "category": "bgm_loop", "duration_ms": 60000, "prompt": "cheerful fantasy idle loop, bouncy"},
        ],
    },
    "roguelike": {
        "label": "⚔️ Pixel Roguelike",
        "palette": "pixel_retro",
        "reference": "vampire-survivors",
        "assets": [
            {"asset_id": "sfx_hit", "category": "sfx_impact", "prompt": "chiptune sword hit, 8-bit", "layers": ["impact", "sweetener", "tail"]},
            {"asset_id": "sfx_coin", "category": "sfx_reward", "prompt": "8-bit coin pickup"},
            {"asset_id": "sfx_hurt", "category": "sfx_character", "prompt": "8-bit character hurt"},
            {"asset_id": "bgm_combat", "category": "bgm_loop", "duration_ms": 45000, "prompt": "driving chiptune battle loop"},
        ],
    },
    "puzzle": {
        "label": "🧩 Minimalist Puzzle",
        "palette": "minimalist_zen",
        "reference": "2048",
        "assets": [
            {"asset_id": "sfx_tile", "category": "sfx_ui", "prompt": "soft tile slide, clean sine"},
            {"asset_id": "sfx_combine", "category": "sfx_reward", "prompt": "minimal reward chime"},
            {"asset_id": "bgm_ambient", "category": "bgm_loop", "duration_ms": 90000, "prompt": "calm minimal ambient loop"},
        ],
    },
}


# ----- Step 1 — identity & template -----
if wiz["step"] == 1:
    st.subheader("1 / 3 — 프로젝트 기본")
    wiz["project_id"] = st.text_input(
        "프로젝트 ID (영문 소문자, 숫자, _)", value=wiz.get("project_id", "my_game"),
    )
    wiz["template"] = st.radio(
        "템플릿", list(TEMPLATES), format_func=lambda k: TEMPLATES[k]["label"],
        horizontal=True, key="wiz_template",
    )
    st.caption(f"레퍼런스: **{TEMPLATES[wiz['template']]['reference']}** · 팔레트: **{TEMPLATES[wiz['template']]['palette']}**")

    c1, c2 = st.columns(2)
    if c1.button("← Home", use_container_width=True):
        st.switch_page("app.py")
    if c2.button("Next →", type="primary", use_container_width=True):
        if not re.match(r"^[a-z0-9_]+$", wiz["project_id"]):
            st.error("프로젝트 ID는 영문 소문자/숫자/언더스코어만 가능")
        else:
            wiz["step"] = 2; st.rerun()

# ----- Step 2 — platform & loudness -----
elif wiz["step"] == 2:
    st.subheader("2 / 3 — 플랫폼")
    wiz["engine"] = st.radio(
        "게임 엔진",
        ["unity", "unity_addr", "fmod", "wwise"],
        format_func=lambda k: {
            "unity": "Unity", "unity_addr": "Unity + Addressables",
            "fmod": "FMOD Studio", "wwise": "Wwise",
        }[k], horizontal=True,
    )
    wiz["platform"] = st.radio(
        "라우드니스 타겟",
        ["mobile", "console", "pc", "broadcast"],
        format_func=lambda k: {
            "mobile": "📱 Mobile (-14 LUFS)", "console": "🎮 Console (-16 LUFS)",
            "pc": "💻 PC (-18 LUFS)", "broadcast": "📺 Broadcast (-23 LUFS)",
        }[k], horizontal=True,
    )
    c1, c2 = st.columns(2)
    if c1.button("← Back", use_container_width=True):
        wiz["step"] = 1; st.rerun()
    if c2.button("Next →", type="primary", use_container_width=True):
        wiz["step"] = 3; st.rerun()

# ----- Step 3 — confirm & create -----
elif wiz["step"] == 3:
    st.subheader("3 / 3 — 확인")
    tmpl = TEMPLATES[wiz["template"]]
    payload = {
        "project": wiz["project_id"],
        "audio_palette": {"genre": tmpl["palette"]},
        "assets": tmpl["assets"],
    }
    st.code(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), language="yaml")
    st.caption(f"엔진: **{wiz['engine']}**  ·  라우드니스: **{wiz['platform']}**")

    c1, c2 = st.columns(2)
    if c1.button("← Back", use_container_width=True):
        wiz["step"] = 2; st.rerun()
    if c2.button("🎉 Create project", type="primary", use_container_width=True):
        input_dir = ROOT / "config" / "projects"
        input_dir.mkdir(parents=True, exist_ok=True)
        input_path = input_dir / f"{wiz['project_id']}.yaml"
        input_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))

        # 프로젝트 출력 디렉토리 + 메타 저장
        out_dir = ROOT / "output" / wiz["project_id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        import json as _json
        (out_dir / "project.json").write_text(_json.dumps({
            "template": wiz["template"], "engine": wiz["engine"],
            "platform": wiz["platform"], "input": str(input_path),
        }, indent=2))

        st.session_state["active_project"] = wiz["project_id"]
        st.session_state[f"input_{wiz['project_id']}"] = str(input_path)
        st.session_state["wiz"] = {"step": 1}
        st.success(f"생성됨: {input_path}")
        st.switch_page("pages/1_🎛️_Studio.py")
