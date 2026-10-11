# AniFlow / 动画工厂

> **当前审计更新（2026-10-11）：** 本仓库的旧视频工作台安装器仍固定 `agnes-video-generator v7.0.4`，自制“队列满换 Key”补丁不可直接用于上游 `v7.1.0`。**不要把下方 V0.1/旧安装命令视为已验收的最新生产路径。** 现已新增只读兼容性预检与 7 项离线测试；Windows、真实 Key、竖屏视频与首集商业可行性仍待验。请先阅读 [最新独立复核](docs/reviews/2026-10-11-aniflow-business-and-v710-audit.md)、[离线验收记录](docs/reviews/2026-10-11-v710-offline-test-evidence.md)；预检脚本为 `scripts/audit_video_studio_v710.py`。本次是隔离分支候选，不表示已经部署、完成完整升级或实际出片。
> **P0 首集时间线锁定（本轮新增）：** `scripts/inspect_video_output.py` 现支持 `--kind episode --shotlist content/shotlists/MYCL-001-cat-lapping.json --min-short-side 720`，按真实镜头工单校验 46 秒总时长（默认 ±0.75 秒）、首尾帧继承及音轨覆盖，并生成工单 SHA-256 便于复核。旧 24 项测试＋新增 21 项测试，离线累计 **45/45 PASS**，另用三种 FFmpeg 合成视频实际验证正常、视频缺时长、音轨提前结束三种结果；**均不代表真实 Agnes 视频、Windows 或人工 QA 已通过**。见 [首集锁定验收记录](docs/reviews/2026-10-11-shotlist-locked-episode-qa.md)。
> **P0 安全验收工具新增：** [固定上游 v7.1.0 的源码准备器](scripts/prepare_video_studio_v710.py)（默认只预览、不会复制 Key 或自动启动）、[MP4 画幅/时长/音轨检查器](scripts/inspect_video_output.py)（元数据通过仍须人工观看）。两组新测试共 **24/24** 在离线模拟/合成媒体上通过；Windows、真实 Agnes 视频仍未验收。详见 [P0 验收交接](docs/reviews/2026-10-11-p0-preparation-and-mp4-acceptance.md)。

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
aniflow queue-probe      # 探测视频队列是按账户还是全平台共享
aniflow bridge
aniflow preflight
aniflow character
aniflow segment
aniflow episode
aniflow benchmark
aniflow daily
```

Do not describe the project as production-ready until the real Windows verification, public-media validation, logged-in CapCut probe/adapter, live Agnes path and first human-calibrated benchmark have been completed.
