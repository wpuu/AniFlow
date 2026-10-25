# AniFlow 前台双 ZIP 独立审计（2026-10-25）

审计对象：仓库 main 提交 `54ef213e1705e714edf1b9250a2226bc4bb9c4a9` 的两个原始 ZIP：
- Claude：`aniflow-ai-video-dashboard-claude.zip`（1,409,211 字节；源ZIP SHA256: `ea0ec7bfbb2c739f1a10a0e293f2e958018d4cb4a50eb3414fa82a06ff7203fc`）
- Grok：`aniflow-ai-video-dashboard-grok.zip`（1,232,520 字节；源ZIP SHA256: `6054585323ab1ae52c0e25dd73dd4043bd1f57d7e421124e18ea90330c4b56ae`）

代码审计：PR #7 的 [ZIP 静态审计 CI #40151215696](https://github.com/wpuu/AniFlow/actions/runs/40151215696)，对 ZIP 直接读取、检查路径和源码，不执行内容。另于 [CI #40151638299](https://github.com/wpuu/AniFlow/actions/runs/40151638299) 用独立临时工作区运行：两份 `npm ci`、严格 `tsc --noEmit`、`vite build` 全通过。没有访问 AWS、Agnes、GPU 或真实视频 API。

## 结论

**选 Grok 作视觉/交互主参考；保留 Claude 的 ModelStatusBar、StatsRow 和 ParamsModal 思路。两份均不是可接入 AWS H3 的功能成品，不得直接替换 AniFlow 现有代码。**

| 维度 | Claude | Grok | 结论 |
| --- | --- | --- | --- |
| 组件组织 | 12 TSX；App 管理状态和模拟任务 | 8 TSX + 独立 `useTaskEngine` | Grok 任务逻辑边界较清楚 |
| 首帧 | 选择上传；图像预览 | 拖拽/点击上传、预设图片、预览 | Grok 交互更方便 |
| 视频参数 | Prompt、Negative、模型、比例、时长、随机 seed | 另有 seed、FPS、CFG、motion、提示词预设 | Grok 功能更完整，实际可用参数要按 Provider 契约过滤 |
| 任务历史 | 页面状态为主，没有检出持久化 | `localStorage` 最多保存40个附加任务 | Grok较好但不安全、不能作为正式数据库 |
| 下载 | HTML `download` 外部视频 | `fetch` 外部MP4、Blob 下载或新标签 | 都不是 Windows 指定文件夹的自动保存 |
| 模型状态/计费 | 假在线、延迟、队列、成本 | 假在线、延迟、队列、成本 | **两者均不得显示为真实值** |
| 后端连接 | 无真实 ComfyUI/AWS Bridge 调用 | 无真实 ComfyUI/AWS Bridge 调用 | 均需另建适配 |
| TypeScript/Vite | 均通过 | 均通过 | 不能以可编译等同于真实功能 |

## 发现的严重风险

1. **假成功**：Claude `src/App.tsx` 用计时器每秒推进模拟任务，到100%后随机回传 MDN flower.mp4 等示例视频；Grok `src/hooks/useTaskEngine.ts` 每420ms推进 `queued → running → done` 并回传 Pexels 示例视频。两个页面都可能在未调用 GPU 时显示“已完成”。
2. **假余额/性能**：Claude `src/data/models.ts` 和 Grok `src/data.ts` 都硬编码提供商在线状态、延迟、每秒价格。不能当成 AWS 实际计价、实例状态或模型可用性证明。
3. **Grok 本地缓存风险**：`persist()` 将附加任务切到最多40条并持续写 `localStorage`；`firstFrame` 可能是图片 Base64，大文件会触发配额、写入失败或重复存储。刷新页面重新合入固定演示任务；正式任务不能依赖此结构。
4. **缺少安全状态机**：均无持久服务器任务ID、提交幂等锁、断线恢复、取消与“停止跟踪”的语义分离、上游错误分类、重复收费请求保护。
5. **缺少 GPU/资金防护**：无 AWS IAM/SSM、EC2 配额检查、GPU实例计费计时、预算硬门、空闲确认后关机、文件回传 SHA256 与磁盘安全路径。
6. **不是本地图生闭环**：上传图片仅在浏览器端读为 Data URI；并未接 ComfyUI 的 `/upload/image`、`/prompt`、`/history`、`/view`，也没有 Windows Bridge 自动保存完整 MP4 与 FFprobe 验证。
7. **模型名称和产品规格均为生成示例**：尤其 H3 / Agnes 的版本、免费政策、视频时长上限、授权许可等，必须在真正部署前按官方权重和 ComfyUI 工作流重新核对，不能复用两份 ZIP 的硬编码标签当事实。

## 安全推进方案（先 Mock、后 AWS）

先保留原始 ZIP 和当前视频 Bridge。新目录 `apps/studio-candidate-grok/` 仅放 Grok 的原始文本源码快照，不直接上线。二进制 Logo 由 `scripts/stage_grok_logo.py` 从原 ZIP 原样恢复，不重新生成图片。

下一工程阶段在隔离分支开发正式 AniFlow Studio 而不是修改上面的基线，先验证：
- Provider 中立的 `create/status/cancel/download` 合同；真实/Mock 任务必须可区分，Mock 默认禁止宣传为真实生成。
- Windows 本机 SQLite 任务库：持久 `task_id`、来源、创建前请求ID、任务历史、失败分类、手动批准的重试。图片本机路径与哈希单独保存，**不写 Base64 到 localStorage**。
- ComfyUI Mock：上传一张首帧→ 返回任务ID→ 模拟排队/进度/失败/超时→ 生成本地标记的假 MP4→ 安全落盘→ 本机播放器/历史；重启后只查询原任务，不重新提交。
- AWS preflight：显示停止/启动/运行状态、可信的实例区域和报价、预算上限、SSM 隧道、自动关机限制。首次实测禁止自动开 EC2，必须获得单次实例/预算授权。
- 前端使用演示数据时明确独立 DEMO 标识；切换到正式模式必须读取 Bridge `/api/health`；未连接时禁止“生成已成功”的假结果。
- 端到端无真实 Key CI：生成流程、网络中断/恢复、重复点击、停止跟踪≠云端取消、磁盘失败、单任务下载校验、超预算拒绝、跨版本依赖不重装。

**暂不启动 AWS，不合并 main，不花赠金，不使用任何真实个人 Key。**
