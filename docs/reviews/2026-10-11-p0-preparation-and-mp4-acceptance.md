# AniFlow｜P0 上游版本准备与 MP4 验收交接

> 2026-10-11（北京时间）。实际执行模型：GPT-6。目标分支：`audit/2026-10-11-v710-revalidation`（PR #2，草稿）。
>
> 本轮真实执行：离线 Python 自动测试与本地 FFmpeg/FFprobe 合成样本检查；未访问真实 Agnes API、未启动 Windows 上游服务、未使用用户 Key，也未验证实际商用作品。

## 一、已落地的两项独立工具

**版本固定的上游准备工具：`scripts/prepare_video_studio_v710.py`**

- 默认只预览。只有显式传入 `--install` 才连接 GitHub，在用户主目录的 `AniFlowExternal` 下新建独立目录。
- 固定上游标签 `v7.1.0`；克隆后核验 HEAD 与 2026-10-11 已核实的真实提交 `bc00ee0affa134ef67f03733d2da5ed32e3582a4` 一致。
- 在临时目录核对 Git 干净状态、关键源码及视频旋转说明，再转入正式目录。已有目录绝不覆盖，Git 获取失败、版本不符或文件缺失即阻止。
- 不覆盖旧的 `v7.0.4`，不应用旧的“503 队列满立即换 Key”补丁；不读取/复制 `.env`、不启动服务、不安装依赖。Git 公共拉取禁用 credential helper。
- `--verify-existing` 只校验版本来源和静态结构，**不**代表上游可运行。

**本地成片元数据检查工具：`scripts/inspect_video_output.py`**

- 使用本地 `ffprobe` 只读检查 MP4 时长、编码尺寸、旋转后的显示尺寸、9:16、是否有音轨、短边最低分辨率。
- 片段默认核验 4–12 秒；成片默认核验 30–60 秒，也可自定范围。
- 错误格式/缺失音轨/横屏或旋转后横屏/尺寸不足均阻断。
- 元数据通过输出 `METADATA_OK_HUMAN_QA_REQUIRED`，**不代表肉眼画面真实朝向正确**；内容可能在竖屏编码中横倒。事实准确性、角色连续性、版权和 AI 标识仍需人工核验。
- 不上传 MP4，不泄露包含用户目录的完整路径，不自动发布。

## 二、本轮真实测试边界

运行环境：临时 Linux / Python 3.13，官方 ffmpeg/ffprobe 命令；不依赖网络。

| 验证内容 | 本轮结果 | 限制 |
|---|---|---|
| `test_prepare_video_studio_v710.py` | **11/11 PASS** | Mock Git 克隆，没有下载真实上游源码 |
| `test_inspect_video_output.py` | **13/13 PASS** | mock 元数据包含正反例 |
| 4 个 Python 文件语法编译 | PASS | 不是 Windows PowerShell 或上游启动测试 |
| FFmpeg 自造 90×160、5 秒无声黑画面 → 实际 ffprobe 检验 | 返回 `METADATA_OK_HUMAN_QA_REQUIRED` | 分辨率很低，且不是 Agnes 作品 |
| FFmpeg 自造 160×90、5 秒无声黑画面 → 实际 ffprobe 检验 | **BLOCKED**（横屏） | 仅检查元数据 |
| 对 90×160 测试要求最低短边 720 | **BLOCKED**（尺寸不足） | 不代表视频模型画质 |

合计：**24/24 自动单元测试通过**。只指上述两份新增测试，不代表整个 AniFlow 项目全部测试通过。测试文件与 GitHub 提交的 Git Blob SHA 已一致核对。未运行 GitHub Actions。

## 三、下一轮的 Windows / Codex 验收步骤

必须先确保当前本地分支拥有上述文件；不要在未合并的 `main` 直接调用不存在的工具。

1. **无 Key、无网络写入验证**：打开 AniFlow 仓库目录，运行：

   ~~~powershell
   py -3 -m unittest discover -s tests -p test_prepare_video_studio_v710.py -v
   py -3 -m unittest discover -s tests -p test_inspect_video_output.py -v
   py -3 scripts\prepare_video_studio_v710.py
   ~~~

2. 若确认有 Git、官方 GitHub 网络可用且允许创建**全新独立目录**，才执行：

   ~~~powershell
   py -3 scripts\prepare_video_studio_v710.py --install
   py -3 scripts\prepare_video_studio_v710.py --verify-existing
   ~~~

   如果返回 `BLOCKED`，停止，记录失败原因。**不能跳过提交哈希校验、强行复用老补丁或覆盖旧目录。** 这两个操作仅准备和静态校验源码，还没有安装依赖或启动服务。

3. 在确认不和旧 AniFlow Bridge 的 `8765` 端口冲突后，另行进行原生上游启动检查。真实 Key 仅在安全本机输入，不能放进聊天或公开仓库。只有获准并确认使用限制，才做最小单 Key、单镜头真实测试。
4. 拿到已生成的本地视频文件后：

   ~~~powershell
   py -3 scripts\inspect_video_output.py "C:\受控输出\clip.mp4" --kind clip --min-short-side 720
   py -3 scripts\inspect_video_output.py "C:\受控输出\episode.mp4" --kind episode --min-seconds 40 --max-seconds 50 --require-audio --min-short-side 720
   ~~~

   然后由真人播放检查：是否实际横倒、科学动作是否正确、雪所长是否一致、旁白是否完全对上事实包、字幕和声音、商业授权、发布平台的 AI 标识与内容类别。

## 四、状态及后续排序

| 关卡 | 状态 |
|---|---|
| 静态版本判断、原生 v7.1.0 源码固定准备逻辑 | 完成；**仅离线模拟验收** |
| 本地 MP4 元数据 QA | 完成；合成样本验证通过 |
| Windows 原生 v7.1.0 安装和服务启动 | **待验** |
| Agnes 单 Key 首条真视频（含 video_id、队列等待和 MP4） | **待验** |
| 9:16 像素内容是否横倒、模型参考图角色锁定 | **待验** |
| MYCL-001 完整成片和人工最终审核 | **待验** |
| 真实买方付费试单与重复交付 | **待验** |

不应在上述证据缺失时直接合并成“生产可用”，不应恢复大规模多 Key 自动抽卡或批量发布。下轮建议 **GPT-6 Luna / Medium** 处理 Windows 安装与测试；出现复杂并发/异步恢复问题再提高 High。重大商业方向变更再交 **GPT-6.1 Sol / High**。

参考：[上游 v7.1.0](https://github.com/lcy362/agnes-video-generator/releases/tag/v7.1.0)、[上游 9:16 旋转已知问题](https://github.com/lcy362/agnes-video-generator/blob/v7.1.0/docs/public/usage.md)、[本轮 PR #2](https://github.com/wpuu/AniFlow/pull/2)。
