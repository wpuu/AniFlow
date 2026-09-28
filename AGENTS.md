# AniFlow Agent Guide

> ## ⚠️ 接手前必读（2026-09-28 更新）
>
> 本文件部分规则**已过期**。接手本项目请**先读**：
>
> 1. **`docs/handover/2026-09-28-takeover-audit.md`** — 接管审计：商业/IP/内容/技术方向的最新判断
> 2. **`docs/model-contracts.md`** — 已核实的 Agnes 官方 API 契约（模型参数的唯一事实来源）
>
> **本文件中已确认失效的规则：**
>
> - ❌ `agnes-video-v2.0` 相关的一切（该模型**已从 Agnes 官方下架**，前端参数契约是死代码）
> - ⚠️ 主力模型应为 `agnes-3.0-flash` + `agnes-image-2.5-flash`（非 2.5-flash / image-2.1-flash）
> - ⚠️ `A -> B -> C` 三帧两段各 5 秒的硬结构**无必要**（视频模型支持 4–12 秒）
> - ⚠️ CapCut / Seedream 自动化**建议删除**（理由见审计 6.3）
> - 🚨 项目存在致命缺口：**完全没有 TTS 配音与字幕**，而抖音审片标准明令禁止「机械配音」
>
> 未经 Owner 确认前，不要按上述过期规则继续开发。

## Product

中文名：动画工厂

Repository: `wpuu/AniFlow`

AniFlow is a private automated animation-content pipeline. It is not a public Agnes API proxy. Real secrets must not be committed or printed in logs/artifacts.

## Fixed product assumptions

- Treat the currently available Agnes Flash models as primary project providers. Do not spend project time monitoring free-plan quotas/pricing unless the owner explicitly changes this rule.
- The owner uses multiple independent Agnes accounts and may enter their API keys directly in the private frontend. Browser keys are intentionally auto-saved locally for convenience; do not use this on public/shared computers.
- Primary reasoning / visual-QA model: `agnes-2.5-flash`.
- Agnes image provider: `agnes-image-2.1-flash`.
- Video models exposed in the private frontend: `agnes-video-v2.0` and `agnes-video-2.5-flash`.
- Primary short-video format: `9:16`; Video 2.5 Flash output `720x1280`.
- V0.1 episode structure: exactly 3 keyframes `A -> B -> C`, two 5-second keyframe-controlled video segments, then concatenate.
- First benchmark styles: needle-felt, clay, miniature toy-world.
- Default production timezone: `Asia/Shanghai`.
- The frontend under `apps/grok-frontend/` is now an active AniFlow frontend, not merely a reserved import area.
- GitHub Actions are currently not a reliable execution path because the owner's GitHub account blocks jobs on billing/spending status. Do not create extra Actions-based smoke work unless this changes.

## Video frontend policy

The private frontend must preserve both video models and each model's own settings.

### Agnes Video V2.0

Keep the imported V2.0 parameter contract, including resolution tiers, width/height, `num_frames`, `frame_rate`, negative prompt, inference steps, seed, image-to-video and old multi-keyframe behavior.

### Agnes Video 2.5 Flash

Use the current contract:

- model: `agnes-video-2.5-flash`
- create: `POST /v1/videos`
- retrieve: `GET /agnesapi?video_id=<id>&model_name=agnes-video-2.5-flash`
- `size: "720P"`
- `seconds`: strings `"4"` through `"12"`
- `n: 1`
- `mode: "text"` for text-to-video
- `mode: "keyframe"` + `first_frame` for single-image animation
- `mode: "keyframe"` + `first_frame` + `last_frame` for first/last-frame animation
- 9:16 output = 720x1280

The two video models keep independent browser-local last/default parameter sets. Switching models must not reset the other model's settings. History records the originating model and must refresh using that original model.

## Frontend hardening already implemented

- 1-9 browser-saved Agnes API keys.
- "Generate all" starts all configured idle Keys instead of being globally disabled by one busy Key.
- Active task history is tracked separately from whichever old history row the user is viewing.
- "Stop tracking" is correctly described as stopping polling only; it does not claim to cancel the server-side Agnes task.
- Busy Key inputs are locked so credentials cannot change during polling/history refresh.
- Key count cannot hide a still-running Key.
- History cannot be cleared while a task is active.
- Local base64 preview images are excluded from saved parameter objects to avoid localStorage quota failure.
- Local image upload errors are surfaced and the same file can be selected again.
- Frontend `npm run build` runs strict TypeScript checking before Vite build.

## Image-provider architecture

AniFlow image generation is provider-neutral.

`src/aniflow/image_provider.py` defines the interface used by:

- cross-style Identity Anchor generation;
- front / three-quarter / side character references;
- story A/B/C keyframes.

Providers:

- `AgnesImageProvider` — direct Agnes Image API.
- `CapCutSeedreamProvider` — controlled external browser-agent provider through a subprocess JSON contract.

Do not reintroduce direct `AgnesImageClient` assumptions into provider-neutral character/keyframe code.

## CapCut / Seedream rules

CapCut/Seedream is a first-class image/keyframe candidate because the owner observes better/faster reference-image output. Do not hard-code one Seedream version. The exact model label is runtime configuration and may be typed in the AniFlow page and auto-saved.

`CAPCUT_SEEDREAM_MODEL` is only an optional default. `CAPCUT_RUNNER_COMMAND` controls whether the local browser Agent Runner exists. Runner readiness and default-model readiness are separate states.

The CapCut provider must automate only the normal signed-in CapCut UI:

- no account creation automation;
- no CAPTCHA/anti-bot bypass;
- no private/undocumented CapCut API reverse engineering;
- no committed cookies or browser state;
- expired login means normal manual sign-in.

The final UI adapter is intentionally not guessed. `scripts/capcut_agent_probe.py` must first capture the owner's real logged-in CapCut AI Design page into gitignored `data/runtime/capcut/`. Only then should selectors/semantic controls be implemented.

Current probe artifacts:

- `snapshot.txt`
- `body.txt`
- `metadata.json`
- `browser-state.json` (sensitive session state; local only)

The subprocess runner contract appends:

`--request <request.json> --response <response.json>`

The response must contain `output_path` or non-empty `output_paths`. Current provider uses the first returned output. Multi-candidate visual ranking is still pending and must not be described as implemented.

## Local Bridge

The private browser frontend now uses a loopback FastAPI Bridge.

Default:

- host: `127.0.0.1`
- port: `8765`
- frontend: `apps/grok-frontend/dist/index.html`

Standard local page:

`http://127.0.0.1:8765/`

The Bridge serves the Vite single-file frontend itself so normal use is same-origin. Do not restore broad `Origin: null` CORS for arbitrary `file://` pages.

Bridge endpoints:

- `GET /api/health`
- `POST /api/media/upload`
- `POST /api/images/generate`

Media upload:

- PNG/JPEG/WEBP only by magic bytes;
- max 20 MiB;
- persists to the S3-compatible public media layer.

Video 2.5 Flash local frame handling:

- browser local image remains a preview data URL only;
- before task creation the frontend sends it to Bridge;
- Bridge persists it to public media;
- the public URL is used as `first_frame` / `last_frame`;
- a multi-Key batch reuses the same in-flight/resolved upload instead of uploading once per Key.

Image generation endpoint:

- Agnes Image requires the request-scoped page Key and persists the upstream image into AniFlow media before returning it;
- CapCut uses the configured Runner plus the page/default model label and also returns an AniFlow-persisted public URL.

## Public media layer

AniFlow uses an S3-compatible abstraction; Cloudflare R2 is recommended but not hard-coded.

Persistent paths include:

- `aniflow/characters/<id>/identity-anchor.*`
- `aniflow/characters/`
- `aniflow/episodes/<episode-id>/keyframes/`
- `aniflow/final/`
- Bridge-generated/uploaded image objects.

Transient paths include visual-QA samples and preflight probes. Real credentials never belong in public media.

## Character identity policy

A style benchmark must compare rendering/video behavior, not independently randomized character designs.

Fixed chain:

1. `agnes-2.5-flash` creates one semantic Character Bible.
2. the selected ImageProvider creates one persistent, style-neutral Identity Anchor locking silhouette/proportions/face/colors/accessory geometry;
3. felt/clay/toy front refs derive from the same anchor, changing material/rendering only;
4. each style's three-quarter/side refs reuse the shared anchor plus existing same-style refs.

Do not revert to three independent text-only style fronts.

## Video quality policy

Each segment candidate is sampled at 0/20/40/60/80/100% and judged by three independent Agnes 2.5 Flash focuses. Numeric scores are median-aggregated.

Hard minimums:

- overall weighted score >= 82
- character identity >= 88
- anatomy integrity >= 85
- start frame match >= 85
- end frame match >= 85
- any hard-fail defect rejects regardless of total score

If every candidate fails, use the best failure diagnosis to repair the video prompt and retry. Default maximum repair rounds: 2 after initial.

After AB/BC assembly, advisory Final QA samples the whole episode including 49%/51% around the middle join and records identity/style/seam/temporal/story/pacing/appeal. It remains calibration telemetry until human review establishes its reliability.

## Human calibration

The first real 30-video benchmark must preserve machine metrics plus human fields for usability, identity/anatomy/background/seam/motion/story/visual-appeal issues and notes. Do not turn Final QA into a hard production gate until the first human calibration is complete.

## Multi-account video policy

Backend `AGNES_API_KEYS` may be a comma-separated list of independent accounts. Default segment generation includes at least one candidate from each configured account, then deterministic round-robin extras. An explicit candidate count may override that default.

Never commit real keys.

## Windows local commands

Initial local preparation:

`powershell -ExecutionPolicy Bypass -File scripts\setup_aniflow_windows.ps1`

Normal start:

`powershell -ExecutionPolicy Bypass -File scripts\start_aniflow_windows.ps1`

Local full verification (replacement for currently blocked GitHub Actions):

`powershell -ExecutionPolicy Bypass -File scripts\verify_aniflow_windows.ps1`

This runs Python pytest plus strict frontend typecheck/Vite build. Do not claim these pass until the owner's real Windows checkout runs the script successfully.

CapCut discovery:

1. `python scripts/capcut_agent_probe.py open`
2. normal manual login/navigation to actual image-generation workspace
3. `python scripts/capcut_agent_probe.py capture`

Do not commit `data/runtime/capcut/browser-state.json`.

## Current implementation status

Implemented/committed:

- multi-account video candidate pipeline;
- Agnes Image, Agnes Video 2.5 Flash and Agnes 2.5 Flash judge clients;
- segment scoring/gates/repair;
- ffmpeg sampling and final assembly;
- advisory Final QA;
- S3-compatible media layer;
- Character Bible / shared Identity Anchor / style refs;
- benchmark/daily runners and calibration fields;
- dual-model private video frontend with independent saved settings;
- frontend bug hardening listed above;
- provider-neutral image architecture;
- local Bridge serving frontend + media upload + image-generation APIs;
- automatic local-image-to-public-URL handoff for Video 2.5 Flash;
- frontend CapCut/Agnes image panel with up to 3 reference images;
- CapCut subprocess provider protocol and Windows-safe command parsing;
- CapCut logged-in UI discovery probe;
- Windows setup/start/verify helper scripts;
- unit tests committed for Bridge/provider logic.

Locally spot-checked in the ChatGPT execution environment (not the full repository checkout):

- CapCut Runner command parsing + JSON subprocess protocol -> OK;
- Bridge health/frontend/media/core CapCut model-override protocol -> OK.

Not yet proven/completed:

- full repository pytest on the owner's Windows checkout after latest changes;
- full frontend `npm run build` on the owner's checkout after latest changes;
- real R2 configuration and live public-media upload from Bridge;
- real Agnes generation through the new Bridge image panel;
- real logged-in CapCut UI probe from the owner's machine;
- final CapCut UI automation adapter;
- real CapCut generation through AniFlow;
- CapCut multi-candidate visual ranking;
- real 30-video benchmark/human calibration;
- production stability.

Do not describe any unverified item as completed or production-ready.
