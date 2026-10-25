# 本机 H3 Bridge 接入准备（未连接真实 H3）

## 当前结论

本次只完成独立本地工程：东京 GPU 配额为 0，用户决定不申请配额；没有创建 EC2、没有下载 H3 权重、没有运行真实 H3，也没有设置云端停机任务。真实模式的生成入口保持禁用，等待用户决定后续方案。

已有 8765 系统和 8767 Mock 服务不改。新服务仅监听 `127.0.0.1:8768`，复用当前 Grok Studio 编译结果。新服务没有 AWS SDK 调用，不持有 AWS 凭证，不创建/升级/启动/停止任何 AWS 资源。

## 本地查看

在已安装项目依赖的仓库中，由 `.venv/Scripts/python.exe` 运行 `scripts/run_studio_real.py`，浏览器打开 `http://127.0.0.1:8768/`。未配置人工审计文件和固定官方 API 工作流时，REAL 健康接口返回 `ready=false`；生成提交返回 403。本地上传和历史查看可以使用，不触发模型计算。

服务仅允许 ComfyUI 的 loopback HTTP 地址；默认 `http://127.0.0.1:8188`，未来由用户已有 SSM 会话转发。健康字段 `tunnel_connected` 只说明 ComfyUI HTTP 服务可达；`gpu_connected` 必须另有 `/system_stats` 报告 CUDA 设备且显存大于零。CPU-only 服务即使隧道连通，仍为 `gpu_connected=false`、`ready=false`，禁止上传上游和提交模型任务。GPU 设备信息本身不证明许可证、预算、目标实例型号或停机措施已经核验。

## 未来启用前的人工审计要求

运行配置使用 `ANIFLOW_REAL_DATA_DIR`、`ANIFLOW_COMFY_URL`、`ANIFLOW_REAL_GATE`、`ANIFLOW_H3_WORKFLOW`。此次没有生成可通过的 gate，也没有假造官方 H3 workflow。

人工 gate 必须逐项明确：EC2 赠金适用、赠金有效期、东京配额、容量价格、SSM 私有连接、H3 地域许可、主动停机和独立备用停机均通过；东京实例固定为 `g6e.2xlarge`，预算不超过 $20，运行时长不超过 14,400 秒，gate 剩余有效期不超过 4 小时。`launch_allowed` 必须为真；该字段只是既有核验结论，不会启动实例。gate 还必须绑定本地 workflow 文件的 SHA256。

工作流文件为固定 API-format bundle：`source_url` 指向 Comfy-Org 官方来源，`prompt` 保存经过人工核对的 API 节点，`bindings` 明确首帧、提示词以及可选负面提示词对应的节点和输入名。必须从官方 H3 工作流导出并记录源版本；Bridge 不猜 H3 节点、不下载模型、不把第三方 API 节点当本地 H3。SHA256 校验是防止本地工作流在审计后改变，不能代替人工核实来源和模型。

**Bridge 不实施云端定时停止。** 启用前必须在 AWS 另行落实并验证双重停机；人工文件声明不能代替真实停机措施。更换云区域、实例或 provider 必须先由用户决定。

## 可靠性与真实结果条件

- REAL 与 Mock 使用独立 API、SQLite 和目录。8768 不暴露 Mock 创建接口。
- 仅允许首轮一条 5 秒、9:16 任务。先持久化本机幂等编号，再发送一次 ComfyUI `/prompt`；相同编号只返回既有任务，不再次提交。未知结果和重启只查询 `/queue`、`/history` 中服务端保存的关联编号。找不到仍保持未知，不自动重发。
- 本机后台持续查询并自动下载，不依赖网页持续在线。下载中断只重试只读下载；不重新生成。尚未实现分块断点续传，重试会从头读取同一 MP4。
- MP4 写入 `.partial`；检查响应长度、容器、ffprobe、约 5 秒、短边至少 768、竖屏 9:16，以及 ffmpeg 全帧解码后才原子改名并显示完成。返回本机绝对路径、字节数、视频信息及 SHA256。再次下载时重新核对哈希。
- 显存峰值和 AWS 实际费用尚未接入可信采集源，均返回 `null`。`elapsed_seconds` 是 Bridge 提交至本地校验完成的端到端时间，不能当纯 GPU 推理时长。

## 本轮验证边界

`tests/test_studio_real_api.py` 使用 `httpx.MockTransport` 模拟 ComfyUI，并用本机 ffmpeg 创建明确命名为 `LOCAL_CONTRACT_NOT_H3.mp4` 的蓝色测试片。测试验证默认禁用、审计过期、工作流哈希变化、跨域拒绝、并发防重、响应丢失与重启恢复、下载断网、坏视频拒绝和本地文件被篡改后拒绝服务。它只证明接口与持久化逻辑，不证明 H3 推理成功、画面质量、真实显存、云端费用或停机措施有效。

官方接口依据：

- https://github.com/Comfy-Org/ComfyUI/blob/master/server.py
- https://github.com/Comfy-Org/docs/blob/main/development/comfyui-server/comms_routes.mdx

部署前应锁定并复核实际 ComfyUI commit；本次未部署。
