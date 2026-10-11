# AniFlow｜P0-004：创意模式中的分镜与旁白锁定验证

> 日期：2026-10-11（北京时间）。实际执行模型：GPT-6。  
> 工作分支：`audit/2026-10-11-v710-revalidation`（PR #2，草稿）；`main` 未改动。  
> 本轮范围：上游 v7.1.0 源码阅读、隔离目录内离线模拟测试和 GitHub 提交；未使用用户 API Key、未发起真实视频生成、未运行 Windows。

## 1. 发现旧方向存在一个真正的交付缺口

直接检查上游代码：

- [创意任务创建 API](https://github.com/lcy362/agnes-video-generator/blob/v7.1.0/web/routes/task_creation_routes.py)：`creative` 可以设置 `duration_source=manual`、`scene_count=8` 和 `scene_durations_json=[5,5,8,5,6,7,5,5]`，并配置手动检查点。
- [分镜代码](https://github.com/lcy362/agnes-video-generator/blob/v7.1.0/core/pipelines/creative/steps_script.py)：仍通过上游编剧模型重新生成 `script.json`；该文件是场景字符串列表。
- [旁白代码](https://github.com/lcy362/agnes-video-generator/blob/v7.1.0/core/pipelines/creative/steps_audio.py)：`_step_generate_narrations` 生成**单条连续旁白**，保存到任务状态的 `narrations[0]`，之后才暂停在 `step_script`。
- [稿件模式](https://github.com/lcy362/agnes-video-generator/blob/v7.1.0/core/pipelines/manuscript_video.py)：可接受外部文本，但按朗读长度重新拆段，不能保证严格沿用既定的 8 镜头时长。
- [上游手动模式](https://github.com/lcy362/agnes-video-generator/blob/v7.1.0/docs/public/manual_mode_guide.md)：宣称可修改产物，但尚**没有在真实任务里验证如何通过受支持接口持久锁定上述旁白字段**。

因此，“把已审稿件直接交上游就得到完全遵循原稿的成片”**目前不成立**。此问题比再写一个生成前端更优先。不能因为单纯固定了时长，就认为科学内容也固定了。

## 2. 实际新增的两份代码

- `scripts/lock_upstream_creative_checkpoint.py`
- `tests/test_lock_upstream_creative_checkpoint.py`

工具仅用于读取本地镜头表和事实包，以及上游的人工检查点**文件副本/指定任务目录**，不执行模型调用、不联网、不读取 .env、不自动继续任务。

有三种使用方式：

**默认计划模式：** 输出 MYCL-001 的场景数量、时长和合计秒数，不产生文件。

~~~powershell
py -3 scripts\lock_upstream_creative_checkpoint.py --shotlist content\shotlists\MYCL-001-cat-lapping.json --factpack content\factpacks\MYCL-001-cat-lapping.json
~~~

**显式导出：** 只在**新的、不存在的独立目录**生成 4 个文件：

~~~powershell
py -3 scripts\lock_upstream_creative_checkpoint.py --shotlist content\shotlists\MYCL-001-cat-lapping.json --factpack content\factpacks\MYCL-001-cat-lapping.json --prepare-dir "C:\AniFlowExternal\MYCL-001-export"
~~~

文件为 `script.json`（8 个镜头提示词）、`locked_narration.txt`（锁定原稿）、`creative_form.json`（上游手动输入参数）和 `manifest.json`（内容指纹及版本说明）。此处**并未**将文件写入上游任务系统。

**人工检查点只读核验：** 上游已暂停在官方 `step_script` 后，读取其 `task_state.json` 与 `script.json`，检查任务确为 creative/manual、总数和各场景时长一致、镜头提示词逐条一致、`narrations[0]` 与原稿仅忽略排版空白后一致，且音视频生成尚未开始。

~~~powershell
py -3 scripts\lock_upstream_creative_checkpoint.py --shotlist content\shotlists\MYCL-001-cat-lapping.json --factpack content\factpacks\MYCL-001-cat-lapping.json --check-task "C:\AgnesVideoStudio\.working_dir\具体任务目录"
~~~

任何差异输出 `BLOCKED`；匹配时只输出 `CHECKPOINT_TEXT_MATCH_ONLY_HUMAN_REVIEW_REQUIRED`，明确 `safe_to_resume_without_manual_approval=false`。不得将文本匹配当成正式内容审核、商用配音授权或视频生产成功。

尤其注意：**尚未实测如何通过上游官方工具将已审核的 `narrations[0]` 写回并持久保存**。不要绕开其状态机、手动篡改生产 `task_state.json`，也不要为绕过检查而跳到后续视频提交。

## 3. 实际测试边界

- 本地临时 Linux / Python 3.13：**新增 21 个独立测试通过**，与之前的 45 个 P0 测试一起执行为 **66/66 通过**；语法编译通过。
- 新测试包含：完整 8 镜头/46 秒时长、狗角色切换、缺失尾帧、禁用事实说法、旁白改变、镜头提示词改变、时长改变、检查点错误、音视频已开始、敏感 .env 不读取、只读文件不变化、导出目标不得覆盖等。
- 已回读 GitHub：本轮提交的检查器与测试文件 **Git blob SHA 完全匹配本地已测试文件**。
- 独立用 GitHub 实际原始 JSON 做静态数据核查：第一集 8 镜头、秒数 5/5/8/5/6/7/5/5，共 **46 秒**；事实包 ID 一致，生成 8 条候选提示词，原文旁白约 **163 字符**，未命中事实包列出的禁用原句。此次不是通过真实 Agnes 应用运行 Python，因此不能冒充上游集成测试。
- 检查器只是结构和原文一致性闸门，不替代 `aniflow.factpack` 的完整数字溯源和人工事实复核。

## 4. 下一关：P0-005

在合法有效、隔离的上游 Windows 运行环境下，验证**不改私有状态机**的正式手动检查点能否：

1. 创建 8 场景、各自锁定秒数的创意任务，停在 `step_script`；
2. 使用上游明确支持的编辑操作替换分镜描述并锁定整段旁白；
3. 恢复后再次核对不会被上游模型改写，也不会提前产生不可撤回视频任务；
4. 不能完成时，停止“一键创意模式严格复现 MYCL-001”路径，再比较“稿件模式重新拆段”或“每镜头生成＋可控音轨合成”。

这一关没有真实服务环境证据，因此**P0-005 仍未完成**。PR #2 保持草稿、Issue #3 的真实 Windows/Agnes 成片验收尚未启动。勿新增多 Key 抢队列、自动发布或商业排产。

建议：涉及上游状态机与恢复机制的工程验证使用 **GPT-6 Luna / High**；大的商业复审使用 **GPT-6.1 Sol / High**。本轮实际执行模型为 GPT-6。
