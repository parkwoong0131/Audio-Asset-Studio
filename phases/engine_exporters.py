"""엔진별 export 백엔드 모음 — Unity/Addressables/FMOD/Wwise.

런타임 베리에이션(pitch/volume 랜덤 범위)을 카테고리별 프리셋으로 자동 기입.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

log = logging.getLogger(__name__)


# 런타임 베리에이션 프리셋 (세미톤, dB, %)
RUNTIME_VARIATION: dict[str, dict] = {
    "sfx_ui":           {"pitch_st": 0.5, "volume_db": 1.0, "max_poly": 4},
    "sfx_reward":       {"pitch_st": 1.0, "volume_db": 1.5, "max_poly": 4},
    "sfx_impact":       {"pitch_st": 2.0, "volume_db": 3.0, "max_poly": 8},
    "sfx_ambient":      {"pitch_st": 0.2, "volume_db": 1.0, "max_poly": 2},
    "sfx_character":    {"pitch_st": 1.5, "volume_db": 2.0, "max_poly": 4},
    "sfx_notification": {"pitch_st": 0.3, "volume_db": 0.5, "max_poly": 2},
    "bgm_loop":         {"pitch_st": 0.0, "volume_db": 0.0, "max_poly": 1},
    "bgm_stinger":      {"pitch_st": 0.1, "volume_db": 0.5, "max_poly": 2},
    "bgm_adaptive":     {"pitch_st": 0.0, "volume_db": 0.0, "max_poly": 4},
}


def runtime_meta(category: str) -> dict:
    return RUNTIME_VARIATION.get(category, {"pitch_st": 0.0, "volume_db": 0.0, "max_poly": 2})


# ========== Unity + Addressables ==========

UNITY_META_TEMPLATE = """\
fileFormatVersion: 2
guid: {guid}
AudioImporter:
  externalObjects: {{}}
  serializedVersion: 7
  defaultSettings:
    loadType: {load_type}
    sampleRateSetting: 0
    sampleRateOverride: 44100
    compressionFormat: {compression}
    quality: 0.7
    conversionMode: 0
  forceToMono: {force_mono}
  normalize: 0
  preloadAudioData: {preload}
  loadInBackground: {load_bg}
  ambisonic: 0
  3D: 0
  userData: '{user_data}'
  assetBundleName: {bundle}
  assetBundleVariant:
"""


def export_unity(processed: list[dict], manifest: dict, export_dir: Path, addressables: bool = False) -> list[str]:
    import json as _json

    exported: list[str] = []
    assets_meta = manifest.get("assets_meta", {})
    addr_entries: list[dict] = []

    for entry in processed:
        fpath = Path(entry.get("processed") or entry.get("output", ""))
        if not fpath.exists():
            continue
        asset_id = entry["asset_id"]
        meta = assets_meta.get(asset_id, {})
        cat = meta.get("category", "sfx_ui")
        is_sfx = cat.startswith("sfx_")
        subdir = "sfx" if is_sfx else "bgm"

        dest_dir = export_dir / "Assets" / "Audio" / subdir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / fpath.name
        shutil.copy2(fpath, dest)

        user_data = _json.dumps(runtime_meta(cat))
        bundle = f"audio_{cat}" if addressables else ""
        (dest_dir / f"{fpath.name}.meta").write_text(UNITY_META_TEMPLATE.format(
            guid=uuid.uuid4().hex,
            load_type=0 if is_sfx else 1,
            compression=1,
            force_mono=1 if is_sfx else 0,
            preload=1 if is_sfx else 0,
            load_bg=0 if is_sfx else 1,
            user_data=user_data,
            bundle=bundle,
        ))
        exported.append(str(dest))
        if addressables:
            addr_entries.append({
                "address": f"audio/{cat}/{fpath.stem}",
                "group": f"audio_{cat}",
                "path": f"Assets/Audio/{subdir}/{fpath.name}",
                "labels": [cat, "sfx" if is_sfx else "bgm"],
                "runtime": runtime_meta(cat),
            })

    if addressables:
        (export_dir / "addressables_groups.json").write_text(_json.dumps({
            "project": manifest.get("project_id"),
            "entries": addr_entries,
        }, indent=2))
    return exported


# ========== FMOD ==========

def export_fmod(processed: list[dict], manifest: dict, export_dir: Path) -> list[str]:
    """FMOD Studio 프로젝트 느낌의 폴더 + bank 메타(JSON). 실제 .bank 빌드는 FMOD Studio에서."""
    import json as _json

    exported: list[str] = []
    events: list[dict] = []
    assets_meta = manifest.get("assets_meta", {})

    for entry in processed:
        fpath = Path(entry.get("processed") or entry.get("output", ""))
        if not fpath.exists():
            continue
        asset_id = entry["asset_id"]
        meta = assets_meta.get(asset_id, {})
        cat = meta.get("category", "sfx_ui")
        bank = "master" if cat.startswith("bgm_") else cat

        dest_dir = export_dir / "Assets" / bank
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / fpath.name
        shutil.copy2(fpath, dest)
        exported.append(str(dest))

        rv = runtime_meta(cat)
        events.append({
            "event": f"event:/{cat}/{fpath.stem}",
            "bank": bank,
            "asset": f"Assets/{bank}/{fpath.name}",
            "category": cat,
            "loop": meta.get("loop", False),
            "pitch_modulation_st": rv["pitch_st"],
            "volume_modulation_db": rv["volume_db"],
            "max_polyphony": rv["max_poly"],
        })

    (export_dir / "events.json").write_text(_json.dumps({"events": events}, indent=2))
    return exported


# ========== Wwise ==========

WWISE_WORKUNIT = """<?xml version="1.0" encoding="utf-8"?>
<WwiseDocument xmlns:audio="http://www.audiokinetic.com/ak/2023" Type="WorkUnit">
  <WorkUnit Name="{name}" Type="Folder">
    <ChildrenList>{children}
    </ChildrenList>
  </WorkUnit>
</WwiseDocument>
"""


def export_wwise(processed: list[dict], manifest: dict, export_dir: Path) -> list[str]:
    exported: list[str] = []
    assets_meta = manifest.get("assets_meta", {})
    by_cat: dict[str, list[str]] = {}

    originals = export_dir / "Originals" / "SFX"
    bgm_originals = export_dir / "Originals" / "Music"
    originals.mkdir(parents=True, exist_ok=True)
    bgm_originals.mkdir(parents=True, exist_ok=True)

    for entry in processed:
        fpath = Path(entry.get("processed") or entry.get("output", ""))
        if not fpath.exists():
            continue
        asset_id = entry["asset_id"]
        meta = assets_meta.get(asset_id, {})
        cat = meta.get("category", "sfx_ui")
        target = bgm_originals if cat.startswith("bgm_") else originals
        dest = target / fpath.name
        shutil.copy2(fpath, dest)
        exported.append(str(dest))
        by_cat.setdefault(cat, []).append(fpath.stem)

    # 카테고리별 WorkUnit XML
    actor_mixer = export_dir / "Actor-Mixer Hierarchy"
    actor_mixer.mkdir(parents=True, exist_ok=True)
    for cat, names in by_cat.items():
        rv = runtime_meta(cat)
        children = "".join(
            f'\n      <Sound Name="{n}" ShortID="{abs(hash(n)) % (10**10)}" '
            f'PitchRandomizer="{rv["pitch_st"]*100:.0f}" VolumeRandomizer="{rv["volume_db"]:.1f}"/>'
            for n in names
        )
        path = actor_mixer / f"{cat}.wwu"
        path.write_text(WWISE_WORKUNIT.format(name=cat, children=children))
    return exported
