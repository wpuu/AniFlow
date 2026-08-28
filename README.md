# AniFlow｜动画工厂

AniFlow 是一个私有 AI 动画内容生产流水线，目标是用尽量少的人工完成每日短动画生成、自动质检、候选选优和最终成片。

## V0.1 固定方案

- 内容方向：毛毡 / 粘土 / 微缩玩具风格优先
- 主输出：9:16，720×1280
- 单条结构：3 个关键帧（A → B → C）
- 视频结构：A→B 与 B→C 两段，每段默认 5 秒
- 剧情规划 / 视觉裁判：`agnes-2.5-flash`
- 关键帧图片：`agnes-image-2.1-flash`
- 视频：`agnes-video-2.5-flash`
- 多账户策略：默认每个 Agnes 账户至少参与 1 次候选生成；账户少于默认候选数时继续轮换抽卡
- 自动质检：抽取 0/20/40/60/80/100% 六帧，三次独立视觉判断，中位数聚合
- 自动修复：全部候选失败时，根据最佳失败样本诊断自动改写 Video Prompt 后继续抽卡
- 默认生产时区：`Asia/Shanghai`

## Agnes 官方规格

权威文档：https://wiki.agnes-ai.com/en/docs/agnes-video-25-flash

`agnes-video-2.5-flash`：

- 创建：`POST /v1/videos`
- 查询：`GET /agnesapi?video_id=<VIDEO_ID>&model_name=agnes-video-2.5-flash`
- 模式：`text` / `keyframe` / `reference`
- 时长：字符串 `"4"`–`"12"`
- `size`：只能为 `"720P"`
- `n`：只能为 `1`
- `keyframe`：支持 `first_frame`、`last_frame` 或两者同时使用
- `reference`：最多 5 张参考图，不支持参考视频
- 媒体 URL 必须在任务完成前可被 Agnes 公网访问

视频输出尺寸：

| aspect_ratio | pixels |
| --- | --- |
| 21:9 | 1680×720 |
| 16:9 | 1280×720 |
| 4:3 | 960×720 |
| 1:1 | 720×720 |
| 3:4 | 720×960 |
| 9:16 | 720×1280 |

关键帧使用 `agnes-image-2.1-flash` 的 `1K + 9:16`，原生输出 736×1312，再交给视频模型生成 720×1280 成片。

## 当前完整流程

```text
一句创意
  ↓
Agnes 2.5 Flash：三帧分镜 A / B / C
  ↓
Agnes Image 2.1 Flash
A：角色母版 → A
B：角色母版 + A → B
C：角色母版 + B → C
  ↓
A/B/C 持久化到对象存储
  ↓
A→B                         B→C
多账户 Video Flash 抽卡     多账户 Video Flash 抽卡
  ↓                           ↓
下载候选 → FFmpeg 抽六帧 → 临时公网媒体
  ↓
Agnes 2.5 Flash 三类视觉裁判
  ↓
角色一致性 / 风格 / 肢体 / 背景 / 首尾匹配 / 动作 / 剧情 / 吸引力
  ↓
PASS：选择最高分
FAIL：诊断 → 自动修 Prompt → 下一轮
  ↓
最佳 AB + 最佳 BC
  ↓
FFmpeg 重编码拼接
  ↓
10 秒 720×1280 MP4
  ↓
持久化最终视频 + 私有运行记录
```

## 质量门槛

- 综合分 ≥ 82
- 角色一致性 ≥ 88
- 肢体完整 ≥ 85
- 首帧匹配 ≥ 85
- 尾帧匹配 ≥ 85
- 严重畸形、角色替换、数量错误、主体消失、严重穿模等触发 `hard_fail`，不看综合分直接淘汰

## 角色与风格实验

`aniflow character`：

- 先由 Agnes 2.5 Flash 生成稳定 Character Bible；
- 默认生成 `felt / clay / toy` 三套角色母版；
- 每种风格生成正面、3/4、侧面参考；
- 母版持久化到对象存储；
- 私有仓库保存 `data/characters/<id>-<style>.json`。

`aniflow benchmark`：

- 默认先生成同一组 10 个故事；
- 让 felt / clay / toy 各跑完全相同的 10 个故事；
- 总计 30 条视频；
- 比较完成率、AB/BC 平均分、平均重抽轮数和最终视频；
- 报告保存到 `data/benchmarks/`。

这样可以区分“风格稳定性”与“剧情难度”，不是拿三组不同故事做错误比较。

## 每日自动生产

`aniflow daily`：

- 读取历史标题，减少内容重复；
- 使用固定角色 + Benchmark 后选定风格；
- 自动生成当日新故事；
- 自动完成关键帧、视频抽卡、视觉质检、Prompt 修复和拼接；
- 结果写入 `data/daily/history.json` 与 `data/daily/runs/`；
- 默认按 `Asia/Shanghai` 归档日期。

GitHub Actions 已提供：

1. `CI`
2. `Build Character References`
3. `Style Benchmark`
4. `Daily Animation Factory`

Daily workflow 当前默认每天北京时间 02:30 执行，也支持手动运行。

## 对象存储路径

```text
aniflow/
├─ characters/                  # 长期角色母版
├─ episodes/<episode>/keyframes # 每集 A/B/C 稳定关键帧
├─ final/                       # 最终成片
└─ tmp/                         # QA 抽帧；建议 7 天生命周期自动删除
```

仓库、前端、API Key 和内部数据仍然可以保持 Private；只有 Agnes 需要读取的媒体资源需要公网 URL。

## 运行环境

需要：

- Python 3.11+
- FFmpeg / FFprobe
- 多个 Agnes API Key
- S3 兼容对象存储（推荐 Cloudflare R2）

真实 Key 只能放 `.env`、GitHub Actions Secrets 或服务端 Secret Store，禁止提交到仓库或写进浏览器前端。

完整首次配置见 `docs/SETUP.md`。

## 已实现代码

- 多账户 Key Pool 与并行抽卡
- Agnes Image 2.1 Flash Provider
- Agnes Video 2.5 Flash keyframe Provider 与异步轮询
- Agnes 2.5 Flash 多模态三裁判
- 六帧自动抽检
- 候选排序、Hard Fail、自动 Prompt Repair
- S3/R2 兼容公网媒体层
- 三帧 Storyboard 与连续关键帧生成
- Episode A/B/C 持久化
- AB / BC 并行生成
- 最终 720×1280 成片拼接
- Character Bible 与三风格角色母版
- 公平 30 条 Style Benchmark
- 历史去重 Daily Runner
- CLI：`doctor` / `character` / `segment` / `episode` / `benchmark` / `daily`
- CI、角色生成、Benchmark、Daily GitHub Actions workflow
- 单元测试与 Import 测试

## 尚未完成真实验收

代码和 workflow 已落地，但目前仓库中没有真实 Agnes / R2 Secrets，因此不能声称以下项目已经真实跑通：

- 第一次真实 Agnes 多账户端到端生成
- R2 实际上传与 Agnes 公网读取
- 三风格 30 条真实 Benchmark
- Daily 定时真实生成
- AI 评分与人工观感校准
- 接入现有私有多 Key 抽卡前端
- 自动发布到 TikTok / YouTube / Instagram 等平台

长期项目规则与当前状态见 `AGENTS.md`。
