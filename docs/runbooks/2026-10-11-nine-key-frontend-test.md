# AniFlow｜现有 9-Key Agnes 视频前端实际试用（P0-020）

## P0-029｜每次显示旧版本：新包一键重启（2026-10-12）

1. **根因一：GitHub 仓库默认 `main` 还是旧版。** 不要在 [AniFlow 仓库首页](https://github.com/wpuu/AniFlow) 直接点 `Code → Download ZIP`；那是 `main` 旧代码。正确来源是 [PR #2](https://github.com/wpuu/AniFlow/pull/2) 中最新 **SUCCESS** 的 GitHub Actions CI，在 `Artifacts` 下载名称为 `AniFlow-9Key-Windows-<完整SHA>` 的 ZIP（不是 `internal-compiled-nine-key-ui` 中间产物）。
2. **根因二：旧版服务仍监听 `127.0.0.1:8765`。** 新 ZIP 解压到独立、好辨认的本地目录，如 `C:\AniFlow-current`（**不要混合覆盖旧文件**）。首次运行 `首次安装AniFlow.cmd`；以后每次**只双击 `一键重启当前AniFlow.cmd`**。
3. 新脚本会检查包内 `prebuilt_frontend.json` 与编译HTML哈希、识别8765端口实际所属进程，**只停止能确认是 AniFlow Bridge 的旧进程**；其他程序绝不误杀。随后只启动本目录的新Bridge，调用 `/api/version` 对比活动SHA，匹配后才打开浏览器并带版本查询串避免缓存旧HTML。
4. 新版网页底部应显示“**正在运行版本：xxxxxxxxxxxx**”。与脚本窗口打印的版本一致即可；无需重复“部署”，更不用清空浏览器 Key、localStorage、历史或任务。注意 `localhost:8765` 与 `127.0.0.1:8765` 的浏览器存储**互相独立**，不要随意切换域名。
5. 脚本**不会自动下载 GitHub 新版**，所以每次换版本仍要手动下载最新成功的 Artifact 并解压完整文件夹；也不会取消 Agnes 供应商的已创建视频任务、GitHub CI、Vercel 部署或其他后台程序。遇到外来进程占用8765，会停下显示PID，请人工确认后关闭；不要执行粗暴的 `taskkill /F /IM python.exe`。
6. 如报错“Missing prebuilt_frontend.json”，表明你现在运行的不是有效CI Windows包。旧 ZIP 的 `启动AniFlow.cmd` 不会自动变成新版。按本步骤下载新版后，用新版的 `一键重启当前AniFlow.cmd`。

**无真实密钥测试范围**：GitHub Windows CI 负责跑两次启动/重启 + 活动SHA+网页不缓存的验证，不代表 Agnes 真视频已成功。


- 核验日期：2026-10-11，UTC+8（北京时间）
- 隔离分支：`audit/2026-10-11-v710-revalidation`；PR #2 继续 Draft，不合并 main
- **这是已有 `apps/grok-frontend/` 的实际操作卡，不是开发新平台。**
- 适用范围：自己的可信 Windows 浏览器，持有合法权限的 Agnes API Key；本轮仅做无 Key 模拟和真实浏览器跨域试验，**未生成任何真实视频**。

> **P0-025 本机 Bridge 访问防护：** 已新增精确 Host 白名单，阻断域名重新绑定（DNS rebinding）访问。只允许 `localhost`、`127.0.0.1` 和仅用于测试的 `testserver` 名称；外部网页 Origin 的预检依旧不放行。此为无 Key 的接口安全检查，不证明真实视频出片。新增 `scripts/one_agnes_real_shot.py` 的 CI 纯预览门槛，只验证 `PLAN_ONLY_NO_REQUESTS` / `submissions=0`。
>
> **云端约束：** 现有 `AGNES_API_KEYS` 曾在 GitHub Actions 旧作业中被判定为非空，但并不等于 Codespaces 中已有 `ANIFLOW_SINGLE_SHOT_API_KEY`。GitHub 的 `workflow_dispatch` 要求对应工作流已存在于默认分支；当前隔离分支内的设计不能凭空变成手机端可执行的正式入口，且在公开仓库中把私有 MP4 上传为可访问的构建产物不是默认安全交付方式。真实试片仍需明确单次许可与私有输出方案。
>
> **P0-021 必须使用最新本地 Bridge：** 官方 Agnes 的 OPTIONS 请求返回 HTTP 204 和通用 CORS 头，但 [Chrome 真浏览器测试](https://github.com/wpuu/AniFlow/actions/runs/38152367310) 发现带 Authorization 的跨域请求仍被阻止，符合 [MDN 对 Authorization 必须显式允许的说明](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Headers)。已在**原 AniFlow 本机 Bridge**增加视频请求转发，浏览器只向 `http://127.0.0.1:8765` 发送请求，由本机一次转发给 Agnes。**不是新平台，不装第二套应用，也没有服务端自动重试**。旧 main 和仅打开孤立 index.html 的用法不具备这一修复。

## A. 从现有应用启动

**如果你的 Windows 已安装这份仓库：**

1. 确保使用的是本隔离分支的最新代码（旧 main 不含本轮修复）；勿直接覆盖自己另行配置的工作目录或删除旧 `.env`。
2. 已安装旧版的也需要先在本隔离分支运行一次根目录的 `首次安装AniFlow.cmd`（更新 Python 编辑安装、重新构建前端），再双击 `启动AniFlow.cmd`。
3. 浏览器打开 **http://127.0.0.1:8765/**，页面标题应是“**AniFlow 动画工厂**”。
4. 如果仍显示旧页面，先退出旧服务进程，重新从本隔离分支构建。新版文本视频转发必须由**新版本机 Bridge**提供；不要只替换 HTML。不要在已经占用 8765 端口时再并行开一个实例。

**如果 Windows 还没有该仓库：**

1. 打开 [隔离分支](https://github.com/wpuu/AniFlow/tree/audit/2026-10-11-v710-revalidation)，点 **Code → Download ZIP**，解压到可信本机新目录；不要使用 main 的旧 ZIP。
2. 需有 Python 3.11+、Node.js/npm。双击根目录 `首次安装AniFlow.cmd` 安装 Python/NPM 依赖并构建前端，再双击 `启动AniFlow.cmd`。
3. 正常入口仍为 **http://127.0.0.1:8765/**。这是**本机地址**，不是已经部署的公网网址。
4. **文生视频**不必先配置 R2/S3、图片上传或 CapCut。若想上传本地角色首帧，才需要配置 Bridge 的合法公网图片存储；暂不要为了第一条视频先折腾媒体服务。

## B. 页面内如何测 1～9 个 Key

1. **视频模型明确选 `Agnes Video 2.5 Flash`**。新浏览器默认已经改为 Flash，但旧浏览器保存的 V2.0 设置不会被覆盖，仍需核对。勿选旧 `Agnes Video V2.0`。
2. 在 **API Key 设置**将数量改为 `9`（或实际持有的数量），逐条输入自己的合法授权 Key。它们保存于本浏览器 `localStorage`；不要在共享设备操作，也不要向 Issue、PR、聊天或公开日志粘贴。
3. 选择 **文生视频**、`9:16`、`720P`、`5秒`。这种测试无需上传首帧，是验证 Key/队列与文字生成的最快方法。
4. 在 `Agnes Video 2.5 Flash` 模型的**提示词区**，点击 **“载入雪所长首镜头 · 5秒”**，自动填入已冻结的850字符英文提示词、文生、9:16、720P与5秒设置；**此按钮只填参数，不发送请求**。也可手动复制下方原文。
5. 单击某个 **“生成视频 · Key1”** 可以单 Key 测通流程；如果你要直接测多 Key，可点击 **“一键生成全部可用 Key”**——当前实现对**每条已填写且空闲的 Key 最多发一次生成创建请求**，因此 9 个空闲 Key 就会有**最多 9 个外部 POST**。**不是“检查是否可用”按钮；实际可能创建 9 条视频任务**。点之前应先查看本人账户当前计费状态/使用条款。
6. 页面右侧按 **Key1…Key9** 切换查看各自排队、完成或失败状态，以及生成视频链接和历史。**停止跟踪只停止浏览器 GET 轮询，不取消供应商服务器上的生成任务。**
7. **提交请求超时、断网、刷新页面或显示失败时不要直接重新点“生成全部”**：新版会在发送视频 POST 之前，将每个 Key 的本次尝试 ID 持久写到**当前浏览器的 localStorage 安全锁**；如果收不到确认，会标记“提交结果待核实”，禁用再次创建。刷新页面后可以在黄色提示中选择**“继续查原任务”**（仅查询，不创建）或**“人工核实后解锁”**。没有 `video_id` 时只能先登录 Agnes 账号查原任务。安全锁不能跨不同浏览器、机器或旧版前端，不能因为换设备而重复发送。

### 首集镜头 1 原文提示词

```text
handmade needle-felt stop-motion miniature diorama, visible wool fiber texture, soft warm studio light, shallow depth of field, tactile handmade feel. needle-felted American Shorthair cat, silver tabby with dark classic swirl markings, round amber eyes, tiny white lab coat with two buttons, visible wool fiber texture, handmade miniature puppet. medium shot, cat centered, bowl in lower third; sitting upright beside a small ceramic water bowl, looking straight at camera, ears forward; miniature felt kitchen counter, tiny felt window with warm morning light behind. the felt cat sits still beside the bowl, blinks once slowly, then tilts its head toward the camera. slow push in. medium shot, same framing, slightly closer; head tilted to one side, eyes half closed mid-blink, chin visibly dry and clean; same felt kitchen counter, same warm light
```

来源：[MYCL-001 锁定分镜表](https://github.com/wpuu/AniFlow/blob/audit/2026-10-11-v710-revalidation/content/shotlists/MYCL-001-cat-lapping.json) 与 [Issue #6](https://github.com/wpuu/AniFlow/issues/6)。8镜头46秒仍保持锁定；目前只测第一镜头5秒。

### 可选试验：Agnes 原生角色参考图（与首帧锁定不同）

- Agnes Video 2.5 Flash 官方支持 `mode=reference` 配 `images`，最多5张参考图片。本次9-Key原应用先支持**一张公开角色图片**，并非重建平台。
- 页面在 Agnes Video 2.5 Flash 下可点击 **「载入角色参考图测试 · 5秒」**，自动填写已有银虎斑白大褂素材的固定 GitHub 原图链接、`mode=reference` 和 `<Picture 1>` 指令；要求模型保持角色造型、但**不要复制原图站姿和厨房家电，应出现水碗与坐姿**。此按钮只填参数，**不会创建视频任务**。
- [参考素材](https://github.com/wpuu/AniFlow/blob/main/assets/character/agnes-felt-test-frame.png) 未通过第1镜头首帧验收，只有“角色参考图”实验价值；**授权归属和最终视觉一致性尚未核实，不可直接将输出作为商用成片**。8镜头46秒冻结原文不被覆盖，这是一种额外的实验生成提示词。
- 因使用的是固定公共 HTTPS GitHub Raw URL，**本次角色参考图试验不需 R2**。用户上传本地图片仍需要通过现有 Bridge 上传到可公开访问的媒体存储。
- 先单 Key、单镜头测试文生视频，把真实 `video_id` 和 MP4 回收完成；再经过费用确认、保留新的唯一任务证据后，才考虑单 Key 参考图模式。避免同一次点击触发9条重复收费任务。
- 页面新增 **「复制9-Key安全测试摘要」**，只复制数量、状态、错误分类和实际时间，不含 API Key、提示词、任务 ID、视频 URL、原始错误正文。
- 官方接口说明：https://wiki.agnes-ai.com/zh-Hans/docs/agnes-video-25-flash

## C. 本轮修复为何必须使用隔离分支

- **官方 Agnes Video 2.5 Flash [最新 API 文档](https://wiki.agnes-ai.com/zh-Hans/docs/agnes-video-25-flash)**：完成时从响应顶层 `url` 获取视频；旧前端仅读 `metadata.url`，可能“生成成功但无预览”。
- 本分支前端已改为**优先读取 `url`，兼容旧 `metadata.url`**；正常轮询与手动刷新历史两处都修复。
- 新浏览器模型默认改为 Flash；旧浏览器若已持久化选用 V2.0，保留原设置但须人工选择 Flash。
- Agnes 接口 `detail` 错误字段现在会显示出来，便于看到服务端队列满等异常。
- 新前端的视频请求只发到本机 **http://127.0.0.1:8765/api/video/** 路由。本机 Bridge 默认转发国际站 **https://apihub.agnes-ai.com**，可由合法本机环境配置 `AGNES_API_ROOT` 指定其他实际授权的 Agnes 服务区域；不自动切区域、不读不同账号的 Key。
- 这份 9-Key 前端只是本地自用并行提交 UI，不是上游视频产能 SLA；共享队列可能使 9 Key 一起请求依旧全部排队或返回 503。

## D. 试验后保留什么

- 不用给我 Key。仅汇报 9 条中“成功创建、队列满/503、已完成、已失败”的数量，首条从点击到成片的时间；若有 MP4，**先下载到你自己的私有目录**，记录实际横竖像素、时长和雪所长角色/眨眼/歪头的视觉结果。
- 可贴**不含 Key 的页面截图**和错误文本，但避免截图显示浏览器内 Key 或后台额度等敏感信息。
- 文生视频即使成功，也**不等于**本项目已通过定妆首帧、人物一致性、科学动作、配音、商用许可和整集验收。

## 未完成/禁止误报

本轮没有用用户 Key 执行 API；没有真实 `video_id`、MP4 或账户账单；不部署、不发布、不合并 main、不启用旧版 `scripts/安装视频工作台.bat`（该脚本固定上游 v7.0.4）。用户手动点击一键生成是单独、可见的外部动作，不要被解释为已经在聊天里自动执行了生成。
