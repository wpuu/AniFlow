# AniFlow P0-033｜Agnes 首镜头恢复与长期免费图生视频事实审计

日期：2026-10-12（北京时间）｜目标版本：v0.33.0｜仅隔离 PR #2

## 本轮解决的问题

1. **已取得 video_id 后的状态查询**：之前只在数次读取错误后就中断，且前端错误丢失 HTTP 状态码。现在将 HTTP 404/408/429/500/502/503/504/520 或临时网络错误识别为仅用于 **GET 状态查询** 的可恢复故障。受限最长20分钟，404间隔12秒、429间隔30秒、5xx间隔25秒、正常状态轮询间隔6秒。过期、明确失效或人工停止时保留原 video_id；**不会发第二个视频创建 POST**。这些间隔/20分钟上限是 AniFlow 内部保守策略，不是 Agnes 官方 SLA。
2. **页面刷新后已受理任务**：只恢复历史中拥有 video_id 且仍在 queued/in_progress 的任务的只读轮询，不自动重试缺失编号的提交，也不重启已手动停止的任务。手动点击历史刷新仍只读取一次原任务状态。
3. **图生视频标准输入入口**：新增「公开首帧图生测试 · 5秒」按钮，只填原仓库已经公开的角色 PNG HTTPS URL、i2v/keyframe、720P/9:16/5秒和专门针对该 PNG 现有姿势的动作提示词。**此 PNG 不具备已验收的水碗构图，不是 MYCL-001 正式首镜头**；仅用于排除本地 Base64 Data URI 兼容性变量。首次点击预设不会提交真实视频，用户再次点击生成按钮才会创建。
4. **本地图片仍保留实验功能**，但 Agnes 官方仅明确支持可公开访问且任务期间有效的图片 URL，没有承诺 data:image/... Base64 兼容；因此本地文件直传不能计入“图生视频真实可用”验收。也不能为了方便而要求用户必然开通付费 R2。

## Agnes 公开事实与测试边界

- 官方 Video 2.5 Flash：mode=keyframe 时 first_frame/last_frame 使用图片 URL；mode=reference 的 images 为图片 URL；媒体在服务端必须可达且持续有效：https://wiki.agnes-ai.com/zh-Hans/docs/agnes-video-25-flash
- 上游仓库 Issue #63 2026-09-20 记录业务响应 code=video_queue_full 时任务在提交阶段就被拒，不应当作已排队：https://github.com/lcy362/agnes-video-generator/issues/63
- 上游 Issue #77 说明公共体验站存在共享 Key 限速，自己的本地 Bridge+自己的 Key 只能排除体验站拥堵，**不能消除 Agnes 供应商上游 GPU 队列容量不足**：https://github.com/lcy362/agnes-video-generator/issues/77
- 第三方 openhanako Issue #1724 曾将 task_id 误作 video_id 引起查询404；AniFlow 当前按官方使用 video_id，不能由该旧案直接证明所有404都是延迟。实际遇404先核编号，再按本轮只读有限恢复逻辑处理：https://github.com/liliMozi/openhanako/issues/1724

## 长期免费图生视频备用方案：仅证实额度，尚未集成

- Hugging Face ZeroGPU 官方免费账号 5 分钟**每天 GPU 时间**，无登录为2分钟；不是每天5分钟成品视频；官方允许通过 Gradio Client 调用共享 Space。免费政策、可用性、实际队列随平台变化：https://huggingface.co/docs/hub/spaces-zerogpu https://huggingface.co/docs/hub/en/spaces-api-endpoints
- 具体候选 zerogpu-aoti/wan2-2-fp8da-aoti-faster 的公开 app.py 使用 Wan2.2 I2V、图像+prompt+negative_prompt 输入，公开 Space 目前有 Gradio API；最大80帧、16fps，可用于约5秒试验，受每日 GPU 配额和启动耗时限制：https://huggingface.co/spaces/zerogpu-aoti/wan2-2-fp8da-aoti-faster/blob/main/app.py
- 尚未验证：用户 HF 账户额度、此 Space 能否从用户所在网络成功API请求、启动耗时、5秒输出真实质量/版权/稳定性；**不注册账号、不提交视频、不在任何公共 GitHub CI 注入 Token**。在有真实样片前不把 ZeroGPU 适配列为“可生产”。

## 真实验收仍缺失

用户截图曾显示 Key2 可播放猫视频，但这仅证明用户侧观察；缺该视频的原始 video_id、SHA256、真实时长/画幅、成本和毛毡画质验收。其他8条 Key 的HTTP错误分布尚未收到脱敏数据。P0-033 的 Chrome E2E 使用虚构 Key 和本地假视频验证逻辑，**真实 Agnes 请求数=0**。这次修复能减少误判/重复创建，不会凭空增加供应商的上游 GPU 容量。

## 版本与权限

按 AGENTS.md 更新 version.json、pyproject、前端 package 与 lock 为 0.33.0；生成带版本的 Windows Artifact 必须经 Linux/Windows/Python/TypeScript/Chromium/安全启动 CI 全绿。隔离分支推进，不合并 main，不使用真实 Key、不发起付费或无限次生成，不改先前通过的 8 镜头 46 秒冻结内容。
