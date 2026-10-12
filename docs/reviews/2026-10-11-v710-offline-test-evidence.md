# AniFlow｜v7.1.0 隔离兼容预检：离线验证记录与续接

- 核验日期：2026-10-11（北京时间）
- 实际执行模型：GPT-6（聊天会话，未使用 Codex 云端执行）
- 分支：`audit/2026-10-11-v710-revalidation`
- 工作内容：在不使用真实 Key、不连接视频服务、不启动 Windows 应用的条件下，增加一个**只读、失败关闭**的兼容预检工具。
- 新文件：`scripts/audit_video_studio_v710.py`
- 回归测试：`tests/test_audit_video_studio_v710.py`

## 本轮实际完成

1. 以现有 `InstallVideoStudio.ps1` 的 `v7.0.4` 为基线，识别旧版安装器版本锁定和与预期 `v7.1.0` 不符的情况。
2. 读取用户指定的**本地上游源码路径**，检测 `core/api/agnes_video.py`、`core/api/retry_policy.py`、`core/api/key_manager.py` 是否存在；仅检查繁忙重试、Key 轮换和 401 归因的标识性代码片段。
3. 检查旧版打补丁的两个源码锚点在上游是否出现，**但绝不自动应用补丁**。
4. 核查第一集的事实包、镜头 JSON 和人工工单是否存在；记录上游使用文档是否提及 9:16 旋转修正选项。
5. 输出可保存的 JSON。工具明确写出 `safe_to_apply_legacy_patch=false`、`safe_to_claim_windows_or_video_verified=false`、`release_identity_verified=false`。匹配源码结构并不等于真实 tag 被验证、Windows 已安装或视频能生成。
6. 预检不会读取 `.env`、不会读取 Key、不会进行 HTTP 请求，也不会改变现有配置文件。

## 本轮测试真实结果

在当前临时 Linux 执行环境，使用 Python 标准库 `unittest` 构造模拟目录，实际运行：

```bash
python3 -m unittest discover -s tests -p 'test_audit_video_studio_v710.py' -v
python3 -m py_compile scripts/audit_video_studio_v710.py tests/test_audit_video_studio_v710.py
```

**结果：7/7 通过，语法检查通过。** 覆盖：旧安装器版本拒绝当作新版本、无上游输入不报成功、上游缺文件阻断、新版结构只报静态匹配、旧补丁锚点识别、示例 .env 秘密不泄露且保持不变、第一集资料缺失阻断。

限制：测试用例使用**模拟上游源码字符串**，没有下载完整上游仓库，也没有在 Windows 原机运行或执行成片测试。不能声称“整个 AniFlow 测试集已通过”或“v7.1.0 已完成真实兼容验证”。

## 下次有 Windows/upstream 文件时如何用

先从官方 [上游 v7.1.0 Release](https://github.com/lcy362/agnes-video-generator/releases/tag/v7.1.0) 获取源码，在独立目录解压。保持原有 `scripts/video-studio` 等业务目录和密钥文件不变。用经人工确认的源码目录执行：

```powershell
python scripts/audit_video_studio_v710.py --upstream "C:\\安全测试目录\\agnes-video-generator-7.1.0"
```

当前旧安装器锁定 v7.0.4，因此报告预期包含 `REQUIRES_VERIFICATION` 和版本不匹配；退出状态码 2 是正确阻断，不代表工具程序崩溃。不会静默修改安装程序。测试目录名字不等于真实官方版本验证；需要检查 Release 来源与对应 SHA。

**下一次实际工程任务：** 在单独、可回滚目录开发原生 v7.1.0 启动/验收路径，并对照预检报告做本地试运行。Windows 测试之前，不应修改原用户安装器的默认行为。之后单 Key、单镜头受限实测，再考虑多 Key 和 MYCL-001。

## 附加风险与退出标准

- AniFlow Bridge 和上游视频工作台都可能尝试使用本地 `8765`，验证时不能同时绑定该端口。
- 旧补丁 `docs/patches/queue-full-rotate-keys.patch` 针对 v7.0.4，不可直接移植。
- 9:16 旋转问题要依据真实视频文件、播放器和 `ffprobe` 结果验收。
- 尚未核实 Edge TTS 的商业授权，也未完成发布平台 AI 标签与客户视频许可审查。
- 不提交 .env、Key、Cookie、任务隐私文件或真实生成视频日志到公开仓库。

## 模型与阶段责任

- 兼容实现、离线自动测试：推荐 GPT-6 Luna / Medium。
- 多 Key 并发正确性、异步恢复、跨服务可靠性：技术复杂时提升 High。
- 商业方向、合规与扩张判断：推荐 GPT-6.1 Sol / High。
- 本轮实际聊天模型：GPT-6。模型建议不代表已经切换执行模型。

**本轮完成边界：离线只读预检及测试；未验证真实生成、安装、商业收入。**
