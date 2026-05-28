"""프롬프트 라이브러리 — 성공 프롬프트 CLAP 임베딩 저장/추천.

ChromaDB 사용. 저장 위치 기본: ~/.audio_asset_studio/prompt_library/
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_ROOT = Path(os.environ.get(
    "PROMPT_LIB_ROOT",
    str(Path.home() / ".audio_asset_studio" / "prompt_library"),
))


def _dependency_status(module_name: str) -> tuple[bool, str | None]:
    try:
        __import__(module_name)
        return True, None
    except Exception as exc:
        return False, str(exc)


def prompt_library_status(root: Path = DEFAULT_ROOT) -> dict[str, Any]:
    chromadb_ok, chromadb_error = _dependency_status("chromadb")
    clap_ok, clap_error = _dependency_status("laion_clap")
    status: dict[str, Any] = {
        "root": str(root),
        "count": 0,
        "can_open": chromadb_ok,
        "can_search": chromadb_ok and clap_ok,
        "can_ingest": chromadb_ok and clap_ok,
        "missing": [],
        "error": None,
        "packages": {
            "chromadb": {"ok": chromadb_ok, "error": chromadb_error},
            "laion-clap": {"ok": clap_ok, "error": clap_error},
        },
    }
    for name, info in status["packages"].items():
        if not info["ok"]:
            status["missing"].append(name)
    if not status["can_open"]:
        return status
    try:
        library = PromptLibrary(root=root)
        status["count"] = library.count()
    except Exception as exc:
        status["can_open"] = False
        status["can_search"] = False
        status["can_ingest"] = False
        status["error"] = str(exc)
    return status


class PromptLibrary:
    def __init__(self, root: Path = DEFAULT_ROOT, collection: str = "prompts") -> None:
        root.mkdir(parents=True, exist_ok=True)
        import chromadb

        self.root = root
        self.client = chromadb.PersistentClient(path=str(root))
        self.col = self.client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        return int(self.col.count())

    def _embed(self, text: str) -> list[float]:
        from .scoring import clap_text_embed

        return clap_text_embed([text])[0].tolist()

    def add(
        self,
        prompt: str,
        category: str,
        model: str,
        score: float,
        audio_path: str | None = None,
        extras: dict[str, Any] | None = None,
    ) -> str:
        import hashlib

        pid = hashlib.sha1(f"{prompt}|{model}|{category}".encode()).hexdigest()[:16]
        meta = {
            "category": category,
            "model": model,
            "score": float(score),
            "audio_path": audio_path or "",
        }
        if extras:
            meta.update({k: str(v) for k, v in extras.items()})
        self.col.upsert(
            ids=[pid],
            documents=[prompt],
            embeddings=[self._embed(prompt)],
            metadatas=[meta],
        )
        return pid

    def recommend(
        self,
        query: str,
        category: str | None = None,
        k: int = 5,
    ) -> list[dict]:
        where = {"category": category} if category else None
        r = self.col.query(
            query_embeddings=[self._embed(query)],
            n_results=k,
            where=where,
        )
        out: list[dict] = []
        if not r.get("ids") or not r["ids"]:
            return out
        for pid, doc, meta, dist in zip(
            r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0],
        ):
            out.append({
                "id": pid,
                "prompt": doc,
                "similarity": 1.0 - float(dist),
                **(meta or {}),
            })
        return out

    def recent(self, limit: int = 20) -> list[dict]:
        r = self.col.get(limit=limit, include=["documents", "metadatas"])
        out: list[dict] = []
        for pid, doc, meta in zip(
            r.get("ids", []),
            r.get("documents", []),
            r.get("metadatas", []),
        ):
            out.append({"id": pid, "prompt": doc, **(meta or {})})
        return out


def ingest_run(
    library: PromptLibrary,
    report_path: Path,
    manifest_path: Path,
    min_score: float = 0.55,
    *,
    extras: dict[str, Any] | None = None,
) -> int:
    """phase4 report + manifest 읽어서 점수 통과한 것만 라이브러리에 등록."""
    import json

    report = json.loads(Path(report_path).read_text())
    manifest = json.loads(Path(manifest_path).read_text())
    jobs_by_id = {j["job_id"]: j for j in manifest["jobs"]}
    assets_meta = manifest.get("assets_meta", {})

    added = 0
    for r in report.get("results", []):
        if r.get("status") != "generated":
            continue
        job = jobs_by_id.get(r["job_id"])
        if not job:
            continue
        score = (r.get("scores", {}) or {}).get(r["job_id"], {}).get("total", 0.0)
        if score < min_score and r.get("variant") not in ("seed_farm", "multiplex"):
            continue
        cat = assets_meta.get(r["asset_id"], {}).get("category", "")
        files = r.get("files") or []
        library.add(
            prompt=job["prompt"],
            category=cat,
            model=job["model"],
            score=score or 1.0,
            audio_path=files[0] if files else None,
            extras=extras,
        )
        added += 1
    return added


def safe_ingest_run(
    report_path: Path,
    manifest_path: Path,
    *,
    min_score: float = 0.55,
    extras: dict[str, Any] | None = None,
) -> int:
    try:
        library = PromptLibrary()
        return ingest_run(library, report_path, manifest_path, min_score=min_score, extras=extras)
    except Exception as exc:
        log.info("Prompt library ingest skipped: %s", exc)
        return 0


def safe_add_prompt(
    *,
    prompt: str,
    category: str,
    model: str,
    score: float,
    audio_path: str | None = None,
    extras: dict[str, Any] | None = None,
) -> bool:
    try:
        library = PromptLibrary()
        library.add(
            prompt=prompt,
            category=category,
            model=model,
            score=score,
            audio_path=audio_path,
            extras=extras,
        )
        return True
    except Exception as exc:
        log.info("Prompt library add skipped: %s", exc)
        return False
