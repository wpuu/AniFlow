# AniFlow｜动画工厂

AniFlow 是一个私有的 AI 动画内容生产流水线，目标是用尽量少的人工完成每日短动画生成、自动质检、候选选优和最终成片。

## V0.1 固定方案

- 内容方向：毛毡 / 粘土 / 微缩玩具风格优先
- 主输出：9:16，720×1280
- 单条结构：3 个关键帧（A → B → C）
- 视频结构：A→B 与 B→C 两段，每段默认 5 秒
- 视频模型：`agnes-video-2.5-flash`
- 视觉裁判：`agnes-2.5-flash`
- 关键帧图片：优先 `agnes-image-2.1-flash`，保留 GPT Image Provider
- 候选机制：支持多个独立 Agnes API Key，每个账户独立参与候选生成
- 目标：候选视频自动抽帧 → 多维视觉评分 → 自动选优 → 失败原因分析 → Prompt 修复 → 重试

## 官方视频参数

`agnes-video-2.5-flash`：

- API：`POST /v1/videos`
- 模式：`text` / `keyframe` / `reference`
- 时长：4–12 秒
- `size`：固定 `720P`
- `n`：固定 `1`
- `keyframe`：支持 `first_frame` / `last_frame`
- `reference`：最多 5 张图片
- 9:16 输出：720×1280

## V0.1 流程

```text
Idea / Story
   ↓
Storyboard A → B → C
   ↓
Keyframe Generator
   ↓
A→B 多账户候选     B→C 多账户候选
   ↓                    ↓
抽取 0/20/40/60/80/100% 帧
   ↓
Agnes 2.5 Flash 三类视觉裁判
   ↓
角色一致性 / 肢体完整 / 首尾匹配 / 动作质量 / 剧情准确 / 视觉吸引力
   ↓
PASS → 选最高分
FAIL → 分析原因 → 修复 Prompt → 重试
   ↓
FFmpeg 拼接
   ↓
10 秒最终视频
```

## 安全

API Key 只允许放在环境变量、GitHub Actions Secrets 或服务端 Secret Store 中，不写入前端源码、日志或仓库。

## 当前阶段

V0.1：先打通“3关键帧 → 多账户视频候选 → Agnes视觉评分 → 自动选优”的核心链路，再接入每日自动生产与发布。
