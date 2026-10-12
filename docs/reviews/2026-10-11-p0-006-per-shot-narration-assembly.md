# AniFlow｜P0-006：逐镜头旁白时间轴与安全合片验收

> 记录日期：2026-10-11（北京时间）。实际模型：GPT-6。  
> 仓库：`wpuu/AniFlow`；分支：`audit/2026-10-11-v710-revalidation`（[PR #2](https://github.com/wpuu/AniFlow/pull/2)，仍为草稿）。  
> 本轮性质：**本地离线工程测试，未使用 Agnes API、真实 Key、Windows、正式配音或客户素材**。不得据此宣布第一集实际完成。

## 1. 本轮解决的交付风险

前一版 `scripts/assemble_locked_episode.py` 可以把 MYCL-001 的 8 镜头（5/5/8/5/6/7/5/5 秒）按 46 秒锁定，但其音频输入是**一条连续配音**。旧版允许一条短至 31 秒的音轨进入合片，再在 46 秒末尾补静音。即使 MP4 只有一条音轨且总时长正确，也无法证明每镜头旁白和对应科学画面时间同步。

为了不通过上游 Creative 编剧模型重新改写事实，本轮保持“分镜、已审片段、已审配音、本地合片”路线，**新增每镜头单独的配音输入方式**。

## 2. 已提交的代码

- [`scripts/assemble_locked_episode.py`](../../scripts/assemble_locked_episode.py)：保留原 `--narration` 单音轨兼容模式；新增 `--scene-audio-dir` 模式，两者强制互斥且只能选一个。
- [`tests/test_per_shot_audio.py`](../../tests/test_per_shot_audio.py)：新增 12 项逐镜头配音专门测试（包括 8 位置真实音频识别、混合音频格式、缺失或过长的音频、文件保护等）。

每镜头模式期望目录中恰好存在：

- `narration_1.wav` 或 `narration_1.mp3`；
- 依次到 `narration_8.wav` / `.mp3`；也支持 `.m4a`、`.aac`，**但同一个镜头只允许一种后缀，不能猜测使用哪一个**。

镜头编号来自原始 `shotlist.json`，不允许重复。每个音频输入必须是普通文件，拒绝符号链接、缺音轨、明显过短、超过对应镜头时长超过 0.10 秒的音轨。

FFmpeg 会将每条音轨统一转换为 48 kHz 双声道，为不足该镜头时长的部分在**本镜头结尾**补齐静音，之后依原工单顺序拼成一条音轨。它不是把所有配音挤到视频前半段后再统一补静音。

输出仍是新建而不覆盖的 MP4，包含镜头表和事实包 SHA-256 指纹、每段输入文件摘要、总时长；返回结果只表明结构成立，**仍为 `ASSEMBLED_MP4_HUMAN_QA_REQUIRED`、`publish_ready=false`**。

## 3. 实际执行与测试证据

测试环境：隔离 Linux、Python 3.13、FFmpeg/FFprobe 7.1.5；仅创建临时模拟素材，没有访问视频提供商。

- `python -m unittest discover -s tests -p 'test_*.py' -q`：**28/28 通过、0 失败、0 跳过**。此计数仅指当前 P0-006 目录的两份测试（原 16 项加新 12 项），**不是整个 AniFlow 仓库的测试统计**。
- 真实 FFmpeg/FFprobe：将 8 条彩色模拟 MP4（90×160、3 fps）按 **46 秒**时长合并。
- 实际生成了 8 条**不同频率的合成正弦波**，分别作为每镜头独立音频。对输出 MP4 逐镜头抽取音频并计算频率成分：**八个对应时间段均识别出正确频率**，排除了只验证“有音轨”但顺序错乱的测试盲点。
- 额外混合样本：第 2、6 镜头改为 22.05 kHz MP3，其余为 16 kHz WAV，统一重采样后合片 MP4 仍通过。
- 失败阻断实测：缺第 8 条音频、同一镜头提供两种文件、单镜头音频超过时长、过短、符号链接、同时提供单音轨和逐镜头目录、原文件存在不可覆盖、未显式执行渲染等。
- `python -m py_compile scripts/assemble_locked_episode.py tests/test_assemble_locked_episode.py tests/test_per_shot_audio.py`：通过。
- GitHub 已回读源代码与测试文件的 Git Blob SHA，并核对与本地**实际测试版本**完全相同。

**限制：** 90×160 彩色画面与正弦波并非 Agnes 模型输出，也不代表 720×1280 真实成片的性能、旁白内容准确性、字幕正确性、TTS 商业授权、AI 生成标识或观众接受度。整仓库测试没有在这次完整重跑。

## 4. 如何在真实素材齐备后使用

假定人工已经检查 `MYCL-001` 的 8 个视频，分别为 `scene_1.mp4` 到 `scene_8.mp4`，均满足 **720×1280**、正确显示方向、对应 5/5/8/5/6/7/5/5 秒。

假定人工已经把实际核查的 8 句旁白交给**授权合规的配音服务**各生成一条音频，放在 `C:\已审素材\voice` 目录，以 `narration_1.wav` 等命名。**文本正确 ≠ 实际发音、音色和字幕正确；须听音核验。**

**步骤一：只做默认预检，不产生 MP4**

```powershell
py -3 scripts\assemble_locked_episode.py --shotlist content\shotlists\MYCL-001-cat-lapping.json --factpack content\factpacks\MYCL-001-cat-lapping.json --clips-dir "C:\已审素材\clips" --scene-audio-dir "C:\已审素材\voice" --output "C:\已审输出\MYCL-001.mp4"
```

**步骤二：预检通过且正式素材已经人工确认，才在上述命令末尾加 `--render`。** 目标输出文件必须尚不存在。

**步骤三：使用已存在的成片元数据审计工具再次锁定 46 秒时间轴，并真人检查科学示意、角色、旁白、字幕、版权、AI 内容标注。**

```powershell
py -3 scripts\inspect_video_output.py "C:\已审输出\MYCL-001.mp4" --kind episode --shotlist content\shotlists\MYCL-001-cat-lapping.json --min-short-side 720
```

当前合片器**不负责 TTS、不生成字幕，也不主动打 AI 内容标识**。没有真实音频授权、人工字幕验收及画面事实审核，就不能进入商业交付。

## 5. 后续工作与状态

1. [Issue #3](https://github.com/wpuu/AniFlow/issues/3) 仍需 Windows 原生 v7.1.0 与最小单 Key 真镜头验证。
2. [Issue #4](https://github.com/wpuu/AniFlow/issues/4) 已明确上游 Creative 批准恢复有重写镜头/旁白的源码级风险，未经受支持接口修复不走直接锁稿方案。
3. [Issue #5](https://github.com/wpuu/AniFlow/issues/5) 更新为优先选择“逐镜头已审核素材＋独立音轨＋本地合片”，再按真实素材验证 AI 画面方向、角色一致性和最终交付。
4. PR #2 继续保持草稿，不合并、不部署、不自动发布；本轮零新增外部 API/服务费用。

技术执行建议：**GPT-6 Luna / Medium** 负责常规 Windows 兼容与真实单镜头验收；碰到上游恢复/并发问题可使用 High。项目商业价值的重大复审可使用 **GPT-6.1 Sol / High**。这些是下轮建议，不代表本轮实际使用了这些模型。
