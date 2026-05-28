"""Prompt library ingestion helpers."""
from __future__ import annotations

import json

import shared.prompt_library as prompt_library
from shared.prompt_library import ingest_run


class _FakeLibrary:
    def __init__(self) -> None:
        self.calls = []

    def add(self, **kwargs):
        self.calls.append(kwargs)
        return "ok"


def test_ingest_run_passes_extras(tmp_path):
    report_path = tmp_path / "report.json"
    manifest_path = tmp_path / "manifest.json"
    report_path.write_text(json.dumps({
        "results": [
            {
                "job_id": "job_a",
                "asset_id": "sfx_click",
                "status": "generated",
                "files": ["a.wav"],
                "scores": {"job_a": {"total": 0.9}},
            }
        ]
    }), encoding="utf-8")
    manifest_path.write_text(json.dumps({
        "jobs": [{"job_id": "job_a", "prompt": "click", "model": "audiogen"}],
        "assets_meta": {"sfx_click": {"category": "sfx_ui"}},
    }), encoding="utf-8")

    fake = _FakeLibrary()
    added = ingest_run(fake, report_path, manifest_path, extras={"project": "demo", "source": "test"})

    assert added == 1
    assert fake.calls[0]["extras"] == {"project": "demo", "source": "test"}


def test_prompt_library_status_reports_missing_storage_dep(tmp_path, monkeypatch):
    def fake_dep(module_name: str):
        if module_name == "chromadb":
            return False, "missing chromadb"
        return True, None

    monkeypatch.setattr(prompt_library, "_dependency_status", fake_dep)

    status = prompt_library.prompt_library_status(root=tmp_path)

    assert status["can_open"] is False
    assert status["can_search"] is False
    assert "chromadb" in status["missing"]


def test_prompt_library_status_allows_recent_browse_without_clap(tmp_path, monkeypatch):
    class FakeLibrary:
        def __init__(self, root, collection="prompts"):
            self.root = root
            self.collection = collection

        def count(self):
            return 7

    def fake_dep(module_name: str):
        if module_name == "laion_clap":
            return False, "missing laion_clap"
        return True, None

    monkeypatch.setattr(prompt_library, "_dependency_status", fake_dep)
    monkeypatch.setattr(prompt_library, "PromptLibrary", FakeLibrary)

    status = prompt_library.prompt_library_status(root=tmp_path)

    assert status["can_open"] is True
    assert status["can_search"] is False
    assert status["count"] == 7
    assert "laion-clap" in status["missing"]
