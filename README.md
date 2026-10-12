# AniFlow / 动画工厂

> **P0-034（2026-10-12）**：计划改为 `v0.34.2` 共享本机Python依赖：不再每个发布包重复运行pip，只有首次初始化或实际依赖变化才安装。Agnes Video 2.5 Flash 如持续返回 `HTTP503/video_queue_full`，属于上游免费共享队列拒绝创建请求，不能通过本地重装/增加Key解决。详见 [P0-034 审计记录](docs/reviews/2026-10-12-p0034-shared-runtime-agnes-503.md)。当前代码提交与完整CI在完成前不代表已安装或可以下载新版。


> **P0-021 9-Key 原前端可测性修复（2026-10-11）：** 原有 `apps/grok-frontend` 保留，并非新建应用。已验证公开 Agnes 视频接口的浏览器跨域 `Authorization` 请求会被阻止（[Chrome 无真实 Key 测试](https://github.com/wpuu/AniFlow/actions/runs/38152367310)）。因此隔离分支加入本机 Bridge 单次视频转发和每 Key 创建前持久安全锁，网络超时不自动重试，保留按 `video_id` 查询的能力。**要更新前端和本地 Python Bridge 两部分，不能只替换 HTML。** 文生视频不需要 R2。Windows 按[9-Key 中文试用卡](docs/runbooks/2026-10-11-nine-key-frontend-test.md)操作。**目前尚无真实 Agnes 视频、账户费用或人工画质证据**，PR #2 仍为 Draft，`main` 不变。


> **P0-012 云端单镜头启动入口（2026-10-11）：** 已为当前隔离分支提供 [打开 GitHub Codespaces 创建页面](https://codespaces.new/wpuu/AniFlow/tree/audit/2026-10-11-v710-revalidation)。该云端环境预装 Python/FFmpeg，**无自动运行/生成 Hook**；可在 Codespaces 创建页可选填入账户个人加密密钥 `ANIFLOW_SINGLE_SHOT_API_KEY`，只能经明确指令生成一条五秒视频。创建 Codespace 可能消耗 GitHub 配额，先核实账户付费提示，绝不把 Key 放在 Issues、PR、CI 或聊天。完整低人工操作说明见 [P0-012 Codespaces 安全运行卡](docs/runbooks/2026-10-11-p012-codespaces-single-shot.md)。已用 GitHub Actions 验证无 Key、断网、只读项目目录的容器构建及 25 项测试；**还未在用户 Codespace 中用真实 Key 成功出片**。草稿 PR 继续不合并。

> **P0-010 单条真实视频入口与队列结论纠偏（2026-10-11）：** 以前把“多账号同时提交时部分成功、部分队列满”解释为**账号级配额**是错误的——**共享队列仅剩少数空位同样产生混合结果**，不可据此声称九倍视频产能。旧 `queue-probe` 已被显式确认和次数上限保护，默认不再并发提交多个可能收费的任务。新增 [`scripts/one_agnes_real_shot.py`](scripts/one_agnes_real_shot.py) 以第一集第 1 镜头为唯一固定对象：默认只预览；仅明确批准当前计费并在可信电脑配置**一个单独环境变量 Key**后，才允许发送**一次** Agnes Video 2.5 Flash 视频创建请求，保存任务 ID，并可无新增 POST 续查；结果仍需实际观看横倒/角色质量。官方当前 Flash 720P 标价限时零费用，可能随时调整。**该程序在仓库中，不代表已持有 Key 或已生成真实 Agnes 视频**。详见 [Issue #5](https://github.com/wpuu/AniFlow/issues/5)；未获真实视频验证前 PR 保持草稿。

> **P0-007 素材快照验收（2026-10-11）：** 本地合片程序已修复“预检后源视频或配音改变，但 FFmpeg 继续读原路径”的问题：执行 `--render` 时为所有来源文件创建隔离快照，复核 SHA-256 与媒体元数据，再以快照合成。新增 9 项快照测试，加上原 28 项专项回归，临时 Linux / FFmpeg 上 **37/37 通过**，其中实际走通合成 720×1280 正式画幅；**没有整仓库测试、Windows 实机或 Agnes 真视频证据**。临时快照会额外占用磁盘。见 [P0-007 记录](docs/reviews/2026-10-11-p0-007-immutable-input-snapshots.md)，PR #2 仍未合并。

> **最新 P0-006（2026-10-11）：** 本分支 [`assemble_locked_episode.py`](scripts/assemble_locked_episode.py) 新增**逐镜头独立旁白**输入（`--scene-audio-dir`），对齐 MYCL-001 的 8 镜头时间段；保留旧 `--narration` 单音轨兼容模式。当前 28 项相关离线测试通过，实际 FFmpeg 合成视频中 8 条不同频率的音轨均被核对出现在正确镜头时间段；**没有真实 Agnes 视频、授权商用 TTS、字幕或 Windows 实机验收**。详见 [P0-006 报告](docs/reviews/2026-10-11-p0-006-per-shot-narration-assembly.md) 和 [Issue #5](https://github.com/wpuu/AniFlow/issues/5)。

> **P0-005 源码级风险与备用合片路径（2026-10-11）：** 上游正式产物修改/批准链对 `creative:script` 会触发脚本产物重算，且未发现可单独写回 `narrations[0]` 的受支持产物入口。因此**不能声称人工检查点已确保已审核旁白在恢复后保持不变**。本分支增加 [`assemble_locked_episode.py`](scripts/assemble_locked_episode.py)：只读取已生成的 8 个本地镜头与合法音轨，按 MYCL-001 46 秒工单做预检，并在显式 `--render` 时本地 FFmpeg 拼接；默认绝不生成视频或上传素材。**新增加的 16 项离线用例已通过，含真实 FFmpeg 合成彩色假视频；没有 Agnes 真片、商业语音许可、字幕发布验收**。详见 [P0-005 技术结论](docs/reviews/2026-10-11-p0-005-creative-resume-and-local-assembly.md) 和 [Issue #5](https://github.com/wpuu/AniFlow/issues/5)。

> **P0-004 新发现——原文不能被自动保证：** 上游 v7.1.0 的 Creative 创意模式虽然支持 8 镜头和指定秒数，但仍会由 AI 重新生成分镜及整条旁白。本分支新增 [`lock_upstream_creative_checkpoint.py`](scripts/lock_upstream_creative_checkpoint.py) 及 21 项离线测试，仅支持导出已审核原稿和只读检查人工检查点；**上游正式界面能否持久导入原文仍未实机验证**。加上此前 45 项测试，共 **66/66 离线通过**，不代表能够真实锁住创意模式中的配音或已经出片。见 [P0-004 交接](docs/reviews/2026-10-11-p0-004-creative-checkpoint-content-lock.md)、[Issue #4](https://github.com/wpuu/AniFlow/issues/4)。

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
