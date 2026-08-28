# AniFlow Agent Guide

## Product

中文名：动画工厂

Repository: `wpuu/AniFlow`

AniFlow is a private automated animation-content pipeline. It is not a public Agnes API proxy and must not expose Agnes API keys in browser code, repository files, generated pages, logs, or public artifacts.

## Fixed product assumptions

- Treat the currently available Agnes Flash models as the primary project providers. Do not spend project time monitoring or optimizing around free-plan quotas unless the owner explicitly changes this rule.
- The owner uses multiple Agnes accounts; their API keys are separate accounts and are intentionally pooled for parallel candidate generation.
- Primary reasoning / visual-QA model: `agnes-2.5-flash`.
- Primary keyframe model: `agnes-image-2.1-flash`.
- Primary video model: `agnes-video-2.5-flash`.
- Primary short-video format: `9:16`, video output `720x1280`.
- Keyframe image format: `9:16`, `1K` (`736x1312` native Agnes Image 2.1 Flash output).
- V0.1 episode structure: exactly 3 keyframes `A -> B -> C`, two 5-second keyframe-controlled video segments, then concatenate.
- First content styles to validate: needle-felt, clay, miniature toy-world.
- Default production timezone: `Asia/Shanghai`.
- The owner's existing multi-key frontend is private and project-specific; do not redesign AniFlow as a public Agnes proxy.

## Official Agnes Video 2.5 Flash constraints

Source of truth: https://wiki.agnes-ai.com/en/docs/agnes-video-25-flash

- Model: `agnes-video-2.5-flash`
- Create: `POST /v1/videos`
- Retrieve: `GET /agnesapi?video_id=<id>&model_name=agnes-video-2.5-flash`
- Modes: `text`, `keyframe`, `reference`
- Duration: strings `"4"` through `"12"`
- `size`: only `"720P"`
- `n`: only `1`
- Keyframe mode supports `first_frame`, `last_frame`, or both
- Reference mode supports up to 5 images and does not support reference videos
- Media URLs must be publicly reachable until task completion
- Supported output dimensions:
  - 21:9 = 1680x720
  - 16:9 = 1280x720
  - 4:3 = 960x720
  - 1:1 = 720x720
  - 3:4 = 720x960
  - 9:16 = 720x1280

## Character identity policy

A style benchmark must compare rendering/video behavior, not three independently randomized character designs.

Character bootstrap therefore uses this fixed chain:

1. `agnes-2.5-flash` creates one semantic Character Bible.
2. `agnes-image-2.1-flash` creates one persistent, style-neutral `identity-anchor` that locks silhouette, proportions, face placement, colors, accessory geometry and distinguishing feature.
3. felt / clay / toy front references all use that same anchor as their source and may change material/rendering only.
4. Each style's three-quarter and side references use the shared anchor plus the already-generated style references.

Do not revert to generating each style's canonical front independently from text only.

## Quality policy

Each generated candidate is sampled at 0/20/40/60/80/100% and judged by Agnes 2.5 Flash using three independent judging focuses. Numeric scores are median-aggregated.

Hard minimums:

- overall weighted score >= 82
- character identity >= 88
- anatomy integrity >= 85
- start frame match >= 85
- end frame match >= 85
- any hard-fail defect rejects the candidate regardless of total score

If every candidate fails, use the best failed candidate's diagnosis to rewrite the video prompt and retry. Default maximum repair rounds is 2 after the initial round.

## Multi-account policy

`AGNES_API_KEYS` is a comma-separated list of API keys from independently owned Agnes accounts. Each default segment batch independently includes at least one draw from every configured account, even when AB and BC run concurrently. If the configured/default candidate target exceeds account count, continue through accounts in deterministic round-robin order. An explicit CLI candidate count may override the all-account default.

Never commit real keys.

## Media layer

Agnes visual input requires public media URLs. AniFlow uses an S3-compatible media abstraction; Cloudflare R2 is the recommended deployment but is not hard-coded into pipeline logic.

Only media objects need public reachability. The repository, frontend, admin UI, API keys, and internal job metadata may remain private.

Persistent paths:

- `aniflow/characters/<id>/identity-anchor.*` — shared cross-style geometry/identity anchor
- `aniflow/characters/` — style-specific canonical character references
- `aniflow/episodes/<episode-id>/keyframes/` — persistent A/B/C episode keyframes
- `aniflow/final/` — final videos

Transient paths:

- `aniflow/preflight/` — connectivity probe; delete immediately after read verification
- `aniflow/tmp/` — visual-QA sampled frames; delete immediately after judging. Configure a short storage lifecycle as crash/interruption fallback.

## Preflight policy

Before Character, Benchmark, or Daily generation, run live preflight:

- every configured Agnes account must successfully answer a minimal `agnes-2.5-flash` request;
- media store must accept a tiny upload;
- the resulting `S3_PUBLIC_BASE_URL` URL must be readable without authentication and return exact bytes;
- the probe must be deletable.

A failed preflight must stop generation before image/video work starts. `Setup Preflight` provides a standalone one-click GitHub Actions check.

## Current implementation status

Implemented in V0.1 code:

- multi-account Agnes key pool and per-segment all-account candidate coverage
- Agnes Image 2.1 Flash client
- Agnes Video 2.5 Flash keyframe task client and polling
- Agnes 2.5 Flash multimodal visual judge
- three-pass judging with median score aggregation
- candidate hard gates and weighted ranking
- automatic video-prompt repair
- six-frame video sampling with ffmpeg
- S3-compatible public media upload/delete
- automatic cleanup of transient visual-QA frames
- live multi-account Agnes + public-media preflight
- 3-frame storyboard planner
- continuity-aware and selected-style-locked A/B/C keyframe generation
- persistent A/B/C episode keyframes before video generation
- parallel A->B and B->C candidate pipelines
- final 720x1280 two-segment assembly
- reusable Character Bible, shared identity anchor, plus felt/clay/toy style reference generation
- shared-story style benchmark: default 10 identical stories x 3 styles = 30 videos
- history-aware daily content runner
- `aniflow doctor`, `preflight`, `character`, `segment`, `episode`, `benchmark`, and `daily` CLI commands
- GitHub workflows: CI, Setup Preflight, character bootstrap, style benchmark, daily generation
- unit/import tests for core control logic

Implemented but not yet proven with a real production run:

- live Agnes API calls using the owner's real multi-account keys
- live R2/S3 upload configuration and Agnes access to those URLs
- Setup Preflight workflow with real secrets
- Build Character References workflow with real secrets
- 30-video Style Benchmark with real generation
- scheduled Daily Animation Factory with real generation

Still pending after first real validation:

- visual-score calibration against human ratings
- integration of the owner's existing private multi-key frontend
- final-publish approval UX
- publishing integrations to external platforms
- optional final whole-episode QA / audio / music / subtitles

Do not describe any unverified item above as completed or production-ready.
