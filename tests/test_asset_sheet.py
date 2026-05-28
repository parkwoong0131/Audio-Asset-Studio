"""Bulk authoring sheet helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from shared.asset_sheet import (
    apply_rows_to_doc,
    export_csv,
    export_xlsx,
    import_rows,
    rows_from_assets,
)


def _sample_doc() -> dict:
    return {
        "project": "sheet_test",
        "assets": [
            {
                "asset_id": "sfx_click",
                "category": "sfx_ui",
                "prompt": "bright click",
                "variations": 2,
                "layers": ["impact", "tail"],
                "post_process": ["trim", "normalize"],
            }
        ],
    }


def test_csv_roundtrip(tmp_path):
    doc = _sample_doc()
    path = tmp_path / "assets.csv"
    export_csv(doc, path)

    rows = import_rows(path)
    updated = apply_rows_to_doc(doc, rows)
    assert updated["assets"][0]["asset_id"] == "sfx_click"
    assert updated["assets"][0]["layers"] == ["impact", "tail"]
    assert updated["assets"][0]["post_process"] == ["trim", "normalize"]


def test_rows_from_assets_text_fields():
    rows = rows_from_assets(_sample_doc())
    assert rows[0]["asset_id"] == "sfx_click"
    assert rows[0]["layers"].startswith("[")


def test_xlsx_roundtrip(tmp_path):
    pytest.importorskip("openpyxl")
    doc = _sample_doc()
    path = tmp_path / "assets.xlsx"
    export_xlsx(doc, path)

    rows = import_rows(path)
    updated = apply_rows_to_doc(doc, rows)
    assert updated["assets"][0]["variations"] == 2
