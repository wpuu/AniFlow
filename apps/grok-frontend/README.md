# AniFlow Grok frontend

This directory contains the owner's Grok 4.6 generated Agnes video workbench, now being adapted as AniFlow's interactive generation frontend.

## Current supported video models

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

Flash keyframe image inputs currently require public HTTP(S) URLs. Local file uploads are kept in memory for preview but are not persisted as base64 inside saved model settings, preventing browser localStorage quota failures. A later AniFlow media-upload adapter will turn local/CapCut images into persistent public URLs automatically.

## Multi-Key behavior

- 1-9 Agnes API keys can be entered in the page.
- Keys and key count are automatically saved in the current browser.
- Each configured idle Key can generate independently.
- "Generate all" starts every configured idle Key, even when another Key is already running.
- "Stop tracking" stops browser polling only; it does not claim to cancel an already-created Agnes server task.

Do not use the auto-save feature on a shared/public computer.

## Build

```bash
npm install
npm run build
```

`npm run build` now runs strict TypeScript checking before the Vite build.

## Image-provider direction

AniFlow image/keyframe generation is being made provider-neutral. Agnes Image remains the default API provider, while CapCut/Seedream is planned as a browser-agent provider. See `docs/capcut-seedream-provider.md`.

Do not commit real API keys, `.env` secrets, browser session/cookie files, build caches, or `node_modules`.
