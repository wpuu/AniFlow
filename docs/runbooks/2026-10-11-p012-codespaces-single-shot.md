# AniFlow P0-012｜纯云端单镜头验证操作卡（GitHub Codespaces）

**日期：2026-10-11，时区：北京时间。** 本文是可实际使用的操作说明，不是“已调用 Agnes 出片”报告。工程代码在隔离分支 `audit/2026-10-11-v710-revalidation`，草稿 [PR #2](https://github.com/wpuu/AniFlow/pull/2)，**不合并 `main`，不部署服务，不默认发送视频生成请求**。

## 推荐入口

**[打开该隔离分支的 GitHub Codespaces 创建页面](https://codespaces.new/wpuu/AniFlow/tree/audit/2026-10-11-v710-revalidation)**

GitHub 官方支持指定分支直达创建页面；打开链接**不是立即收费或创建**，仍需用户确认环境和计费承担者。文档：https://docs.github.com/en/codespaces/setting-up-your-project-for-codespaces/setting-up-your-repository/facilitating-quick-creation-and-resumption-of-codespaces

### 第一步：由账号持有人创建云端环境（不可代填密钥）

1. 点击上述链接，确认界面当前仓库为 `wpuu/AniFlow`、分支为 `audit/2026-10-11-v710-revalidation`。若界面没有指向此分支，停止，不从 `main` 创建。
2. 选择 Codespaces 的 **New with options（使用选项新建）**，使用仓库自带 `.devcontainer/devcontainer.json`；优先选择可用的最低资源档。**先看界面上的承担费用者与剩余免费配额**；如不愿产生 GitHub 计算/存储费用，则不要创建。
3. 创建页可能提示一个**可选的推荐密钥**：`ANIFLOW_SINGLE_SHOT_API_KEY`。只能由你在 GitHub 的加密表单中填入一个有合法使用权限的 Agnes Key，选择只允许 **wpuu/AniFlow** 使用。不要把 Key 粘到 ChatGPT、Issues、PR、文件、工作流参数或终端命令行。
4. 没有 Key 可以**不填写并先创建 Codespace**，运行下方只预览测试。Codespaces Secret 可在 GitHub → Settings → Codespaces 设置；当前 Codespace 新增密钥后可停止/重新启动以确保其被注入。官方安全说明：
   - https://docs.github.com/en/codespaces/managing-your-codespaces/managing-your-account-specific-secrets-for-github-codespaces
   - https://docs.github.com/en/codespaces/setting-up-your-project-for-codespaces/configuring-dev-containers/specifying-recommended-secrets-for-a-repository

环境安全属性：`.devcontainer/Dockerfile` 以**官方 Python 3.11 Debian 镜像**预装 FFmpeg、Git、HTTPX；镜像构建期间不能读取 GitHub Codespaces secrets。本项目没有 `postCreateCommand` / `postStartCommand` 等自动运行 Hook，也不默认转发服务端口。**创建环境绝不会自动 POST Agnes 视频接口**。GitHub Codespaces 运行在浏览器云端，不需要用户 Windows 笔记本保持开机。

### 第二步：只预览，确保一笔 API 费用都不会触发

在 Codespaces 的 Terminal（终端）中执行：

```bash
git branch --show-current
python scripts/one_agnes_real_shot.py
```

预期显示：

- 分支：`audit/2026-10-11-v710-revalidation`；
- `result: PLAN_ONLY_NO_REQUESTS`、`submissions: 0`；
- 固定 `MYCL-001` 第 1 镜头、`agnes-video-2.5-flash`、`5` 秒、`720P`、`9:16`；
- 不打印或读取 Key；不写证据文件；不联网、不收费。

若这些内容不符合，**不执行下一步**。完整镜头表及事实包有 SHA-256 锁定；不要临时替换成未审核的宣传片素材。

### 第三步：如果你明确同意提交“一条真实视频”

**先去你的 Agnes 平台账户确认当前价格、API 来源域名和 Key 是否有效**。官方公开文档当前显示 Flash 720P 限时 `$0/秒`，但政策可能调整；本程序不会自动读取账户实际余额/最终扣费。已确认并接受潜在费用后才继续：
https://wiki.agnes-ai.com/zh-Hans/docs/agnes-video-25-flash

先建立**Git 仓库之外、但位于 Codespaces 重建后仍保留的 `/workspaces` 持久化卷内**的私有存储目录，再执行一次创建：

> **P0-015 修正：不要再使用旧版 `$HOME/aniflow-private` 路径。** GitHub 官方确认 Codespaces 容器重建会清理 `/workspaces` 以外的容器目录；旧路径不仅可能丢失 MP4，而且原有 `~/.local/state/aniflow-single-shot` 单次提交锁也会丢失。新代码在 Codespaces 中对临时主目录输出**直接拒绝**，并将唯一提交锁放在 `/workspaces/.aniflow-private/single-attempt-ledger/MYCL-001-shot-1.once.json`。如果曾用旧版提交，请先核实原视频与 Agnes 平台历史任务，**不得因重建后丢失锁而重新提交**。官方依据：https://docs.github.com/en/codespaces/developing-in-a-codespace/rebuilding-the-container-in-a-codespace#persisting-data-over-a-rebuild


```bash
mkdir -p "/workspaces/.aniflow-private"
python scripts/one_agnes_real_shot.py \
  --execute \
  --i-reviewed-current-charges \
  --domain global \
  --output-dir "/workspaces/.aniflow-private/mycl001-shot1"
```

**国内 Key 使用前需核实域名**；若属于中国平台，请把 `--domain global` 改成 `--domain china`，切勿为了猜测域名连续提交多次。确认读取的是 `ANIFLOW_SINGLE_SHOT_API_KEY`；不要把密钥写入命令本身。

安全规则：

- **仅 1 Key × 1 个 5 秒视频**，不批量抽卡、不调用旧 `queue-probe`，无后台无限重试。
- 提交前持久写入 `MYCL-001-shot-1.attempt.json`。如果提交响应丢失，任务**可能已经创建**，禁止换目录重新 `--execute`；只能先查供应商账户任务记录。
- 如果已取得 `video_id`，后续可在相同目录下仅轮询**既有任务**：

```bash
python scripts/one_agnes_real_shot.py \
  --resume \
  --i-reviewed-current-charges \
  --domain global \
  --output-dir "/workspaces/.aniflow-private/mycl001-shot1"
```

- 已下载的 `MYCL-001-shot-1.mp4` 与 `*.attempt.json` 存放在**仓库外的 `/workspaces/.aniflow-private/mycl001-shot1` 持久目录**（容器重建后仍存在），不要提交公开 GitHub。不向外部 CDN 发送 Agnes Key。
- 元数据通过只能表明 9:16 显示尺寸、时长、分辨率等合格；**还要本人完整观看画面**，排除像素横倒、角色/科学动态错误、伪影。暂不能发布或算作商业成品。

### 第四步：回收证据并关闭计费资源

真实文件保存在仓库目录的**兄弟目录** `/workspaces/.aniflow-private/mycl001-shot1`，不会自动出现在仅打开 `AniFlow` 仓库的文件树中。可以在 VS Code Web 的 **File → Open Folder（打开文件夹）** 进入此路径，下载真实 MP4 与无密钥 JSON 验收记录；请勿将它们复制进 Git 仓库。记录运行的 UTC/北京时间、单次实际请求、`video_id`、下载文件 SHA-256、收费记录（如有）、视频是否真正竖直。不要上传任何真实 Key 或账户余额等私密证据到公开 PR。

**完成后停止 Codespace**，不再持续消耗计算配额；若视频已安全下载并不需要保留云端目录，可按 GitHub 指引删除 Codespace 以避免存储长期占用。

GitHub Codespaces 对部分个人账号包含月度免费计算/存储额度，但剩余额度和超额计费必须以账户 UI 为准：https://docs.github.com/en/codespaces/troubleshooting/troubleshooting-included-usage

## 已有可验证证据与严格未完成事项

- 官方 v7.1.0 无 Key Windows 原生服务启动：已在 GitHub Actions 通过（此前 P0-009）。
- Linux/Windows 全仓库 283/283 Pytest：此前 P0-011 通过。
- Codespaces 基础云端容器：GitHub [P0-012 实际构建和断网测试 #38113959808](https://github.com/wpuu/AniFlow/actions/runs/38113959808) **SUCCESS**，无真实 Key、只读 Git 目录、无外网，**25/25 模拟接口测试通过**。此前因基础镜像自带 Yarn 源签名失效，已改用独立官方 Python Debian Slim 镜像，不降低 APT 签名安全检查。
- **未完成**：在用户自己的 Codespace 实例验证 Key 注入；首次真实 Agnes Video POST；真实任务 ID、生成耗时、真正 Agnes MP4、像素视觉方向和商业用途。这些仍必须由可信 Key 持有人明确执行。

下一轮在 Codespace 配置完成后，继续 P0-012 的真 Key/真片证据采样，完成才解除 Issue #5 的首次真实视频阻塞。建议 GPT-6 Luna Medium；疑难异步队列/视频方向 High。


> **P0-015 持久化范围声明：** `/workspaces` 能防止同一个 Codespace 的 stop/start 与 container rebuild 丢失数据，但**不同 Codespace 是不同的存储卷**。跨 Codespace 创建新实例不能认为已经清空原有视频任务；先检查 Agnes 平台任务历史和此前的 `once.json`，不得盲目第二次提交。
