"""Bulk authoring — CSV/XLSX round-trip editor for assets."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dashboard.state import load_project_config, project_dir  # noqa: E402
from shared.asset_sheet import (  # noqa: E402
    apply_rows_to_doc,
    export_sheet,
    import_rows,
    rows_from_assets,
    rows_preview_text,
)
from shared.pipeline_helpers import write_yaml  # noqa: E402
from shared.schemas import validate_audio_input  # noqa: E402

st.set_page_config(page_title="Bulk Authoring", page_icon="🧮", layout="wide")

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

input_path = Path(input_file)
if not input_path.exists():
    st.error(f"Input YAML not found: {input_path}")
    st.stop()

with st.sidebar:
    st.markdown(f"### 🧮 {project_name}")
    st.page_link("app.py", label="Home", icon="🏠")
    st.page_link("pages/1_🎛️_Studio.py", label="Studio", icon="🎛️")
    st.page_link("pages/6_🧪_Review_Cockpit.py", label="Review Cockpit", icon="🧪")
    st.page_link("pages/7_🧵_Queue_Manager.py", label="Queue Manager", icon="🧵")

st.title("Bulk Authoring")
st.caption("CSV/XLSX로 에셋을 대량 편집하고 YAML에 다시 반영합니다.")

doc = yaml.safe_load(input_path.read_text(encoding="utf-8")) or {}
rows = rows_from_assets(doc)
sheet_dir = pdir / "bulk_authoring"
csv_path = sheet_dir / f"{project_name}_assets.csv"
xlsx_path = sheet_dir / f"{project_name}_assets.xlsx"

top = st.columns([1, 1, 2])
if top[0].button("Export CSV", type="primary", use_container_width=True):
    out = export_sheet(doc, csv_path)
    st.success(f"내보냄: {out}")
if top[1].button("Export XLSX", use_container_width=True):
    try:
        out = export_sheet(doc, xlsx_path)
        st.success(f"내보냄: {out}")
    except Exception as e:
        st.error(str(e))
top[2].caption("JSON 컬럼: `layers`, `intensity_layers`, `post_process`, `multiplex`")

st.subheader("Current Asset Sheet")
st.dataframe(rows, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Import Edited Sheet")
uploaded = st.file_uploader("CSV 또는 XLSX 업로드", type=["csv", "xlsx"])

if uploaded is not None:
    uploaded_path = sheet_dir / uploaded.name
    sheet_dir.mkdir(parents=True, exist_ok=True)
    uploaded_path.write_bytes(uploaded.getvalue())
    try:
        imported_rows = import_rows(uploaded_path)
        st.code(rows_preview_text(imported_rows), language="csv")
        if st.button("Apply to YAML", type="primary"):
            updated = apply_rows_to_doc(doc, imported_rows)
            validated = validate_audio_input(updated)
            write_yaml(input_path, validated)
            st.success(f"YAML updated: {input_path}")
            st.session_state[f"input_{project_name}"] = str(input_path)
    except Exception as e:
        st.error(f"Import 실패: {e}")
