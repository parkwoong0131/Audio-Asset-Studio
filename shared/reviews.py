"""Persistent review records for generated assets."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def reviews_path(project_dir: Path) -> Path:
    return project_dir / "reviews.json"


def load_reviews(project_dir: Path) -> dict:
    path = reviews_path(project_dir)
    if not path.exists():
        return {"jobs": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"jobs": {}}
    if not isinstance(data, dict):
        return {"jobs": {}}
    data.setdefault("jobs", {})
    return data


def save_reviews(project_dir: Path, data: dict) -> Path:
    path = reviews_path(project_dir)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def update_review(project_dir: Path, job_id: str, **patch: Any) -> dict:
    data = load_reviews(project_dir)
    jobs = data.setdefault("jobs", {})
    review = dict(jobs.get(job_id, {}))
    for key, value in patch.items():
        if value is not None:
            review[key] = value
    review["updated_at"] = datetime.now(timezone.utc).isoformat()
    jobs[job_id] = review
    save_reviews(project_dir, data)
    return review


def review_lookup(project_dir: Path) -> dict[str, dict]:
    return load_reviews(project_dir).get("jobs", {})


def summarize_reviews(entries: list[dict], lookup: dict[str, dict]) -> dict[str, int]:
    summary = {"approved": 0, "rejected": 0, "favorites": 0, "pending": 0}
    for entry in entries:
        review = lookup.get(entry.get("job_id", ""), {})
        status = review.get("status")
        if review.get("favorite"):
            summary["favorites"] += 1
        if status == "approved":
            summary["approved"] += 1
        elif status == "rejected":
            summary["rejected"] += 1
        else:
            summary["pending"] += 1
    return summary
