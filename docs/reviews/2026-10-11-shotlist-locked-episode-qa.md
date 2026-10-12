# AniFlow｜P0 成片与镜头工单一致性检查（2026-10-11）

> 日期：2026-10-11（北京时间）。实际执行：GPT-6 聊天端。工作分支：`audit/2026-10-11-v710-revalidation`，草稿 PR #2。  
> **本次仅开发和离线验证。没有调用 Agnes、没有运行 Windows、没有生成第一集真实视频，也没有合并主分支。**

## 核验发现

第一集的仓库原始事实包 `content/factpacks/MYCL-001-cat-lapping.json` 与镜头表 `content/shotlists/MYCL-001-cat-lapping.json` 都标记 `MYCL-001`。镜头表共有 8 镜头，计划时长依次为 `5, 5, 8, 5, 6, 7, 5, 5` 秒，合计 **46 秒**；镜头 `4、5、7、8` 继承上一镜尾帧，对照原始 JSON 未发现链条缺失。

**既有缺口：** 早期的 `scripts/inspect_video_output.py` 只需成片落在 30–60 秒，便可能返回“元数据通过”；一条漏掉 5 秒镜头的 40 秒视频也落在宽泛范围内。原检查也只核实“存在音轨”，没有核对是否覆盖完整时间线。

## 新增的实际能力

现有 `scripts/inspect_video_output.py` 增加了可选参数 `--shotlist`，从**实际 JSON 工单**提取镜头数、计划总秒数、镜头 ID、SHA-256 指纹：

- 拒绝重复镜头 ID、无效时长（单镜头必须 4–12 秒）、无首帧、尾帧继承断链、非 9:16、畸形或超出 1 MiB 的镜头工单。
- 对总时长实施**默认 ±0.75 秒容差**（可用 `--duration-tolerance` 指定），第一集约为 45.25–46.75 秒；超差的成片自动阻断。
- 与镜头工单绑定时**自动要求存在且只有一条音轨**，核对 ffprobe 中音轨 `start_time` 和 `duration` 是否覆盖视频主要时间线。缺音、音频开始过晚、提前结束、元数据缺失则阻断。
- 返回 `shotlist_sha256`、预期时长和差异原因，便于后续接手者核对究竟验收的是哪一版工单。
- 检查器仍只读本机 MP4 和指定 JSON，不运行视频生成、不读取 API Key、不上传视频、不触碰 GitHub 之外的用户运行配置。
- **通过结果仍然是 `METADATA_OK_HUMAN_QA_REQUIRED`，不是“已达到发布标准”。** 总时长正确不能证明八个镜头都在；音轨存在不证明有可听到的旁白、字幕同步或文字正确；毛毡角色一致性、事实、配音许可证和 AI 标识均须人工检查。

## 新增与回归测试

在临时 Linux / Python 3.13 环境，执行：

```bash
python -m unittest discover -s tests -p 'test_*.py' -q
python -m py_compile scripts/inspect_video_output.py tests/test_inspect_video_contract.py
```

本轮**45/45 项测试通过**，其中：
- 原有 24 项单元回归；
- 新增 21 项镜头工单、音轨覆盖、异常输入、指纹和 CLI 验证（`tests/test_inspect_video_contract.py`）。

另外，确实使用 FFmpeg 合成三种**假视频测试素材**并用真实 ffprobe 运行检查器（非 Agnes 模型输出）：

| 模拟视频 | 元数据 | 检查结果 |
|---|---|---|
| 46 秒、90×160、46 秒音轨 | 视频与音轨覆盖总时长 | `METADATA_OK_HUMAN_QA_REQUIRED` |
| 40 秒、90×160、40 秒音轨 | 符合旧的 30–60 秒宽限，但缺少 6 秒 | `BLOCKED`：与锁定工单 46 秒不符 |
| 46 秒、90×160、仅 30 秒音轨 | 视频足长但音轨提前停止 | `BLOCKED`：音轨不足以覆盖时间线 |

以上合成素材短边仅 90 像素，只用于测试新逻辑，**不能被认定为真实成片或达到 720P 质量**。运行真实视频验收时应传 `--min-short-side 720`。

## Windows 本机后续运行方式

必须先检出带新工具的审计分支，`main` 尚无这些新功能：

```powershell
py -3 scripts\inspect_video_output.py "C:\受控输出\MYCL-001.mp4" --kind episode --shotlist content\shotlists\MYCL-001-cat-lapping.json --min-short-side 720
```

如果制作脚本实际缩短为 30 秒，**应该建立并审计新的版本化镜头工单**，不能为了让 40 秒片通过而手动放大容差。

后续必须拿到真实 Windows 上游服务、有效合法 Key、真实生成视频，再进行单 Key、单镜头、9:16 实画面方向、第一集成片和最终人工审核。不能靠离线工具通过就判定上线或商业化成功。

## 执行责任

- 工程与测试建议：GPT-6 Luna／Medium；涉及多 Key 并发/恢复再提高思考等级。
- 重大商业化与合规冻结：GPT-6.1 Sol／High。
- 每轮回报实际完成/验证状态/阻塞、模型、时间、GitHub 分支与 SHA；不要将“将来要执行”写成“本轮已执行”。

[上游 v7.1.0](https://github.com/lcy362/agnes-video-generator/releases/tag/v7.1.0) ｜ [P0 上轮记录](2026-10-11-p0-preparation-and-mp4-acceptance.md) ｜ [PR #2](https://github.com/wpuu/AniFlow/pull/2)
