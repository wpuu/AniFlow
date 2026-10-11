# AniFlow｜现有 9-Key Agnes 视频前端实际试用（P0-020）

- 核验日期：2026-10-11，UTC+8（北京时间）
- 隔离分支：`audit/2026-10-11-v710-revalidation`；PR #2 继续 Draft，不合并 main
- **这是已有 `apps/grok-frontend/` 的实际操作卡，不是开发新平台。**
- 适用范围：自己的可信 Windows 浏览器，持有合法权限的 Agnes API Key；本轮只修改前端兼容字段，**未生成任何真实视频**。

## A. 从现有应用启动

**如果你的 Windows 已安装这份仓库：**

1. 确保使用的是本隔离分支的最新代码（旧 main 不含本轮修复）；勿直接覆盖自己另行配置的工作目录或删除旧 `.env`。
2. 以前已完成安装的，双击仓库根目录的 `启动AniFlow.cmd`。
3. 浏览器打开 **http://127.0.0.1:8765/**，页面标题应是“**AniFlow 动画工厂**”。
4. 如果仍显示旧页面，先退出旧进程，并在本隔离分支运行一次 `首次安装AniFlow.cmd` 重新构建本地前端，然后启动。不要在已经占用 8765 端口时再并行开一个实例。

**如果 Windows 还没有该仓库：**

1. 打开 [隔离分支](https://github.com/wpuu/AniFlow/tree/audit/2026-10-11-v710-revalidation)，点 **Code → Download ZIP**，解压到可信本机新目录；不要使用 main 的旧 ZIP。
2. 需有 Python 3.11+、Node.js/npm。双击根目录 `首次安装AniFlow.cmd` 安装 Python/NPM 依赖并构建前端，再双击 `启动AniFlow.cmd`。
3. 正常入口仍为 **http://127.0.0.1:8765/**。这是**本机地址**，不是已经部署的公网网址。
4. **文生视频**不必先配置 R2/S3、图片上传或 CapCut。若想上传本地角色首帧，才需要配置 Bridge 的合法公网图片存储；暂不要为了第一条视频先折腾媒体服务。

## B. 页面内如何测 1～9 个 Key

1. **视频模型明确选 `Agnes Video 2.5 Flash`**。新浏览器默认已经改为 Flash，但旧浏览器保存的 V2.0 设置不会被覆盖，仍需核对。勿选旧 `Agnes Video V2.0`。
2. 在 **API Key 设置**将数量改为 `9`（或实际持有的数量），逐条输入自己的合法授权 Key。它们保存于本浏览器 `localStorage`；不要在共享设备操作，也不要向 Issue、PR、聊天或公开日志粘贴。
3. 选择 **文生视频**、`9:16`、`720P`、`5秒`。这种测试无需上传首帧，是验证 Key/队列与文字生成的最快方法。
4. 将下方冻结镜头 1 提示词粘贴到输入框（英文保留角色特征，不改故事）。
5. 单击某个 **“生成视频 · Key1”** 可以单 Key 测通流程；如果你要直接测多 Key，可点击 **“一键生成全部可用 Key”**——当前实现对**每条已填写且空闲的 Key 最多发一次生成创建请求**，因此 9 个空闲 Key 就会有**最多 9 个外部 POST**。**不是“检查是否可用”按钮；实际可能创建 9 条视频任务**。点之前应先查看本人账户当前计费状态/使用条款。
6. 页面右侧按 **Key1…Key9** 切换查看各自排队、完成或失败状态，以及生成视频链接和历史。**停止跟踪只停止浏览器 GET 轮询，不取消供应商服务器上的生成任务。**
7. **提交请求超时、断网、刷新页面或显示失败时不要直接重新点“生成全部”**：先检查各 Key 本地历史及供应商任务记录。前端没有跨浏览器/跨目录的全局防重发账本，旧任务可能已创建而新页面不知道。

### 首集镜头 1 原文提示词

```text
handmade needle-felt stop-motion miniature diorama, visible wool fiber texture, soft warm studio light, shallow depth of field, tactile handmade feel. needle-felted American Shorthair cat, silver tabby with dark classic swirl markings, round amber eyes, tiny white lab coat with two buttons, visible wool fiber texture, handmade miniature puppet. medium shot, cat centered, bowl in lower third; sitting upright beside a small ceramic water bowl, looking straight at camera, ears forward; miniature felt kitchen counter, tiny felt window with warm morning light behind. the felt cat sits still beside the bowl, blinks once slowly, then tilts its head toward the camera. slow push in. medium shot, same framing, slightly closer; head tilted to one side, eyes half closed mid-blink, chin visibly dry and clean; same felt kitchen counter, same warm light
```

来源：[MYCL-001 锁定分镜表](https://github.com/wpuu/AniFlow/blob/audit/2026-10-11-v710-revalidation/content/shotlists/MYCL-001-cat-lapping.json) 与 [Issue #6](https://github.com/wpuu/AniFlow/issues/6)。8镜头46秒仍保持锁定；目前只测第一镜头5秒。

## C. 本轮修复为何必须使用隔离分支

- **官方 Agnes Video 2.5 Flash [最新 API 文档](https://wiki.agnes-ai.com/zh-Hans/docs/agnes-video-25-flash)**：完成时从响应顶层 `url` 获取视频；旧前端仅读 `metadata.url`，可能“生成成功但无预览”。
- 本分支前端已改为**优先读取 `url`，兼容旧 `metadata.url`**；正常轮询与手动刷新历史两处都修复。
- 新浏览器模型默认改为 Flash；旧浏览器若已持久化选用 V2.0，保留原设置但须人工选择 Flash。
- Agnes 接口 `detail` 错误字段现在会显示出来，便于看到服务端队列满等异常。
- 前端当前视频 API 地址固定为 **https://apihub.agnes-ai.com**（国际站）；没有确认中国区 Key 可复用在该域名，请勿自动换区域重复提交。
- 这份 9-Key 前端只是本地自用并行提交 UI，不是上游视频产能 SLA；共享队列可能使 9 Key 一起请求依旧全部排队或返回 503。

## D. 试验后保留什么

- 不用给我 Key。仅汇报 9 条中“成功创建、队列满/503、已完成、已失败”的数量，首条从点击到成片的时间；若有 MP4，**先下载到你自己的私有目录**，记录实际横竖像素、时长和雪所长角色/眨眼/歪头的视觉结果。
- 可贴**不含 Key 的页面截图**和错误文本，但避免截图显示浏览器内 Key 或后台额度等敏感信息。
- 文生视频即使成功，也**不等于**本项目已通过定妆首帧、人物一致性、科学动作、配音、商用许可和整集验收。

## 未完成/禁止误报

本轮没有用用户 Key 执行 API；没有真实 `video_id`、MP4 或账户账单；不部署、不发布、不合并 main、不启用旧版 `scripts/安装视频工作台.bat`（该脚本固定上游 v7.0.4）。用户手动点击一键生成是单独、可见的外部动作，不要被解释为已经在聊天里自动执行了生成。
