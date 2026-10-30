# 本机 H3 Bridge 接入准备（未连接真实 H3）

## 当前结论

本机 Bridge 已增加用户选择的东京 WorkSpaces `Graphics.g6.4xlarge` Windows 路径的门禁兼容。此变更只完成本地接口与契约测试，不证明 WorkSpaces 账户资格、赠金、容量、SSM 或双停机已经核验。没有生成可通过的真实 gate；真实模式默认仍禁用。云端创建、模型部署与实际结果应以另行保存的 AWS 实读证据为准。

已有 8765 系统和 8767 Mock 服务不改。新服务仅监听 `127.0.0.1:8768`，复用当前 Grok Studio 编译结果。新服务没有 AWS SDK 调用，不持有 AWS 凭证，不创建/升级/启动/停止任何 AWS 资源。

## 本地查看

在已安装项目依赖的仓库中，由 `.venv/Scripts/python.exe` 运行 `scripts/run_studio_real.py`，浏览器打开 `http://127.0.0.1:8768/`。未配置人工审计文件和固定官方 API 工作流时，REAL 健康接口返回 `ready=false`；生成提交返回 403。本地上传和历史查看可以使用，不触发模型计算。

服务仅允许 ComfyUI 的 loopback HTTP 地址；默认 `http://127.0.0.1:8188`，未来由用户已有 SSM 会话转发。健康字段 `tunnel_connected` 只说明 ComfyUI HTTP 服务可达；`gpu_connected` 必须另有 `/system_stats` 报告 CUDA 设备且显存大于零。CPU-only 服务即使隧道连通，仍为 `gpu_connected=false`、`ready=false`，禁止上传上游和提交模型任务。GPU 设备信息本身不证明许可证、预算、目标实例型号或停机措施已经核验。

REAL 的 `GET /api/studio/cloud/preflight` 使用独立接口，`mode=LOCAL_AUDIT_PROJECTION`，不再复用 Mock 的 EC2 占位结果。它只投影通过完整 workflow/gate 校验的本地审计，不查询 AWS；`aws_queries=0`、`aws_writes=0`。没有有效 gate 时，默认展示 WorkSpaces 东京候选的预期规格（Graphics.g6.4xlarge、NVIDIA L4、24GiB 显存、64GiB 内存），十项检查全部 `null`，账户计划 `unknown`，余额/价格/余额核验时间均 `null`，且 `launch_allowed=false`。预期规格不表示资源已创建或已观察到该型号。

有效审计中的 `account_plan`、`estimated_credit_remaining_usd`、`credit_settled_remaining_usd`、`credit_observed_at_utc`、`hourly_price_usd` 只有明确记录才返回，缺失字段保持未知；估计余额与结算余额分开。过期、workflow 哈希不符或缺少必要检查时，整份预检审计退回未知，不能沿用旧的通过状态。`real_gpu_connected`、`tunnel_connected` 只来自当前 ComfyUI 设备观察；即使本地审计通过，GPU/隧道有阻塞也不能 `launch_allowed=true`。旧 EC2 gate 保留 `service=ec2` 与对应 EC2 检查，不会转换为 WorkSpaces 通过。8767 Mock 预检保持原行为。

## 未来启用前的人工审计要求

运行配置使用 `ANIFLOW_REAL_DATA_DIR`、`ANIFLOW_COMFY_URL`、`ANIFLOW_REAL_GATE`、`ANIFLOW_H3_WORKFLOW`。此次没有生成可通过的 gate，也没有假造官方 H3 workflow。

人工 gate 按 AWS 服务分别验证；`provider` 在任务接口中继续固定为模型 `minimax-h3`，gate 的 `service` 表示 AWS 服务，不改变模型接口。

| gate 条件 | EC2（原行为） | WorkSpaces（新增） |
|---|---|---|
| `service` | 缺省或 `ec2` | 必须明确 `workspaces` |
| `region` | `ap-northeast-1` | `ap-northeast-1` |
| `instance_type` | `g6e.2xlarge` | `Graphics.g6.4xlarge` |
| 赠金适用检查 | `credit_ec2_eligible=true` | `credit_workspaces_eligible=true`，不能拿 EC2 适用证明替代 |
| 东京配额检查 | `tokyo_gpu_quota=true` | `tokyo_workspaces_quota=true`，不能拿 EC2 配额替代 |
| 实验预算 | `experiment_budget_usd` 大于 0、至多 $20 | `credit_budget_usd` 大于 0、至多 $20；另行明确 `cash_cap_usd` 为 $0–$1，不能将赠金预算当作自付许可 |
| 账户检查 | 保留既有门禁 | `account_plan_unchanged=true` 且 `workspaces_account_eligible=true`，前者仅表示未升级或变更，不能代替后者的服务及计费资格核验 |

两条路径均要求 `checks` 中 `credit_expiry_confirmed`、`tokyo_capacity_and_price`、`ssm_private_connectivity`、`h3_license_territory`、`gpu_stop_safeguard`、`independent_stop_safeguard` 全部明确为真。GPU 运行时长不超过 14,400 秒，gate 剩余有效期不超过 4 小时；预算核验应包含目录、基础费用、存储、网络和日志等实际适用费用。赠金余额不足、无法确认抵扣或无法保证自付上限时，不得把门禁标为通过。

`launch_allowed` 必须为真；该字段只是既有核验结论，不会启动实例。gate 还必须绑定本地 workflow 文件的 SHA256。WorkSpaces 机型名称在本地只是审计匹配字段，不能证明 GPU 显存实际足够；连接后仍需真实设备和模型验证。

工作流文件为固定 API-format bundle：`source_url` 指向 Comfy-Org 官方来源，`prompt` 保存经过人工核对的 API 节点，`bindings` 明确首帧、提示词以及可选负面提示词对应的节点和输入名。必须从官方 H3 工作流导出并记录源版本；Bridge 不猜 H3 节点、不下载模型、不把第三方 API 节点当本地 H3。SHA256 校验是防止本地工作流在审计后改变，不能代替人工核实来源和模型。

**Bridge 不实施云端定时停止。** 启用前必须在 AWS 另行落实并验证双重停机；人工文件声明不能代替真实停机措施。更换云区域、实例或 provider 必须先由用户决定。

## 可靠性与真实结果条件

- REAL 与 Mock 使用独立 API、SQLite 和目录。8768 不暴露 Mock 创建接口。
- 仅允许首轮一条 5 秒、9:16 任务。先持久化本机幂等编号，再发送一次 ComfyUI `/prompt`；相同编号只返回既有任务，不再次提交。未知结果和重启只查询 `/queue`、`/history` 中服务端保存的关联编号。找不到仍保持未知，不自动重发。
- 本机后台持续查询并自动下载，不依赖网页持续在线。下载中断只重试只读下载；不重新生成。尚未实现分块断点续传，重试会从头读取同一 MP4。
- MP4 写入 `.partial`；检查响应长度、容器、ffprobe、约 5 秒、短边至少 768、竖屏 9:16，以及 ffmpeg 全帧解码后才原子改名并显示完成。返回本机绝对路径、字节数、视频信息及 SHA256。再次下载时重新核对哈希。
- 显存峰值和 AWS 实际费用尚未接入可信采集源，均返回 `null`。`elapsed_seconds` 是 Bridge 提交至本地校验完成的端到端时间，不能当纯 GPU 推理时长。

## 已审计原生 H3 的固定 5 秒后处理

已审计的 workflow bundle 明确包含 `postprocess`，且其唯一字段为 `preset: h3_native_5s_portrait_v1` 时，使用本段更严格流程。**本次 `service=workspaces` 的固定 H3 实验必须带该配置，否则门禁拒绝**。未知、空或附带额外参数的配置在提交前拒绝；没有 `postprocess` 的既有 EC2/旧路径保持上述原行为。增加此配置会改变 bundle 哈希，必须重新人工审计，不能沿用旧的 gate SHA256。提交时将配置存入本机任务；断网或重启后的结果处理使用这份既有配置，不再次提交模型任务。

1. 将下载到的原始文件完整校验为 MP4、800×1376、24fps、至少 124 个可读取帧，并完整解码；保存为 `<job>.source.mp4`。记录 `source_local_path`、`source_sha256`、`source_bytes`、`source_video_metadata`。此时任务尚未完成，原始片只作为生成证据保留。
2. 固定截取源帧 0–119，裁为 774×1376，起点 x=12、y=0（左裁 12、右裁 14），设置 SAR=1。没有缩放、补帧、插帧或帧率转换。有音轨时同步截取前 5 秒，重新编码为 AAC 192kbps；无音轨时不添加音轨。`audio_present` 记录真实音轨存在情况。
3. 本地 FFmpeg 将视频重新编码为 H.264 CRF18、yuv420p；这是高质量有损编码，不能称为位级无损。最终片必须再次通过 ffprobe：774×1376、24fps、恰好 120 帧、视频与容器均恰好 5 秒、SAR=1，音轨不得超过 5 秒；视频及现存音轨均需完整解码。最后计算 SHA256、原子改名为 `<job>.mp4`，才在 SQLite 标记 `completed/verified=true` 并开放下载。

后处理失败仍保留已校验的原始文件与哈希，任务不会显示完成。`local_path`、`output_sha256`、`output_bytes`、`video_metadata` 和前端下载始终指向最终片；源文件使用独立字段，不把 5.1667 秒、124 帧的原始片当作严格 5 秒最终成片。默认 REAL 仍禁用；本流程不启动 GPU、不创建停机保护，也不修改模型工作流节点。

## 本轮验证边界

`tests/test_studio_real_api.py` 使用 `httpx.MockTransport` 模拟 ComfyUI，并用本机 ffmpeg 创建明确命名为 `LOCAL_CONTRACT_NOT_H3.mp4` 的蓝色测试片。测试验证默认禁用、审计过期、工作流哈希变化、跨域拒绝、并发防重、响应丢失与重启恢复、下载断网、坏视频拒绝和本地文件被篡改后拒绝服务；另验证 WorkSpaces 专属赠金与配额检查、账户资格、现金与赠金预算分开、资源/区域匹配，以及缺少 SSM 或任一停机核验时拒绝。所有通过门禁的测试数据只存在于临时目录，并连接本地模拟接口。它只证明接口与持久化逻辑，不证明 H3 推理成功、画面质量、真实显存、云端费用或停机措施有效。

后处理新增测试使用 800×1376、124 帧、24fps 的本机合成测试图视频，分别带合成音轨和不带音轨；验证断网恢复后仅提交一次、保留原始文件及哈希、严格 120 帧最终文件及哈希、无临时残留，并拒绝错误画幅/帧率/不足帧数与未知 preset。模拟后处理失败时保留 source 证据且拒绝下载最终片。这些视频均不是 H3 输出。

官方接口依据：

- https://github.com/Comfy-Org/ComfyUI/blob/master/server.py
- https://github.com/Comfy-Org/docs/blob/main/development/comfyui-server/comms_routes.mdx

部署前应锁定并复核实际 ComfyUI commit；本次未部署。
