# AniFlow frontend

This directory contains the owner's Grok 4.6 generated Agnes workbench, now adapted as AniFlow's private interactive animation frontend.

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
- `n: 1`

2.5 Flash requires public HTTP(S) frame URLs. Local image files selected in the browser are uploaded automatically through the AniFlow loopback Bridge and the configured R2/S3-compatible public media store before the video request is created. The same local image upload is cached for a multi-Key batch so it is not uploaded once per Key.

## Multi-Key behavior

- 1-9 Agnes API keys can be entered in the page.
- Keys and key count are automatically saved in the current browser.
- Each configured idle Key can generate independently.
- "Generate all" starts every configured idle Key, even when another Key is already running.
- A Key input is locked while that Key has an active task so polling/history cannot switch credentials mid-task.
- "Stop tracking" stops browser polling only; it does not claim to cancel an already-created Agnes server task.

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

Then create local `.env` from `.env.example` and fill the R2/S3 values needed for public media.

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
