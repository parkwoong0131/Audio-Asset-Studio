"""Review store helpers."""
from __future__ import annotations

from shared.reviews import review_lookup, summarize_reviews, update_review


def test_review_update_and_summary(tmp_path):
    update_review(tmp_path, "job_a", status="approved", favorite=True, note="good")
    lookup = review_lookup(tmp_path)
    assert lookup["job_a"]["status"] == "approved"
    assert lookup["job_a"]["favorite"] is True

    summary = summarize_reviews([{"job_id": "job_a"}, {"job_id": "job_b"}], lookup)
    assert summary["approved"] == 1
    assert summary["favorites"] == 1
    assert summary["pending"] == 1
