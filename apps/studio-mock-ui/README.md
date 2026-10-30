# AniFlow Studio Mock UI (P0-035)

这是基于 Grok 原版界面制作的**独立工程集成副本**。原始 ZIP 与 `apps/studio-candidate-grok/` 完全保留不变；当前生产用的 AniFlow 8765 不会被替换。

**只连本机模拟服务，没有 AWS / ComfyUI / Agnes 真实 API。**

本地验证（仓库根目录）：

```
cd apps/studio-mock-ui
npm ci
npm run build
cd ../..
python scripts/run_studio_mock.py
```

然后使用 `http://127.0.0.1:8767/`，选择**电脑本地 PNG/JPG**首帧，输入提示词，点击生成。后台 SQLite 自动记录任务，约6秒完成一个原仓库**蓝色模拟视频**，保存于 `data/runtime/studio/videos/`，并在前台可播放/下载。断线刷新后读取原始任务编号，重复创建有幂等键保护；不需要真实 GPU。HTTP 状态不使用 Grok 原版随机模拟计时器。

`src/data.ts` 只暴露 MOCK 模型；不显示虚假的 AWS 在线状态与计价。原始文本+Logo资产在仓库根目录的 Grok ZIP 中，Mock服务可从 ZIP 原样读取 Logo，不上传外部服务。不删除当前系统任何视频或密钥。浏览器仅保存“从列表隐藏”的 ID，不保存图像Base64与任务资料。

这里实现的是**Mock工程通路**，尚未连接真实 H3/ComfyUI、AWS EC2、SSM、自动关机，也不代表真实5秒图生视频成功。任何 AWS 的实际创建、启动、消费都需要重新做预算/实例/许可与显存核验并经用户允许。

验收证据：[2026-10-25 Mock Studio CI](https://github.com/wpuu/AniFlow/actions/runs/40152956282)，包括真实Chromium首帧上传、任务创建、下载的Mock MP4哈希验证和刷新后任务恢复。独立实验目录；不得当成真实AWS部署包。

## P0-036 提交可靠性

提交前在浏览器持久保留**只有请求编号和时间戳**的防重复保护；若服务器已接受但浏览器丢失响应，不自动重发视频创建请求。页面会显示“查询原任务”只读操作；无法确认则停止新提交，除非用户明确同意放弃保护。SQLite 通过 `GET /api/studio/mock/requests/{idempotency_key}` 找回受理记录。详细情况见 `docs/reviews/2026-10-25-p0036-unknown-submission-hardening.md`。依然只生成蓝色视频假样片，不开AWS。

## P0-037 AWS东京预检入口（仍为纯本机模拟）

Studio 顶部新增「AWS 东京 H3：部署前资格核验（未连接）」入口。通过本机只读 `GET /api/studio/cloud/preflight` 获取未核验状态。赠金适用EC2、截止时间和余额、G/VT配额、实例库存/报价、SSM私有连接、H3地域许可、强制停机措施均在无真实AWS连接时明确显示“未核验”。不写入或传输 AWS 密钥，UI 不能创建、启动或停止EC2，不能把历史赠金数字当作实时余额。

下一步需要 ChatGPT Work + 用户授权的已登录 Ego 浏览器读取真实AWS账户核验页面。浏览器权限不可用时停止云操作；详见 `docs/runbooks/2026-10-25-aws-tokyo-h3-work-handoff.md`。原有两份ZIP、8765应用与真实AWS均未修改。

## 受控真实 H3 服务接入

同一份前端现在也可由独立的本机真实 Bridge（8768）托管。默认仍选中 Mock，用户必须显式选择「真实 H3」；模式与当前本机服务不符时提示打开对应的 8767 / 8768 服务并禁止提交。页面不会跨域调用另一个端口，也不会创建、启动或升级 AWS 账户。

真实 Bridge 默认关闭生成。前端读取 `/api/studio/real/health`，只有服务身份匹配且 `ready=true` 才启用按钮；服务还须在创建请求时重新校验人工审计、配额、官方工作流和双重停机保护。当前东京配额不足，不能把这个工程接入当作已连接真实 GPU。

真实历史走独立 `/api/studio/real/*`，请求保护与隐藏列表使用 `aniflow.real.*` 存储键；Mock 继续使用原来的 `aniflow.mock.*` 键。浏览器刷新或提交响应丢失后仅查询原任务，不自动重发生成。下载与完整性检查由 Windows 本机 Bridge 执行，不依赖浏览器持续在线。

真实结果只有 `completed`、`verified=true`、本机路径、SHA256、正数文件大小和有效 MP4 元数据同时具备时才显示完成。下载校验中和提交待确认有独立状态。详情展示 ComfyUI prompt_id、本机路径、SHA256、尺寸/时长、耗时和显存；没有实测数据的费用、进度、ETA、显存保持「未测」。单次实验表单固定 5 秒 / 9:16。

本地验证：`npx tsc --noEmit`、`npm run build`、`node --test tests/real-contract.test.cjs`。后者只检验前端响应契约与真/假隔离，**不生成 H3 视频**。原有 Mock 浏览器 E2E 仍在仓库根目录 `scripts/e2e_studio_mock_ui.py`。
