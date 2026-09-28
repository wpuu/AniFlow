# 方向变更：视频层改为复用开源引擎，不再自己造

`2026-09-28 | Claude Opus 5.5` | 分支 `main` | 状态：已实现补丁 + 安装器，待用户实机验证

---

## 起因

用户问：「GitHub 上是不是有现成的生成应用？你优化一下给我用不就行了吗」

用户是对的。我前几轮一直在 AniFlow 里手搓视频提交层和队列探测工具，
而社区已经有成熟实现。查证结果如下。

---

## 调研结果

用 GitHub API 搜了 `agnes video generator` / `agnes studio` / `agnes-ai` 等，
按星数和活跃度筛出 6 个，重点评估 3 个：

| 项目 | 星 | 协议 | 形态 | 多 Key | 结论 |
|---|---|---|---|---|---|
| **lcy362/agnes-video-generator** | 436 | MIT | Python + Web UI，`start.bat` 一键 | ✅ `KeyRing` 轮换 | **选它** |
| liobububu/agnes-manga-studio | 37 | Apache-2.0 | Electron，88MB exe | ❌ 单 Key | 领域最接近，但无多 Key |
| LingyunStudio/AgnesStudio | 51 | MIT | Rust，5MB exe | ❌ 单 Key | 最轻，但只够手动单发 |

`lcy362/agnes-video-generator` 的实际能力（读码确认，非看 README）：

- `core/api/key_manager.py` 的 `KeyRing`：round-robin 轮换 + 429 强制换 Key
- `core/api/rate_limiter.py`：视频提交独立令牌桶，速率与容量都按 **1 × Key 数** 计
- `core/api/agnes_video.py`：`video_queue_full` / `fail_to_fetch_task` **独立退避轨道**，
  不占用普通 5xx 的重试配额，默认预算 900 秒
- 断点续跑、SSE 进度、22 语言错误提示、Docker、459 文件 / 约 5.3 万行、约 1300 个测试
- 最近一次提交就在今天（2026-09-28），仍在活跃维护

它的代码注释里写着「实测 video_queue_full 可持续 12 分钟以上（连续 25 次被拒）」
—— 与我们今天实测的队列饱和现象完全吻合，说明这是该模型的普遍状况，不是我们的配置问题。

---

## 找到的缺陷（也就是「优化」）

**队列满时不换账号。**

- HTTP **429** → 立刻 `ring.rotate()` 换下一个 Key 重试，不 sleep
- HTTP **503 `video_queue_full`** → 直接 `await asyncio.sleep(30~60s)`，
  靠下一轮循环顶上的 `ring.next()` 才轮到下一个账号

后果：9 个账号轮完一圈要 **4.5 ~ 9 分钟**。
如果队列是按账户隔离的，这几分钟里其余 8 个账号可能全是空的。

这不是设计取舍，是漏了一处——它自己的限速桶 burst 就是 `1 × Key 数`，
注释写明「允许每 Key 立即提交一次」，也就是说**连续换 Key 重试用的正是它预留的配额**。

### 补丁

在 `_submit_with_retry` 的 queue_full 分支里，退避之前先把其余账号试一遍；
全部被拒才回到原来的退避节奏。退避预算语义不变，单 Key 行为完全不变。

补丁文件：`docs/patches/queue-full-rotate-keys.patch`

### 附带价值

这个补丁顺手回答了我们悬了一整天的问题：
**如果换账号之后立刻成功，就证明队列是按账户隔离的。**
不需要另外跑探测工具，生产过程本身就是实验。

---

## 验证状态

| 项目 | 状态 |
|---|---|
| 补丁锚点与上游 v7.0.4 原文逐字符匹配（各命中 1 次） | ✅ |
| 打补丁后 Python 语法有效 | ✅ |
| 新增 4 个测试覆盖：先换账号 / 全拒才退避 / 单 Key 行为不变 / 不偷吃退避预算 | ✅ |
| 撤掉补丁后这些测试如期失败（证明测试有效） | ✅ |
| 上游全量测试（约 1300 个）通过 | ✅ 仅跳过 3 个依赖 ffmpeg 的文件，沙箱未装，与改动无关 |
| 安装器的下载 / 解压 / 打补丁 / 写 .env 流程 | ⚠️ 逻辑已模拟验证，**Windows 实机未验证** |
| 真实跑出一条视频 | ❌ **仍未做到**，队列全天饱和 |

---

## 对 AniFlow 的影响

用户早先定的边界是「可借鉴开源 Agnes 项目实现，但不得把 AniFlow 变成
Agnes Studio / Agnes Video Generator 的重复品」。这次正好落在该边界的正确一侧：

**把 agnes-video-generator 当作视频渲染引擎，AniFlow 保留自己的差异化层。**

- 不再自己维护：视频提交、队列退避、多 Key 轮换、任务轮询、断点续跑
- 继续自己做：IP 体系、选题、事实核验（Fact Pack）、编剧、角色一致性、
  QA、配音字幕、商业化内容生产

因此 AniFlow 里 `src/aniflow/pipeline/gacha.py`、`src/aniflow/agnes/`、
`src/aniflow/queue_probe.py` 这几块的定位需要重新评估——
它们解决的问题上游已经解决得更好。**本次先不删**，等实机验证通过再动。

---

## 下一步

1. 用户实机跑安装器，确认能启动
2. 观察补丁行为：出现「换账号立即重试」后是否有账号成功 → 直接得出队列模型结论
3. 拿到第一条真实视频，人眼确认毛毡风格动态稳定性
4. 视结果决定 AniFlow 旧视频层的删减范围
5. 补丁可考虑回馈上游（搜过 issue / PR，无人提过同样问题）
