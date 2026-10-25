# AniFlow Studio Mock H3 合同（P0-035）

此阶段只在隔离审计分支验证，不运行 AWS、ComfyUI、Agnes 或付费服务。用户现有 `127.0.0.1:8765` AniFlow 不受影响。

运行方式：从仓库根目录安装已有 Python 依赖后，通过 `python scripts/run_studio_mock.py` 在 `127.0.0.1:8767` 启动**独立模拟服务**。

API 合同：`GET /api/studio/mock/health`；`POST /api/studio/mock/assets` 接收最大10MB的PNG/JPG并保存为 SHA256 内容地址；`POST /api/studio/mock/jobs` 使用 `idempotency_key` 显式创建（只能 `provider=mock-h3`）；`GET /api/studio/mock/jobs/{id}` 查询；`GET /api/studio/mock/jobs` 列表；`GET /api/studio/mock/jobs/{id}/video` 下载本机合成测试 MP4。

状态：提交后1秒内排队、1–6秒生成模拟进度、6秒后使用已有测试蓝色视频假文件完成并在本机磁盘落盘，SHA256校验。所有响应均有 `simulation:true`、`actual_cost_usd:0`、`gpu_connected:false`。文件名含 `MOCK`，不得说成模型生成成功。任务与图片保存在 `data/runtime/studio`，用 SQLite 跨服务重启持久化；不会将 Base64 上传图塞进浏览器 localStorage。

Mock 仅验证工程链路，不表示 L40S 能运行 H3、模型权重许可证有效、图生视频质量达标、费用低于某数值或已成功连接AWS。

后续接入 Grok 视觉前台时，必须保留**演示模式与真实模式显式隔离**。真实 `/api/studio/*` 未来才会实现 ComfyUI/AWS 的状态查询、提交和分块下载；需新的独立开发与真实设备验收，严禁模拟计时器在 REAL 模式假报已完成。

测试：`pytest -q tests/test_studio_mock_api.py`；CI 不读取 API Key，不安装/启动 AWS，不产生实际视频推理费用。

## 阶段验收

2026-10-25：Grok工程副本现已实际连接该Mock Bridge并独立托管在8767，已用真实Chromium端到端验证上传、进度、下载、SHA256和刷新历史。[CI #40152956282](https://github.com/wpuu/AniFlow/actions/runs/40152956282) 全部5项独立审计作业通过。真实GPU与AWS仍为0次调用；正式应用 v0.34.2 在另一PR #2，尚未合并到本分支。
