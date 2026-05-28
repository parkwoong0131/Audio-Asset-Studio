"""Review cockpit for generated assets."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dashboard.components import ab_viewer, warning_badges  # noqa: E402
from dashboard.state import load_manifest, load_post_report, load_project_config, load_report, project_dir  # noqa: E402
from shared.prompt_library import safe_add_prompt  # noqa: E402
from shared.reviews import review_lookup, summarize_reviews, update_review  # noqa: E402

st.set_page_config(page_title="Review Cockpit", page_icon="🧪", layout="wide")

project_name = st.session_state.get("active_project")
if not project_name:
    st.info("Home에서 프로젝트를 선택하세요.")
    st.page_link("app.py", label="← Home", icon="🏠")
    st.stop()

pdir = project_dir(ROOT, project_name)
project_cfg = load_project_config(pdir)
manifest = load_manifest(pdir)
report = load_report(pdir)
post_report = load_post_report(pdir)
reviews = review_lookup(pdir)

if not manifest or not report:
    st.warning("리뷰할 생성 결과가 없습니다. 먼저 pipeline을 실행하세요.")
    st.stop()

jobs_by_id = {job["job_id"]: job for job in manifest.get("jobs", [])}
processed_by_job = {
    row["job_id"]: row
    for row in (post_report or {}).get("results", [])
    if row.get("status") == "processed"
}

entries: list[dict] = []
for row in report.get("results", []):
    processed = processed_by_job.get(row.get("job_id"))
    merged = dict(row)
    if processed:
        merged["processed"] = processed.get("processed")
        merged["_tags"] = processed.get("_tags")
        merged["_stems"] = processed.get("_stems")
    entries.append(merged)

with st.sidebar:
    st.markdown(f"### 🧪 {project_name}")
    st.page_link("app.py", label="Home", icon="🏠")
    st.page_link("pages/1_🎛️_Studio.py", label="Studio", icon="🎛️")
    st.page_link("pages/5_🧮_Bulk_Authoring.py", label="Bulk Authoring", icon="🧮")
    st.page_link("pages/7_🧵_Queue_Manager.py", label="Queue Manager", icon="🧵")

st.title("Review Cockpit")
st.caption("결과를 빠르게 승인/반려/즐겨찾기하고, 좋은 프롬프트를 축적합니다.")

summary = summarize_reviews(entries, reviews)
s1, s2, s3, s4 = st.columns(4)
s1.metric("Pending", summary["pending"])
s2.metric("Approved", summary["approved"])
s3.metric("Rejected", summary["rejected"])
s4.metric("Favorites", summary["favorites"])

f1, f2, f3 = st.columns([1, 1, 2])
review_filter = f1.selectbox("Review", ["all", "pending", "approved", "rejected", "favorites"])
status_filter = f2.selectbox("Status", ["all", "generated", "cached", "failed"])
query = f3.text_input("Search asset/job", value="")

filtered = entries
if review_filter == "pending":
    filtered = [e for e in filtered if reviews.get(e.get("job_id", ""), {}).get("status") not in {"approved", "rejected"}]
elif review_filter == "approved":
    filtered = [e for e in filtered if reviews.get(e.get("job_id", ""), {}).get("status") == "approved"]
elif review_filter == "rejected":
    filtered = [e for e in filtered if reviews.get(e.get("job_id", ""), {}).get("status") == "rejected"]
elif review_filter == "favorites":
    filtered = [e for e in filtered if reviews.get(e.get("job_id", ""), {}).get("favorite")]

if status_filter != "all":
    filtered = [e for e in filtered if e.get("status") == status_filter]
if query:
    needle = query.lower()
    filtered = [e for e in filtered if needle in e.get("asset_id", "").lower() or needle in e.get("job_id", "").lower()]

for entry in filtered:
    job_id = entry.get("job_id", "?")
    job = jobs_by_id.get(job_id, {})
    review = reviews.get(job_id, {})
    audio_path = entry.get("processed") or ((entry.get("files") or [None])[0])

    with st.container(border=True):
        head_l, head_r = st.columns([4, 2])
        with head_l:
            st.markdown(f"### {entry.get('asset_id', '?')} · `{job_id}`")
            st.caption(f"status={entry.get('status', '?')} · model={job.get('model', '?')}")
            for badge in warning_badges(entry):
                st.caption(badge)
            if job.get("prompt"):
                st.code(job["prompt"], language="text")
        with head_r:
            status = review.get("status", "pending")
            favorite = bool(review.get("favorite"))
            st.caption(f"Review: **{status}**")
            st.caption(f"Favorite: {'yes' if favorite else 'no'}")

        if audio_path and Path(audio_path).exists():
            st.audio(str(audio_path))

        if entry.get("variant") in {"multiplex", "seed_farm"}:
            with st.expander("Candidates", expanded=False):
                ab_viewer(entry)

        action_cols = st.columns([1, 1, 1, 3])
        if action_cols[0].button("Approve", key=f"approve_{job_id}", use_container_width=True):
            update_review(pdir, job_id, status="approved", favorite=review.get("favorite", False))
            safe_add_prompt(
                prompt=job.get("prompt", ""),
                category=manifest.get("assets_meta", {}).get(entry.get("asset_id", ""), {}).get("category", ""),
                model=job.get("model", "unknown"),
                score=float(review.get("score") or entry.get("score") or 1.0),
                audio_path=str(audio_path) if audio_path else None,
                extras={"project": project_name, "job_id": job_id, "source": "review_approved"},
            )
            st.rerun()
        if action_cols[1].button("Reject", key=f"reject_{job_id}", use_container_width=True):
            update_review(pdir, job_id, status="rejected", favorite=review.get("favorite", False))
            st.rerun()
        favorite_label = "Unfavorite" if review.get("favorite") else "Favorite"
        if action_cols[2].button(favorite_label, key=f"favorite_{job_id}", use_container_width=True):
            next_favorite = not review.get("favorite", False)
            update_review(pdir, job_id, status=review.get("status", "pending"), favorite=next_favorite)
            if next_favorite:
                safe_add_prompt(
                    prompt=job.get("prompt", ""),
                    category=manifest.get("assets_meta", {}).get(entry.get("asset_id", ""), {}).get("category", ""),
                    model=job.get("model", "unknown"),
                    score=float(entry.get("score") or 1.0),
                    audio_path=str(audio_path) if audio_path else None,
                    extras={"project": project_name, "job_id": job_id, "source": "review_favorite"},
                )
            st.rerun()

        note_key = f"review_note_{job_id}"
        st.text_input("Review note", value=review.get("note", ""), key=note_key)
        if st.button("Save note", key=f"save_note_{job_id}"):
            update_review(
                pdir,
                job_id,
                status=review.get("status", "pending"),
                favorite=review.get("favorite", False),
                note=st.session_state[note_key],
            )
            st.rerun()
