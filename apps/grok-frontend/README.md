# AniFlow frontend

This directory contains the owner's Grok 4.6 generated Agnes workbench, now adapted as AniFlow's private interactive animation frontend.

**P0-031 behavior correction (2026-10-12):** No historical/unknown-create localStorage lock blocks a new explicit click. Unknown HTTP submission outcomes remain in history with precise error text and immediate manual retry (no hidden automatic retries); prior valid video IDs remain in history for explicit status queries. All-nine Flash mode requires no billing dialog. The prompt textarea is user-resizable, preserves height, and has local saved prompt history. Local single-image mode first attempts direct Base64 data URI in the Agnes request without R2; **public official video docs specify URLs, so acceptance of Base64 by the real provider is unverified**, and a public HTTPS URL is the documented fallback. CI mocks must not be mistaken for Agnes production proof.

**P0-028 operational fix (2026-10-12):** Use the latest successful CI ZIP, not previous P0-027 packages. Agnes Video 2.5 Flash remains the default promotionally free option; paid Agnes Video 2.5 requires explicit price confirmation; V2.0 creation is not offered. Legacy no-video-id submission guards are archived and locally unlocked with one confirmation and a durable browser-only backup; known video IDs remain available to resume status-only. Numeric 1–9 tabs display per-Key 0–100% provider progress. **Text-to-video never needs R2**; Agnes Image now returns a clearly flagged temporary public HTTPS URL when R2 is not configured (the owner should promptly save it). Local file uploads still need public media storage. [中文恢复指南](../../docs/runbooks/2026-10-11-nine-key-frontend-test.md).


> **2026-10-11 P0-021**: Use this branch's **new local Bridge and rebuilt frontend together**. A real headless Chrome test showed Agnes public cross-origin `Authorization` browser fetch is blocked despite OPTIONS 204, so video create/status now go through same-origin `http://127.0.0.1:8765/api/video/*`. The Bridge sends **one** upstream POST per explicitly approved creation and one GET for each status query; it never automatically retries a create. No R2 is needed for text-to-video. [中文操作卡](../../docs/runbooks/2026-10-11-nine-key-frontend-test.md).

## Video models

AniFlow currently supports both:

- `agnes-video-v2.0`
- `agnes-video-2.5-flash`

The model selector changes both the API model and the parameter contract. The two models keep independent auto-saved settings in browser `localStorage`, so switching models does not reset the other model's prompt/settings.

### V2.0

Retains the imported frontend's width/height, resolution tiers, `num_frames`, `frame_rate`, `negative_prompt`, inference steps, seed, image-to-video and multi-keyframe request structure.

### Video 2.5 Flash

Uses the Flash contract:

- `size: "720P"`
- `seconds`: 4-12
- `aspect_ratio`
- `mode: "text"` for text-to-video
- `mode: "keyframe"` + `first_frame` for single-image animation
- `mode: "keyframe"` + `first_frame` + `last_frame` for first/last-frame animation
- `mode: "reference"` + `images: ["https://..."]` for optional character/style reference; the current UI accepts one image although Agnes Flash supports up to five.
- `n: 1`

The optional “载入角色参考图测试 · 5秒” button uses the existing public silver-tabby portrait pinned to a known Git commit, as an *identity reference only*. P0-023 visual QA rejected that source as an exact first frame because the cat stands beside a kitchen appliance and the water bowl is missing. Reference mode can request another pose/background, but visual fidelity and commercial rights are **unproven**. It does not modify MYCL-001's locked 8 shots / 46 seconds.

2.5 Flash requires public HTTP(S) frame URLs. Local image files selected in the browser are uploaded automatically through the AniFlow loopback Bridge and the configured R2/S3-compatible public media store before the video request is created. The same local image upload is cached for a multi-Key batch so it is not uploaded once per Key.

## Multi-Key behavior

- 1-9 Agnes API keys can be entered in the page.
- Keys and key count are automatically saved in the current browser.
- Each configured idle Key can generate independently.
- "Generate all" asks for explicit confirmation and starts every configured idle/unlocked Key, even when another Key is already running; duplicate Key strings across slots are blocked before any batch POST.
- A Key input is locked while that Key has an active or unresolved task so polling/history cannot switch credentials mid-task.
- Each video POST reserves a durable per-Key browser-local guard before calling the local Bridge. Network uncertainty retains the guard; users can resume GET polling by original video_id or manually unlock after checking the provider account.
- "Stop tracking" stops browser polling only; it does not claim to cancel an already-created Agnes server task.
- "复制9-Key安全测试摘要" copies status, category-level failures and measured times **without** Key strings, task/video IDs, prompt or CDN URLs.

Do not use the auto-save feature on a shared/public computer.

## AI image / reference-image panel

The frontend now exposes a provider-neutral image panel before video settings.

### CapCut / Seedream

- The exact model label is entered in the page and auto-saved. It is intentionally not compiled into AniFlow.
- The `.env` model value is only an optional default.
- Up to three reference images can be supplied from local files or public URLs.
- The Bridge reports whether the CapCut Agent Runner is configured separately from whether a default model exists.
- A generated image can be sent directly to the current video's single-image first frame or to Video 2.5 Flash first/last-frame slots.

CapCut browser automation itself is not considered verified until `scripts/capcut_agent_probe.py` captures the owner's real logged-in AI Design UI and a final adapter is built from that probe. AniFlow does not guess coordinates or reverse-engineer private CapCut APIs.

### Agnes Image

- Pick one of the saved Agnes Keys.
- Optional reference images use the same panel.
- The generated Agnes image is copied into AniFlow media storage before it is returned to the frontend, avoiding dependence on a temporary upstream URL.

## Local Bridge

The standard private-local layout is now:

```text
Browser: http://127.0.0.1:8765/
          |
          v
AniFlow Local Bridge
  |-- serves the built single-file frontend
  |-- Agnes Video create/status -> one-shot HTTPS relay (no CORS or retry)
  |-- local image -> R2/S3 -> public URL
  |-- Agnes Image -> persistent public URL
  `-- CapCut Seedream Provider -> browser Agent Runner (after UI probe)
```

The Bridge only binds to loopback. Its normal production-like frontend is same-origin; broad `file://` / `Origin: null` CORS access is intentionally not enabled.

## Windows setup

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_aniflow_windows.ps1
```

For **text-to-video**, R2/S3 is **not required**. Configure `.env` storage only when using browser-local image uploads, Agnes Image or CapCut media.

Normal start:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_aniflow_windows.ps1
```

The script starts the Bridge in the foreground and opens `http://127.0.0.1:8765/`. Keep the terminal open; Ctrl+C stops AniFlow.

## Manual build

```bash
npm install
npm run build
```

`npm run build` runs strict TypeScript checking before the Vite single-file build.

Do not commit real API keys, `.env` secrets, CapCut browser state/cookies, build caches, or `node_modules`.
