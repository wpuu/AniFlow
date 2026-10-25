# AniFlow｜P0-007 交付素材快照完整性修复与离线验证

> 记录日期：2026-10-11，北京时间（UTC+8）。本次实际模型：GPT-6。隔离分支：`audit/2026-10-11-v710-revalidation`；PR #2 继续为草稿。  
> **本次已运行的是 Linux / FFmpeg 合成媒体专项测试；不是 Agnes 视频模型输出，不是 Windows 实机，也不是整个 AniFlow 仓库测试。**

## 一、发现的问题及修复

上一轮 `scripts/assemble_locked_episode.py` 会先对本地视频片段、配音文件读取媒体信息和计算 SHA-256，然后在正式 FFmpeg 拼接时直接使用原来的输入路径。倘若某个素材在预检后被其他软件/用户替换、改写，原版无法保证成片读取的字节等于报告中记录的字节。

**P0-007 实际修复已提交到原脚本，不新建另一个视频系统：**

1. 默认不运行拼接，仅预检，增加 `input_snapshots_verified=false`；绝不假称预览阶段已经创建/验证快照。
2. 明确执行 `--render` 时，先在输出目录的独立临时文件夹将所有视频和配音文件复制为当次任务的输入快照。分镜源文件和事实包仍保持只读。
3. 每份复制文件必须与先前预检的 SHA-256 完全一致；不一致**立即阻止成片发布**，且原有输出不被覆盖。
4. 对快照重新运行实际 FFprobe 检查，确认画幅、时长和音轨符合原锁定工单。FFmpeg 拼接命令只引用快照路径，而非可被其他程序修改的用户原文件。
5. 采用受限的源文件描述符读取和可用时的 `O_NOFOLLOW` 防符号链接措施；快照目标使用独占新建，不覆盖现有文件。临时目录在失败/完成后自动清理。
6. 真实完成后报告 `input_snapshots_verified=true`、`snapshotted_input_count` 和最终 MP4 SHA-256。通过状态仍为 `ASSEMBLED_MP4_HUMAN_QA_REQUIRED`，**不表示已具备发布资格**。

**实际资源代价：** 在渲染期间需要额外磁盘空间储存全部视频和配音的临时副本；若空间不足，按错误停止，不自动删除用户素材。

## 二、本轮真实测试

运行环境：临时 Linux，Python **3.13.5**；FFmpeg/FFprobe **7.1.5**；不使用 Agnes API Key 或网络视频服务。

### 测试范围

- 保留 P0-005/P0-006：**28 项已有离线测试全部通过**，包括模拟 8 镜头、46 秒、有音轨 MP4 拼接，以及 8 段不同频率的声音与镜头窗口对齐、MP3/WAV 混合输入、故障拒绝等。
- P0-007 新增 `tests/test_media_snapshot.py`：**9 项专项测试全部通过**。包括：
  - 源素材快照必须是独立副本，原文件修改后快照仍不变；
  - 预检后改写片段或配音，必须失败且不产生最终输出；
  - FFmpeg 只能读取临时快照，不能继续读用户源路径；
  - 正式编码期间原输入被修改，仍从快照拼出正确视频；
  - 已存在目标不得覆盖；符号链接替换不得通过；
  - 仅预检不得声称快照已验证；
  - **实际生成并拼接一段 720×1280、5 秒的合成彩色视频**，验证非模拟的生产画幅分支。
- `python -m unittest discover -s ... -p 'test_*.py' -q` → **37 tests, 0 failures, 0 skips**。
- `python -m py_compile` → **通过**。
- GitHub 已回读并对照 Git Blob 指纹： 
  - `scripts/assemble_locked_episode.py` → `af44796ee757bfac3d39195adb026f604ed6c93f`
  - `tests/test_media_snapshot.py` → `8998f5f94e790e9bacf988b0dd9ec3158ed8dd41`

### 未完成或不能宣称已验证

- 整个 AniFlow 仓库的测试未能运行。本次容器 `git ls-remote` 尝试连接 GitHub 时返回 `Could not resolve host: github.com`，所以没有完整检出依赖、前端或旧项目代码。GitHub 连接器可读写指定文件但不提供本地可执行仓库副本。以上 37 项来自现有 P0-005/P0-006 脚本和 P0-007 专项测试，**不是整仓库测试总数**。
- Windows 文件语义、真实工作台运行、Agnes 真实片段、9:16 像素是否横倒、实际配音准确性、字幕同步、事实审核、商用声音/字体/配乐授权以及短视频发布标识，均未完成验收。
- 预检的 SHA-256 与视频拼接一致**不等于已经核实旁白的说话内容**。AI 配音必须另行人工比对原稿。
- 当前 `main` 未合并上述变更；不部署、不发布、不请求额外付费视频生成。

## 三、后续最短路径

1. 在授权的 Windows 电脑检出当前隔离分支，运行 `py -3 -m unittest discover -s tests -p test_*.py -v` 和项目原有完整验证命令，记录通过/跳过/失败，修复回归问题。
2. 基于 [Issue #3](https://github.com/wpuu/AniFlow/issues/3) / [Issue #5](https://github.com/wpuu/AniFlow/issues/5) 做**一次**原生 Agnes v7.1.0 单 Key、单镜头生成。核实任务 ID、队列/推理时间、完成 MP4、画幅、像素朝向，拒绝未授权多 Key 大量重试。
3. 真视频有证据后，按照 P0-006/P0-007 已测试路径逐镜头对齐旁白、合成 MYCL-001，再做人工终审。不得用本地色块假视频冒充可发布作品。
4. 仍不应提前合并草稿 PR #2；实际视频可用性、最终听读与授权审核是合并前的实质关卡。

建议执行模型：GPT-6 Luna / Medium 处理本地测试和单镜头验证；复杂 Windows/上游异步故障可提高到 High；重大商业方向再用 GPT-6.1 Sol / High。本次实际会话并未自行切换模型。

[草稿 PR #2](https://github.com/wpuu/AniFlow/pull/2) · [原有 Issue #5](https://github.com/wpuu/AniFlow/issues/5)
