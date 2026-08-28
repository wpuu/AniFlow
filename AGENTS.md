# AniFlow Agent Guide

## Product

中文名：动画工厂

Repository: `wpuu/AniFlow`

AniFlow is a private automated animation-content pipeline. It is not a public Agnes API proxy. Real API keys must never be committed to repository files, embedded into generated bundles, printed in logs, or exposed in public artifacts.

The owner's private interactive frontend may accept Agnes keys at runtime and save them in that user's browser `localStorage` for convenience. This is a private-use UX choice, not permission to hard-code keys into source code or ship them in build output.

## Fixed product assumptions

- Treat the currently available Agnes Flash models as primary project capabilities. Do not spend project time monitoring or optimizing around free-plan quotas unless the owner explicitly changes this rule.
- The owner uses multiple Agnes accounts; their API keys are separate accounts and are intentionally pooled for parallel candidate generation.
- Primary reasoning / visual-QA model: `agnes-2.5-flash`.
- Image generation must be provider-neutral. Agnes Image 2.1 Flash is the default direct-API provider, but CapCut/Seedream is a first-class planned image provider because the owner has observed better/faster reference-image results in their actual CapCut environment.
- Video generation comparison must support both `agnes-video-v2.0` and `agnes-video-2.5-flash` in the private frontend. The backend V0.1 episode pipeline currently targets Video 2.5 Flash for the A->B / B->C benchmark.
- Primary short-video format: `9:16`; Video 2.5 Flash output is `720x1280`.
- Default Agnes keyframe image format: `9:16`, `1K` (`736x1312` native Agnes Image 2.1 Flash output).
- V0.1 episode structure: exactly 3 keyframes `A -> B -> C`, two 5-second keyframe-controlled video segments, then concatenate.
- First content styles to validate: needle-felt, clay, miniature toy-world.
- Default production timezone: `Asia/Shanghai`.
- The owner's existing multi-key frontend is private and project-specific; do not redesign AniFlow as a public Agnes proxy.
- The Grok-generated frontend lives under `apps/grok-frontend/` and is now an actively adapted AniFlow interactive workbench, not merely a reserved import area.

## Private frontend model policy

`apps/grok-frontend/` supports two independent Agnes video profiles:

### Agnes Video V2.0

- API model: `agnes-video-v2.0`
- Preserve the imported V2 controls and request family: width/height, 480p/720p/1080p presets, `num_frames`, `frame_rate`, `negative_prompt`, inference steps, seed, single-image and multi-keyframe behavior.

### Agnes Video 2.5 Flash

- API model: `agnes-video-2.5-flash`
- `size`: `720P`
- `seconds`: 4-12
- `aspect_ratio`
- text-to-video: `mode=text`
- single-image animation: `mode=keyframe` + `first_frame`
- first/last-frame animation: `mode=keyframe` + `first_frame` + `last_frame`
- `n=1`

Each video model must keep an independent auto-saved parameter set. Switching V2.0 -> 2.5 Flash -> V2.0 must restore the user's previous V2.0 settings rather than rebuilding defaults.

History records must keep the model used to create each task, and polling/manual refresh must query with that original model even if the user has since switched the active model.

Agnes API keys entered into the private frontend are auto-saved in browser `localStorage` because the owner explicitly wants that convenience. Never commit those values. Do not use this UX on shared/public computers.

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

Local browser `data:` images must not be sent as Flash keyframes. They must first be persisted through AniFlow's public media layer and converted to reachable HTTP(S) URLs.

## Image-provider architecture

`src/aniflow/image_provider.py` defines the provider-neutral image interface used by character and story-keyframe pipelines.

Current implementation:

- `ImageProvider` protocol
- `AgnesImageProvider` default adapter
- `KeyframeGenerator` accepts a custom provider
- `CharacterBuilder` accepts a custom provider

Therefore the following stages can use Agnes Image or a future CapCut/Seedream provider without rewriting downstream video/QA logic:

1. shared identity anchor;
2. style-specific front / three-quarter / side character references;
3. episode A/B/C story keyframes.

Provider output must become a durable/public URL before being passed into Agnes Video.

### CapCut / Seedream provider direction

Preferred first implementation is normal CapCut Web UI automation through a browser Agent, not coordinate-based desktop clicking and not private API reverse engineering.

Rules:

- user performs normal login manually once;
- authorized browser state is local-only and never committed;
- automate visible model selection, prompt input, reference upload, ratio selection, Generate and normal result download;
- treat the model label as runtime configuration rather than hard-coding a particular Seedream version, because the owner's account may expose labels such as Seedream 4.3 / 4.0s while public CapCut pages can expose newer labels;
- no automated account creation, CAPTCHA bypass or anti-bot bypass;
- fail closed when required UI elements cannot be identified;
- persist downloaded candidates into AniFlow's media store before Video use;
- when CapCut returns multiple images, compare candidates using visual QA rather than blindly choosing the first.

Detailed plan: `docs/capcut-seedream-provider.md`.

## Character identity policy

A style benchmark must compare rendering/video behavior, not three independently randomized character designs.

Character bootstrap therefore uses this fixed semantic chain:

1. `agnes-2.5-flash` creates one semantic Character Bible.
2. the selected `ImageProvider` creates one persistent, style-neutral `identity-anchor` that locks silhouette, proportions, face placement, colors, accessory geometry and distinguishing feature.
3. felt / clay / toy front references all use that same anchor as their source and may change material/rendering only.
4. each style's three-quarter and side references use the shared anchor plus the already-generated style references.

Do not revert to generating each style's canonical front independently from text only.

## Quality policy

Each generated video candidate is sampled at 0/20/40/60/80/100% and judged by Agnes 2.5 Flash using three independent judging focuses. Numeric scores are median-aggregated.

Hard minimums:

- overall weighted score >= 82
- character identity >= 88
- anatomy integrity >= 85
- start frame match >= 85
- end frame match >= 85
- any hard-fail defect rejects the candidate regardless of total score

If every candidate fails, use the best failed candidate's diagnosis to rewrite the video prompt and retry. Default maximum repair rounds is 2 after the initial round.

After AB and BC pass and are assembled, V0.1 also runs an advisory whole-episode Final QA. It samples the final video with points bracketing the middle join at 49%/51% and evaluates whole-episode character identity, style consistency, seam continuity, temporal integrity, story clarity, pacing and visual appeal. During the first benchmark this Final QA must not discard an otherwise viewable video; its scores are calibration telemetry until compared with human ratings.

For multi-candidate image providers such as CapCut/Seedream, candidate selection should eventually judge character identity, anatomy/geometry, style/material, reference fidelity, scene continuity and suitability as a stable first/last video frame before selecting one durable image URL.

## Human calibration policy

The first real 30-video benchmark must preserve a human calibration sheet. The benchmark report already embeds human calibration rows; `data/calibration/<run_id>.json` may also be emitted locally. Do not claim the current GitHub benchmark workflow commits `data/calibration/` unless that workflow is explicitly updated and verified.

Do not make Final QA a hard production gate until the first human review is complete and false-positive/false-negative behavior has been measured.

## Multi-account policy

`AGNES_API_KEYS` is a comma-separated list of API keys from independently owned Agnes accounts. Each default segment batch independently includes at least one draw from every configured account, even when AB and BC run concurrently. If the configured/default candidate target exceeds account count, continue through accounts in deterministic round-robin order. An explicit CLI candidate count may override the all-account default.

Never commit real keys.

In the private browser frontend, Key count and Key values are auto-saved locally. "Generate all" should start every configured idle Key and skip Keys already running rather than disabling the whole batch because one Key is busy.

## Frontend task/history rules

- A running task is bound to its own history ID; selecting another history item must not change which record is marked stopped/completed.
- "Stop tracking" means stop browser polling only. Do not claim the server-side Agnes generation was cancelled unless an actual cancel API is used.
- Do not reduce the configured Key count if that would hide a currently running Key.
- Do not clear task history while tasks are running.
- Avoid nested interactive `<button>` elements in history cards.
- Browser-uploaded base64 images are ephemeral and must not be persisted as part of the entire parameter object in `localStorage`, because a few images can exceed browser storage quota and make all setting persistence fail.
- Image processing/upload errors must be visible to the user; do not silently swallow them.
- `npm run build` must run strict TypeScript checking before Vite packaging.

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
- `aniflow/tmp/` — segment/final QA frames and future rejected image-provider candidates; delete after judging, with short lifecycle as crash fallback

## Preflight / execution policy

Before Character, Benchmark, or Daily generation, live validation must eventually cover every configured Agnes account plus the public media upload/read/delete path.

The repository contains GitHub workflows for CI, Setup Preflight, character bootstrap, benchmark and daily generation. At the 2026-08-28 checkpoint, the owner's GitHub account is preventing Actions jobs from starting because of GitHub Billing/Spending-limit state. This is an external execution limitation, not an AniFlow or Agnes API failure.

Until that account state is changed, do not waste project time using GitHub Actions as the primary validation mechanism. Prefer local/Codex execution for typecheck/build/tests and real runtime checks. Do not describe an unstarted GitHub Action as an Agnes failure.

## Current implementation status

Implemented in V0.1 code:

- multi-account Agnes key pool and per-segment all-account candidate coverage
- Agnes Image 2.1 Flash client
- provider-neutral `ImageProvider` + default `AgnesImageProvider`
- provider-neutral character identity/reference generation injection
- provider-neutral A/B/C keyframe generation injection
- Agnes Video 2.5 Flash keyframe task client and polling
- Agnes 2.5 Flash multimodal visual judge
- three-pass segment judging with median score aggregation
- candidate hard gates and weighted ranking
- automatic video-prompt repair
- six-frame segment video sampling with ffmpeg
- advisory whole-episode Final QA with middle-seam-focused sampling
- S3-compatible public media upload/delete
- automatic cleanup of transient segment/final visual-QA frames
- live multi-account Agnes + public-media preflight code
- 3-frame storyboard planner
- continuity-aware and selected-style-locked A/B/C keyframe generation
- persistent A/B/C episode keyframes before video generation
- parallel A->B and B->C candidate pipelines
- final 720x1280 two-segment assembly
- reusable Character Bible, shared identity anchor, plus felt/clay/toy style reference generation
- shared-story style benchmark: default 10 identical stories x 3 styles = 30 videos
- benchmark embedded human-calibration rows
- history-aware daily content runner
- adapted private Grok frontend under `apps/grok-frontend/`
- frontend V2.0 / Video 2.5 Flash switch with model-specific request contracts
- independent per-video-model auto-saved frontend settings
- model-aware task history/result polling
- hardened multi-Key controls and browser persistence
- `aniflow doctor`, `preflight`, `character`, `segment`, `episode`, `benchmark`, and `daily` CLI commands
- GitHub workflows: CI, Setup Preflight, character bootstrap, style benchmark, daily generation
- unit/import tests for core control logic
- CapCut/Seedream provider design document

Implemented or statically reviewed but not yet proven end-to-end with the owner's real runtime:

- live Agnes API calls through the current backend using the owner's keys
- live R2/S3 upload configuration and Agnes access to those URLs
- complete private frontend Vite production build in the owner's environment (strict TypeScript checking of changed core files passed during review; GitHub Actions are unavailable at this checkpoint)
- Video V2.0 / 2.5 Flash browser calls from the modified frontend with real keys
- advisory Final QA behavior on real Agnes-generated assembled videos
- 30-video Style Benchmark with real generation
- scheduled Daily Animation Factory with real generation

Still pending / next external integrations:

- actual `CapCutSeedreamProvider` browser Agent against the owner's signed-in CapCut Web UI
- local image upload -> AniFlow media store -> public URL bridge for Video 2.5 Flash
- candidate-level CapCut/Seedream image vision ranking
- visual-score and Final-QA calibration against human ratings
- final-publish approval UX
- publishing integrations to external platforms
- optional audio / music / subtitles

Do not describe any unverified item above as completed or production-ready.
