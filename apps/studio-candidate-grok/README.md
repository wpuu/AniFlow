# AniFlow Grok candidate (P0-035 review)

This folder is an exact text-source snapshot of the **Grok-uploaded ZIP** dated 2026-10-25. The original ZIP remains at the repository root. The binary logo is not duplicated in Git; to recover it safely, run from the repository root:

`python scripts/stage_grok_logo.py`

**This is a visual candidate only.** No AWS, ComfyUI, MiniMax H3, Agnes or Hugging Face API is connected. The UI currently animates simulated tasks, returns third-party sample video links and displays fictional prices/health. NEVER regard those as real GPU status, jobs, generated MP4s or charges.

Do not merge this directory over `apps/grok-frontend`. Engineering should develop an adapter in a separate integration location, with strict real-vs-mock labels, server-side durable tasks, file integrity verification, cost permission gates and no automatic paid requests. The Claude ZIP stays in the repository as comparison reference.

See `docs/reviews/2026-10-25-claude-grok-frontend-audit.md`.
