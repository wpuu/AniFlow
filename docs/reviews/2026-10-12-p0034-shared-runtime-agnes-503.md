# AniFlow P0-034｜Windows 共享依赖环境与 Agnes 503 容量结论

日期：2026-10-12（北京时间）
版本：v0.34.0 / P0-034
唯一项目：wpuu/AniFlow；原 PR #2 隔离分支，main 不合并。

## 1. 真实定位：重复安装依赖是应用缺陷

v0.33.0 及以前的完整 Windows ZIP 解压到新目录后，首次安装都会创建新目录下的 `.venv`，并每次执行 `pip install -e .`；程序重启时若检测到 editable install 指向旧目录，也会重新执行 pip。这与用户“每次升级就重新安装 Python 依赖”的观察一致。

P0-034 将第三方 Python 依赖从每个版本目录中独立，改为 **同一 Windows 用户账户共享一次**：

- 运行环境在 `%LOCALAPPDATA%\AniFlow\python-env`，不进入 ZIP、不提交 GitHub、不存储密钥。
- 每次检查 `pyproject.toml` 的 `project.dependencies`、运行环境的 Python 主次版本，生成依赖指纹。
- 如指纹不变、关键包存在，直接跳过 pip；如依赖确实改变或运行环境受损，才在共享位置安装/修复。
- 新版本业务代码仍使用当前解压目录的 `src`，启动脚本设置 `PYTHONPATH` 并检查 `aniflow.__file__` 必须属于当前版本，拒绝错误绑定旧代码。
- 不移动、不破坏、不删除此前的 `.venv`，以免损坏用户正在使用的旧版本；版本化 ZIP、Bridge SHA256 检查和安全识别8765端口进程的规则全部保留。
- **首次从v0.33升级到v0.34，需要在电脑上新建共享运行环境，通常还会安装一次依赖；从后续版本起同依赖不再重新安装。** 不能把“以后跳过pip”误称为“本次保证零下载”。
- CI 使用真实 Windows runner：第一次安装 + 第二次安装必须出现 `PASS_ANIFLOW_SHARED_RUNTIME_REUSED_NO_PIP`，并用共享 Python 实际启动 Bridge、两次安全重启、读取真实 `/api/version`。未通过不能发布新版。

## 2. Agnes Flash 503 的根因与本项目决策

用户反馈9条 Key 现在全部503，尚未提供每条脱敏原始响应。若服务商返回 `HTTP 503 / video_queue_full`，Agnes 创建接口直接拒绝任务；没有 `video_id`，扩大状态轮询毫无作用。

已核实证据：

- 上游公开 Issue #63 明确记录 `video_queue_full` 是 Agnes 共享推理队列已满，提交时被拒绝，而非本地参数、密钥或工作站配置错误：https://github.com/lcy362/agnes-video-generator/issues/63
- 上游维护者 Issue #75 回报，自己用真实账户12分钟内25次请求都被拒；明确表示需求已超出免费队列容量、客户端无法保证恢复：https://github.com/lcy362/agnes-video-generator/issues/75
- 上游 v7.1.0/FAQ 将错峰试验作为有限缓解，并未宣布解决容量问题：https://video.lichuanyang.top/zh/faq

因此本次**不再通过修改提示词、盲目增加 Key 并发或重复重装来冒充 Agnes 修复**。界面只将确认 `503/video_queue_full` 的响应明确为“上游队列满、创建被拒”，并提示停止9-Key齐发；单 Key 自愿错峰测试也不意味着能够长期稳定免费生产。其他普通503无明确业务码时不直接断言一定是队列满。

## 3. 后续方向

- 先暂停 Agnes 大批量调用，并保护 Key2 已有历史及尚在跟踪的已创建任务。
- 要实现“长期免费图生视频”，Hugging Face ZeroGPU 是可重复获得免费 GPU 时间的候选，但不保证稳定 API 产能和画质；在没有成功5秒图生样片前不开发第二套系统，不以试用赠金额度冒充长期免费。
- 若整集8镜头需要可靠量产，应重新评估用少量AI动态镜头 + 定格关键帧/本地合成替代方案，不再以9 Key 估算产能。

本次代码/CI没有读取真实 Key、不会触发 Agnes POST、不会部署或合并 main。
