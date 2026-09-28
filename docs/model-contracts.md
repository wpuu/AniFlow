# Agnes 模型契约（已核实）

最后核实：**2026-09-28 15:26 CST** · 核实人：`Claude Opus 5.5`
来源：`https://wiki.agnes-ai.com/llms.txt` 官方文档索引 + 各模型官方页 + 官方 Pricing 页。

> 本文件是 AniFlow「每个模型必须使用自己的正确配置」这条强制要求的**唯一事实来源**。
> 任何代码里的模型参数都必须能在本文件找到依据。改模型前先改本文件。

---

## 0. 全局

| 项 | 值 |
|---|---|
| Base URL | `https://apihub.agnes-ai.com/v1` |
| 认证 | `Authorization: Bearer <AGNES_API_KEY>`（Messages API 用 `x-api-key`） |
| 厂商 | Agnes AI（Sapiens AI，新加坡） |
| 一个 Key 覆盖 | 文本 + 图片 + 视频 全部模型 |

**官方文档索引里现存的模型，就是全部模型。** 截至核实日共 9 个：

- 文本：`agnes-2.5-flash`、`agnes-2.5-pro-beta`、`agnes-2.5-pro`、`agnes-3.0-flash`
- 图片：`agnes-image-2.0-flash`、`agnes-image-2.1-flash`、`agnes-image-2.5-flash`
- 视频：`agnes-video-2.5`、`agnes-video-2.5-flash`

### ⚠️ 已消失的模型

| 模型 | 状态 | 依据 |
|---|---|---|
| `agnes-video-v2.0` | **已下架**。文档索引无、Pricing 页无 | 项目前端仍保留其完整参数契约，属死代码 |
| `agnes-2.0-flash` | 已弃用（Deprecated） | 官方 2.5 Flash 页明确标注 |

---

## 1. 价格（核实日）

| 模型 | 计费项 | 标价 | 现价 |
|---|---|---|---|
| `agnes-2.5-flash` | 输入 / 输出 | $0.05 / $0.15 每 M | **$0** |
| `agnes-3.0-flash` | 输入 / 输出 | $0.05 / $0.15 每 M | **$0** |
| `agnes-2.5-pro-beta` | 输入 / 输出 | $0.10 / $0.30 每 M | 照价收费 |
| `agnes-2.5-pro` | 输入 / 输出 | $0.45 / $0.90 每 M | 照价收费 |
| `agnes-image-2.0/2.1/2.5-flash` | 1K/2K/3K/4K 出图 | $10/$18/$21/$24 每千张 | **$0（全档位）** |
| 同上 | 第 4 张起的参考图 | $0.003 / 张 | **$0** |
| `agnes-video-2.5` | 720P / 1080P | $0.025 / $0.040 每秒 | **照价收费** |
| `agnes-video-2.5-flash` | 720P | $0.025 每秒 | **$0** |

> **结论：AniFlow 生产链可做到 100% 零 API 成本** —— `agnes-3.0-flash` + `agnes-image-2.5-flash` + `agnes-video-2.5-flash`。
> `agnes-video-2.5`（非 Flash）是唯一会真实产生视频费用的模型，**不要默认启用**。
> 现价为促销价，随时可能恢复标价。恢复后一条 60 秒视频的视频费约 $1.5（按 $0.025/s）。

---

## 2. 文本模型

### `agnes-3.0-flash` ← 建议的新主力

| 项 | 值 |
|---|---|
| 端点 | `POST /v1/chat/completions`（另支持 `/v1/responses`、`/v1/messages`） |
| 输入 | 文本 + **图片 URL** |
| 输出 | **仅文本** |
| 最大输出 | 65,536 tokens |
| 上下文 | **生产 API：1,000,000 tokens** |
| 参数 | `model` `messages` `temperature` `top_p` `max_tokens` `stream` `tools` `tool_choice` `chat_template_kwargs` |
| 能力 | 函数调用、多步工具编排、可选 thinking 模式 |

### 🚨 Preview ≠ 生产（必须记住）

| | 开源 Preview（HuggingFace） | 生产 API |
|---|---|---|
| 参数量 | 33B | 未公开，不同 checkpoint |
| 上下文 | 262,144 | 1,000,000 |
| 许可 | Apache-2.0 | 专有，仅 API |
| 跑分 | 仅适用于 Preview 权重 | Artificial Analysis 榜上的 36 分指这个 |

**开源 Preview 的跑分、上下文、行为一律不可迁移到生产 API，反之亦然。**
（注：另有第三方 OpenClaw 配置声称实测 524,288 上下文，与官方 1M 不符 —— 以官方为准，实际上限需自测。）

### `agnes-2.5-flash`（现主力，建议降级为备用）

同样是 OpenAI 兼容 `/v1/chat/completions`，参数表与 3.0 Flash 基本一致，输入支持文本 + 图片 URL。
3.0 Flash 在同价（都免费）下更强更快（235 tok/s vs 159.5 tok/s），**无理由继续把 2.5 Flash 当主力**。

---

## 3. 图片模型

### `agnes-image-2.5-flash` ← 建议的新主力

| 项 | 值 |
|---|---|
| 端点 | `POST /v1/images/generations` |
| 能力 | 文生图、图生图、**多图合成（multi-image composition）** |
| `model` | 必填 |
| `prompt` | 必填 |
| `size` | 必填。**档位制**：`1K` `2K` `3K` `4K` |
| `ratio` | 选填。`1:1` `3:4` `4:3` `16:9` `9:16` `2:3` `3:2` `21:9`，默认 `1:1` |
| `image` | `string[]`，图生图/多图合成必填。公网 URL 或 Data URI Base64 |
| `return_base64` | 选填，**仅文生图**用 |
| `extra_body.response_format` | `url` 或 `b64_json` |

**9:16 输出尺寸**：1K=`736x1312`，2K=`1472x2624`，3K=`2208x3936`，4K=`2944x5248`

**坑（官方明确警告）**：
- `response_format` **不能放请求体顶层**，必须放 `extra_body`。
- 图生图的输入图走 `extra_body.image`。
- 传 `1920x1080` 这类精确尺寸会被归一化到最近档位，**不要依赖精确像素**。
- 图生图**不需要** `tags: ["img2img"]`。

### 与 `agnes-image-2.1-flash` 的关系

官方原话：请求/响应参数、支持尺寸、价格、计费方式**与 2.1 Flash 完全相同**，质量「全面超越」2.1 Flash。
→ **可直接换模型字符串升级，零改造成本。**

### ⚠️ 2.0 与 2.5 的参数不兼容（这就是为什么必须每模型独立 Schema）

| | `agnes-image-2.0-flash` | `agnes-image-2.5-flash` |
|---|---|---|
| `size` 语义 | 像素串，如 `1024x768` | 档位，如 `2K` |
| `ratio` | 文档未列 | 独立参数 |

**把 2.0 的 `size` 直接塞给 2.5 会得到错误画幅。禁止共用一套 Schema。**

---

## 4. 视频模型

### `agnes-video-2.5-flash` ← 生产主力（免费）

| 项 | 值 |
|---|---|
| 创建 | `POST /v1/videos` |
| 查询 | `GET https://apihub.agnes-ai.com/agnesapi?video_id=<ID>&model_name=agnes-video-2.5-flash` |
| 轮询 | 每 1–2 秒，直到 `status` = `completed` / `failed` |
| 取结果 | 顶层 `url` 字段 |

**请求参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `model` | string | ✅ | `agnes-video-2.5-flash` |
| `prompt` | string | ✅ | reference 模式内用 `<Picture N>` / `<Audio N>` 指代输入 |
| `mode` | string | ✅ | `text` / `keyframe` / `reference` |
| `seconds` | string | ❌ | **字符串** `"4"`–`"12"`，默认 `"5"` |
| `size` | string | ❌ | **Flash 只接受 `"720P"`**，其他值 HTTP 400 |
| `aspect_ratio` | string | ❌ | 默认 `16:9`；AniFlow 用 `9:16` |
| `seed` | integer | ❌ | |
| `n` | integer | ❌ | **只支持 1** |

**模式专属参数与互斥规则（关键）**

| `mode` | 必需媒体 | **禁止出现的字段** |
|---|---|---|
| `text` | 无 | `first_frame` `last_frame` `images` `audios` `videos` |
| `keyframe` | `first_frame` / `last_frame` 至少一个 | `images` `audios` `videos` |
| `reference` | `images` / `audios` 至少一个非空 | `first_frame` `last_frame` `videos` |

> 🔑 **架构级含义：`keyframe` 与 `reference` 互斥。**
> 不能既锁定首尾帧、又同时喂角色参考图。
> → 角色一致性必须在**上游图片阶段**解决（用 `agnes-image-2.5-flash` 多图合成从 Identity Anchor 出帧），
> 视频阶段用 `keyframe` 继承一致性。`reference` 模式是无精确帧时的备选路线。

**Flash 相对 `agnes-video-2.5` 的额外限制**

| 校验 | Flash 规则 | 失败响应 |
|---|---|---|
| `size` | 只能 `"720P"` | `size must be 720P` |
| `images` | ≤ **5** 张 | `images length must not exceed 5` |
| `audios` | ≤ **3** 个 | `audios length must not exceed 3` |
| `videos` | **完全不支持** | `videos is not supported` |

校验在建任务/排队/计费/推理之前执行，非法请求不建任务也不计费。

**所有媒体 URL 必须是 Agnes 可公网访问、且在任务完成前持续有效。**
→ 这是 R2 / S3 公网媒体层存在的根本原因，**不可省略**。

### `agnes-video-2.5`（非 Flash，收费）

继承全部 Flash 能力，额外支持：
- `size` 可到 1080P / 1K（$0.040/s）
- `images` ≤ 8 张（单张 <15MB，边长 256–5760px）
- `videos` 视频参考（1 个，2–12 秒，<50MB，24–60 FPS，含 `start_seconds`、`require_audio`）
- 单请求参考媒体总数 ≤ 12

**AniFlow 暂不启用**（唯一真实花钱项）。仅在 Flash 质量确实不够、且已验证 1080P 有商业必要时再考虑。

### 视频原生音频（未验证）

官方示例 prompt 含「natural footsteps and instrument sounds」「natural ambience」，且视频参考有 `require_audio` 参数，**强烈暗示视频输出自带音轨**。
但官方未明确声明，**AniFlow 必须实测确认**。即使自带环境音，也**无法承载精确中文台词** —— 台词仍需外部 TTS。

---

## 5. Agnes 没有的东西

**Agnes 全线没有 TTS / 语音合成 / 语音克隆模型。** 文档索引只有 Text / Image / Video 三类。

→ AniFlow 的配音必须外接。见接管审计文档中的 TTS 选型结论。
