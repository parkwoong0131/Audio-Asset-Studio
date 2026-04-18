"""Phase 6: 엔진별 오디오 폴더 + 설정 임포트.

지원 엔진:
    unity        — Assets/Audio + .meta (+ Addressables groups)
    unity_addr   — Unity + Addressables enabled
    fmod         — FMOD Studio 폴더 + events.json
    wwise        — Wwise WorkUnit XML + Originals/
"""
from __future__ import annotations

import logging
from pathlib import Path

from shared.pipeline_helpers import read_json, write_json

from .engine_exporters import export_fmod, export_unity, export_wwise

log = logging.getLogger(__name__)


def run(
    post_report_path: Path,
    manifest_path: Path,
    out_dir: Path,
    engine: str = "unity",
) -> Path:
    report = read_json(post_report_path)
    manifest = read_json(manifest_path)

    processed_files = [
        r for r in report.get("results", [])
        if r.get("status") == "processed"
    ]
    processed_files.extend(report.get("layer_mixes", []))

    engine = engine.lower()
    export_dir = out_dir / f"export_{engine}"
    export_dir.mkdir(parents=True, exist_ok=True)

    if engine == "unity":
        exported = export_unity(processed_files, manifest, export_dir, addressables=False)
    elif engine in ("unity_addr", "addressables"):
        exported = export_unity(processed_files, manifest, export_dir, addressables=True)
    elif engine == "fmod":
        exported = export_fmod(processed_files, manifest, export_dir)
    elif engine == "wwise":
        exported = export_wwise(processed_files, manifest, export_dir)
    else:
        raise ValueError(f"Unsupported engine: {engine}")

    out = out_dir / "phase6_engine_import_report.json"
    write_json(out, {
        "project_id": report.get("project_id", ""),
        "engine": engine,
        "exported_files": exported,
        "total": len(exported),
    })
    log.info("Phase 6 done: %d files → %s (%s)", len(exported), export_dir, engine)
    return out
