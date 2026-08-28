# AniFlow / 动画工厂

AniFlow is a private AI animation-production pipeline focused on repeatable short-form vertical animation rather than one-off prompt generation.

## Current V0.1 shape

- story / storyboard / visual QA / prompt repair: `agnes-2.5-flash`
- image generation: provider-neutral (`Agnes Image` or controlled `CapCut / Seedream` path)
- video generation: `agnes-video-v2.0` and `agnes-video-2.5-flash` are both available in the private frontend
- default production format: vertical `9:16`
- V0.1 episode: `A -> B -> C`, two controlled video segments, then final assembly
- public media: S3-compatible store; Cloudflare R2 recommended
- private interactive frontend: `apps/grok-frontend/`
- local frontend/API host: AniFlow loopback Bridge on `127.0.0.1:8765`

Real API keys, R2 credentials and browser session state must never be committed.

## Windows local use

GitHub Actions are not currently the preferred execution path for this repository because the owner's account is blocking jobs on billing/spending status. Local Windows verification is the current source of truth.

First preparation:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_aniflow_windows.ps1
```

Create `.env` from `.env.example` and fill the R2/S3 values needed for public media.

Normal start:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_aniflow_windows.ps1
```

The Bridge serves the built single-file AniFlow frontend at:

```text
http://127.0.0.1:8765/
```

Full local verification:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_aniflow_windows.ps1
```

That command runs Python tests plus strict TypeScript checking and the Vite frontend build.

## Private frontend

The frontend supports 1-9 browser-saved Agnes Keys and keeps separate settings for:

- `agnes-video-v2.0`
- `agnes-video-2.5-flash`

Switching video model does not reset the other model's saved parameters.

The page also includes an AI image/reference-image panel:

- Agnes Image
- CapCut / Seedream
- up to 3 reference images
- exact CapCut model label entered in the page and auto-saved
- generated result can be sent directly into a video's first frame or Video 2.5 Flash first/last frame

For Video 2.5 Flash, local browser images are automatically uploaded through the Bridge to the configured public media store before the Agnes video request is sent.

## CapCut / Seedream status

The provider abstraction, local Bridge endpoint and subprocess Runner contract are implemented. The final CapCut UI automation is intentionally gated on a real logged-in UI probe rather than guessed coordinates/selectors.

On the actual Windows machine:

```powershell
python scripts\capcut_agent_probe.py open
```

Log in normally and navigate to the real CapCut AI image/design workspace, then:

```powershell
python scripts\capcut_agent_probe.py capture
```

Private probe/session artifacts are written under gitignored `data/runtime/capcut/`.

See:

- `AGENTS.md`
- `docs/capcut-seedream-provider.md`
- `apps/grok-frontend/README.md`

## Backend CLI

Available commands include:

```text
aniflow doctor
aniflow bridge
aniflow preflight
aniflow character
aniflow segment
aniflow episode
aniflow benchmark
aniflow daily
```

Do not describe the project as production-ready until the real Windows verification, public-media validation, logged-in CapCut probe/adapter, live Agnes path and first human-calibrated benchmark have been completed.
