# AniFlow P0-005｜上游手动恢复审计与锁稿本地拼接替代路线

> 核查日：2026-10-11（北京时间）。实际模型：GPT-6（本会话；无权自称切换为其他模型/思考档）。  
> AniFlow 先前基线：`main@4a09aa3`；本次工作分支：`audit/2026-10-11-v710-revalidation`，草稿 [PR #2](https://github.com/wpuu/AniFlow/pull/2)。  
> 上游：`lcy362/agnes-video-generator@v7.1.0`，固定 tag commit `bc00ee0affa134ef67f03733d2da5ed32e3582a4`。  
> 性质：**基于真实上游源码的只读逻辑审查＋本机离线模拟生产链路**。尚未获得 Windows 或 Agnes 真实视频/恢复运行证据，不应合并或称生产可用。

## 1. P0-005 实质结论：创意模式严格锁稿的标准操作不能当作已可用

这次不再仅阅读 README，而是核查以下 **v7.1.0 固定版本源文件**：

- [`core/pipelines/creative/steps_script.py`](https://github.com/lcy362/agnes-video-generator/blob/v7.1.0/core/pipelines/creative/steps_script.py)：`_step_script` 在 `step_script` 已完成、文件存在且场景数符合时才复用；否则重新调用 `screenwriter.write_script`；`_step_generate_narrations` 另生成整段旁白。
- [`core/pipelines/creative/steps_audio.py`](https://github.com/lcy362/agnes-video-generator/blob/v7.1.0/core/pipelines/creative/steps_audio.py)：`_step_generate_narrations` 将整段旁白放在任务状态 `narrations[0]`，配音阶段从此字段读取，并不是从手工编辑的 `script.json` 重建。
- [`core/pipelines/creative/pipeline.py`](https://github.com/lcy362/agnes-video-generator/blob/v7.1.0/core/pipelines/creative/pipeline.py)：`step_script` 手动暂停发生在编剧和旁白生成**之后**。
- [`core/artifacts.py`](https://github.com/lcy362/agnes-video-generator/blob/v7.1.0/core/artifacts.py)：creative 模式声明的脚本产物为 `creative:script` → `script.json`，关联 `script_file`、`narrations` 两个状态字段。**没有单独可上传编辑的 `narrations[0]` 产物声明**。
- [`web/routes/video_routes.py`](https://github.com/lcy362/agnes-video-generator/blob/v7.1.0/web/routes/video_routes.py)：产物上传只覆盖文件并标记修改；正式批准先使用依赖图计算 `affected`，删除受影响产物文件，重置步骤，最后调用 `resume_task`。
- [`core/dependency_graph.py`](https://github.com/lcy362/agnes-video-generator/blob/v7.1.0/core/dependency_graph.py)：`creative:script` 的产物/字段级修改在影响集合中**包含它自身**；该集合会把 `step_script` 加入 `steps_to_reset`。即使传 `creative:script:scene_prompt`，规范化后的 affected 仍包含 `creative:script`。

### 关键失败路径（源码级推导，尚未实际在 Windows 复现）

1. 在创意模式进入 `step_script` 暂停前，AI 已生成 `script.json` 和 `narrations[0]`。
2. 经正式上传接口覆盖 `creative:script` 的文件，其内容成为想要的 8 个镜头。
3. 照正式“确认修改影响”路径申报 `creative:script` 已修改，依赖图会将该产物自身加入 affected。
4. 批准接口删除 affected 中的 `script.json` 并重置 `step_script`。
5. 下一轮恢复时 `_step_script` 不符合复用条件，再次走 AI 写分镜。保留原有 `narrations[0]` 也可能与重写分镜不再对应；若用户原稿尚未写入状态，则 AI 旁白仍是原值。

**结果：** 不能把上传脚本＋正常批准视作可靠的原稿/旁白导入。若故意不上报 modified_artifact_ids，可能绕过依赖计算，**不应作为正式受支持的解决方案**，且依然缺乏对 `narrations[0]` 的授权写回。

因此：**暂时冻结“创意模式自动锁定 MYCL-001 旁白后继续”这一生产假设。** 本结论是源码级阻塞判断，不是假装已有 Windows 或真实队列失败记录。已有 [Issue #4](https://github.com/wpuu/AniFlow/issues/4) 仍保留真实环境核验；若要让 creative 正式支持锁稿，需要上游维护者提供明确 API/补丁和回归测试，而不是直接篡改任务文件。

## 2. 本轮实际实现：8 镜头已审素材本地拼接

新增：
- `scripts/assemble_locked_episode.py`
- `tests/test_assemble_locked_episode.py`

**用途：** 读取原始 AniFlow `shotlist.json` 与 `factpack.json`，再读取用户已获得并验收的**本地**视频片段及本地配音文件，严格按源工单镜头顺序和时长，用 FFmpeg 合成 MP4。它不调用 Agnes、不接触上游私有任务状态、不下载素材、不生成新的 AI 内容、不重新编写配音、不自动发布。

关键防护：

- 默认只预检（无需 `--render`），并不产生输出；必须显式确认渲染操作。
- 工单/事实包 ID 要一致，镜头 ID 不可重复/路径穿越，时长必须在 4–12 秒，首尾帧继承必须有效，禁止出现事实包的禁用语句。
- 输入必须是明确命名的 `scene_1.mp4` ～ `scene_8.mp4` 等既有文件；按工单校验时长（默认 ±0.3 秒）、画幅。**生产路径只接受 720×1280（9:16）、无显示旋转元数据**，不“智能裁切”不合规视频。
- 独立配音文件只读验证格式/时长/音轨。较短但合理的配音会补齐静音到目标时长；**静音填补不等于语音内容充分或字幕同步，最终必须人工听完整成片**。
- 输出只接受未存在的 MP4 路径，临时编码+校验后通过同文件系统原子硬链接发布，拒绝覆盖原文件。
- 输出带镜头表/事实包 SHA256、每镜头文件摘要/时长、最终 MP4 摘要；**不记录 Key 和完整用户路径**。
- 返回 `ASSEMBLED_MP4_HUMAN_QA_REQUIRED`，明确 `publish_ready=false`，没有假称科学示意正确、字幕齐全、版权清晰或商业 TTS 授权通过。

### 使用示例（仅在已准备好真实本地素材之后）

前置：电脑安装 FFmpeg 与 FFprobe；本地已存在经审核的 8 个镜头 `scene_1.mp4` 至 `scene_8.mp4`（每条符合各自的长度和 720×1280），以及自行合法制作的配音音频 `voice.wav`。

在 AniFlow 本项目根目录，先用**默认预检**：

~~~powershell
py -3 scripts\assemble_locked_episode.py --shotlist content\shotlists\MYCL-001-cat-lapping.json --factpack content\factpacks\MYCL-001-cat-lapping.json --clips-dir "C:\已审素材\MYCL-001" --narration "C:\已审素材\voice.wav" --output "C:\已审输出\MYCL-001.mp4"
~~~

预检通过后才显式加 `--render`。随后仍需使用上一轮的 `scripts/inspect_video_output.py` 对最终 MP4 复核，并**人工逐帧/逐段检查**画面方向、科学描述、角色外观、字幕、旁白、著作权和 AI 标签。

重要限制：这个备用程序目前**只负责编排已有的片段与已获授权的音轨**，既不是 TTS 工具，也不负责合成字幕。不要把它当完整视频工厂。

## 3. 本轮实际执行与测试证据

在临时 Linux / Python 3.13、FFmpeg 7.1.5、FFprobe 环境进行：

- `python -m unittest discover -s tests -p 'test_assemble_locked_episode.py' -v` → **16/16 通过**。
- `python -m py_compile ...` → **通过**。
- 使用 FFmpeg 真正生成了八段**90×160、3 fps 合成彩色假镜头**（时长 5/5/8/5/6/7/5/5 秒）以及 31 秒的测试正弦波音频。
- 先预检，确认不产生输出；再真实调用 FFmpeg 进行 8 镜头拼接并生成约 **46 秒**有音轨的合成 MP4，调用 FFprobe 回读。此测试是**本机拼接功能的真实执行**，不是 Agnes 生成的视频。
- 另有故障测试：缺失某镜头、短一秒、非生产分辨率、明显过短音轨、危险镜头 ID、事实包 ID 不一致、禁用事实说法、尾帧断链、目标文件已存在、符号链接输入及容差 NaN 等均正确拒绝。
- 本轮测试所用文件为**临时模拟镜头工单**，数目和时长与仓库中的 MYCL-001 匹配。并非已读取或生成实际 MYCL-001 原始八条视频，更非商业交付证明。
- 当前仓库完整单元/集成测试、Windows 原生服务、视频真实生成、字幕及商用授权都**尚未因此标为完成**。

## 4. 下一阶段怎么做

1. 保留 P0-005 上游锁稿阻塞事实，不把已证明存在的破坏性级联当作正常可用导入；不应用脆弱的私有状态文件篡改。
2. 下一次能使用真实 Windows 本机时，首先只做 1 Key、1 条镜头生成与落盘，并检验 9:16 上游旋转异常；不大规模重试或多 Key 抢资源。
3. 有第一条可用真实镜头后，决定最终是否采用“逐镜头生成＋本地合片”；先做 2–3 关键动态镜头、其余静帧转片段的成本/画质对比，再决定整集方案。
4. 为正式发布增加可审计的 TTS/旁白锁定、字幕生成及事实二次核验；确认配音服务与商业授权。
5. 保留草稿 PR #2；**用户没有请求合并，且核心真实素材尚未验收，不应合并 main 或部署。**

技术下一步模型建议：GPT-6 Luna / High 用于上游恢复和音轨同步问题，常规工程可使用 Medium。重大商业模式冻结可交 GPT-6.1 Sol / High。本轮报告实际由 GPT-6 编写。

## 5. 本轮质量与审计

- 本次核对了 GitHub main/PR/Issue 的实时 HEAD、上游 v7.1.0 发布版本以及 4 条连续的“继续推进”历史方向，**没有发现子项目串台**。当时未发现需要改写此前商业判断的新版上游 release。
- 目标始终是“可重复、可交付并可能收费的原创短视频”，不是把“多 Key”“免费 API”“视频工厂”当最终商品。
- **绝不把源码级逻辑推断说成已实测 Windows 恢复失败；也不把合成 MP4 拼接说成 Agnes 真成片。**

相关： [PR #2](https://github.com/wpuu/AniFlow/pull/2) · [Issue #3](https://github.com/wpuu/AniFlow/issues/3) · [Issue #4](https://github.com/wpuu/AniFlow/issues/4)。
