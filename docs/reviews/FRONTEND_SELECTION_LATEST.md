# FRONTEND_SELECTION_LATEST

审计时间：2026-10-25 ｜项目：wpuu/AniFlow ｜阶段：P0-035（Mock集成，非发布版）

**选 Grok 作为主前台基线，吸收 Claude 的模型状态栏/统计/参数详情组织。** 原ZIP及原始候选均保持不变，工程副本在 `apps/studio-mock-ui/`。

依据：
- 两份 ZIP 都已真实静态解包检查，均通过严格 TypeScript/Vite 构建。
- Grok 的首帧拖拽、提示词预设、高级参数、任务引擎分离更适合作为操作界面；Claude 的任务数据持久化与操作参数较弱。
- 两份原样运行都存在模拟任务自动完成、演示视频和硬编码在线/计费数据，均不能作为真实视频后端。
- 工程副本已替换随机模拟任务，接入SQLite Mock Bridge且通过真实Chromium端到端下载验证。单独端口8767、不接AWS、不影响用户现有8765。

详细证据：[双ZIP审计](2026-10-25-claude-grok-frontend-audit.md) 与 [Mock合同](2026-10-25-studio-mock-h3-contract.md)；[CI #40152956282](https://github.com/wpuu/AniFlow/actions/runs/40152956282) 全部通过；[Draft PR #7](https://github.com/wpuu/AniFlow/pull/7)。

下一步：先把隔离Mock工作台与先前隔离PR #2 v0.34.2的Windows共享依赖/版本机制统一，验证无回归；再做 AWS 预算/配额/模型权重许可与SSM预检。直到用户单独批准，严格禁止创建EC2或真实视频任务。
