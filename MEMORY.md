# Audio Asset Studio Memory

## Productivity Surfaces
- `dashboard/pages/5_🧮_Bulk_Authoring.py`: CSV/XLSX bulk authoring page.
- `dashboard/pages/6_🧪_Review_Cockpit.py`: approve/reject/favorite review flow for generated assets.
- `dashboard/pages/7_🧵_Queue_Manager.py`: file-backed background queue manager.

## Queue Runtime
- Queue state lives at `output/<project>/job_queue.json`.
- Queue writes are guarded by `job_queue.lock` and atomic temp-file replaces.
- Worker script is `scripts/queue_worker.py`.
- Worker log lives at `output/<project>/queue_worker.log`.
- Per-job logs live under `output/<project>/queue_logs/`.
- Worker state now tracks `current_run_pid` / `current_run_pgid` so `Stop Now` can terminate the active child pipeline and re-queue the interrupted job safely.

## Prompt Library
- Successful Phase 4 runs auto-ingest prompts through `shared.prompt_library.safe_ingest_run()`.
- Review approve/favorite actions also try to push prompts into the library with `source=review_approved` or `source=review_favorite`.
- Prompt library storage defaults to `~/.audio_asset_studio/prompt_library/`.
- `shared.prompt_library.prompt_library_status()` is the shared availability check for dashboard pages. `chromadb` gates browsing, while `laion-clap` gates search/recommend/auto-ingest.

## Bulk Authoring
- Asset sheet helpers live in `shared/asset_sheet.py`.
- CSV is always supported.
- XLSX import/export requires `openpyxl` and is included in dashboard dependencies.

## Safety UX
- `dashboard/pages/4_⚙️_Settings.py` now protects `Clear all outputs` behind a typed `CLEAR` confirmation because it removes generated assets, reports, and queue logs for every project.
