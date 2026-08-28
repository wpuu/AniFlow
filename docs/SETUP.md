# AniFlow 首次运行配置

AniFlow 的代码、前端和 GitHub 仓库都可以保持 Private。只有需要被 Agnes 读取的图片 / 抽帧 / 最终视频使用公网媒体 URL。

## 1. GitHub Secrets

在 `wpuu/AniFlow` → Settings → Secrets and variables → Actions → Secrets 中添加：

| Secret | 内容 |
| --- | --- |
| `AGNES_API_KEYS` | 多个独立 Agnes 账户的 API Key，用英文逗号分隔 |
| `S3_ENDPOINT_URL` | S3 兼容对象存储 endpoint；推荐 Cloudflare R2 S3 endpoint |
| `S3_ACCESS_KEY_ID` | 对象存储 Access Key ID |
| `S3_SECRET_ACCESS_KEY` | 对象存储 Secret Access Key |
| `S3_BUCKET` | Bucket 名称 |
| `S3_PUBLIC_BASE_URL` | 可以直接公网访问对象的 HTTPS 基础地址 / 自定义域名 |

不要把任何真实 Secret 写入 `.env.example`、README、Issue、Actions 输入框或前端代码。

## 2. GitHub Variables

同一页面的 Variables 中可配置：

| Variable | 建议初值 | 作用 |
| --- | --- | --- |
| `S3_REGION` | `auto` | R2 使用 `auto` |
| `ANIFLOW_CANDIDATES_PER_SEGMENT` | `5` | 最少候选数；实际默认仍会保证每个 Agnes 账户至少参与一次 |
| `ANIFLOW_MAX_REPAIR_ROUNDS` | `2` | 首轮全部失败后最多再修复/重抽 2 轮 |
| `ANIFLOW_PASS_SCORE` | `82` | 综合合格线 |
| `ANIFLOW_CHARACTER_ID` | Benchmark 后确定 | Daily workflow 使用的角色 |
| `ANIFLOW_STYLE` | Benchmark 后确定 | Daily workflow 使用的胜出风格，如 `felt` |
| `ANIFLOW_DAILY_COUNT` | `3` | 每天计划生成条数 |
| `ANIFLOW_DAILY_CONCURRENCY` | `2` | 并行 Episode 数 |

## 3. 对象存储要求

AniFlow 需要一个 S3-compatible Bucket；Cloudflare R2 是推荐实现，但代码没有绑定 R2。

需要满足：

1. 程序可以通过 S3 API 上传对象；
2. `S3_PUBLIC_BASE_URL/<object-key>` 可以在不登录、不带 Cookie、不带私有请求头的情况下由 Agnes 直接读取；
3. HTTPS 正常；
4. Character References 和 `aniflow/final/` 应长期保存；
5. `aniflow/tmp/` 只是视觉质检抽帧，建议对象存储配置生命周期规则：7 天后自动删除该前缀下对象。

对象路径约定：

```text
aniflow/
├─ characters/       # 长期角色母版
├─ final/            # 最终成片
└─ tmp/              # QA 抽帧，建议 7 天生命周期删除
```

## 4. 第一次正确执行顺序

### Step A — CI 基础检查

GitHub → Actions → `CI`。

CI 不需要 Agnes Secret 即可运行单元测试；它只验证 Python 包、导入、评分规则和基础逻辑。

### Step B — 创建角色母版

Actions → `Build Character References` → Run workflow。

建议第一角色保持极简，例如：

- `character_id`: `filo`
- `name`: `Filo`
- description: `A small orange fox with a white muzzle, black button eyes, short limbs, a green scarf, and a slightly bent left ear.`
- styles 留空：系统自动生成 `felt / clay / toy` 三套母版。

成功后私有仓库会新增：

```text
data/characters/
├─ filo-felt.json
├─ filo-clay.json
└─ filo-toy.json
```

三个 JSON 保存的是长期 R2 公网图片 URL，不保存 API Key。

### Step C — 三风格公平 Benchmark

Actions → `Style Benchmark` → Run workflow。

初次参数：

- `character_id`: `filo`
- `per_style`: `10`
- `styles`: 留空
- `concurrency`: `2`

系统先生成同一组 10 个故事，然后：

```text
10 felt + 10 clay + 10 toy = 30 条
```

不是三组不同故事，所以风格间可以公平比较。

Benchmark 报告写入：

```text
data/benchmarks/<run_id>.json
```

主要比较：

- completion_rate
- mean_ab_score
- mean_bc_score
- mean_rounds
- 每条 final_public_url

AI 分数只负责第一轮机器筛选。首个 30 条 Benchmark 最终仍建议人工快速看一遍，确认 AI 评分与实际观感是否一致，再固定 Daily 的风格。

### Step D — 固定 Daily

在 GitHub Variables 设置：

```text
ANIFLOW_CHARACTER_ID=filo
ANIFLOW_STYLE=<benchmark 胜出风格>
ANIFLOW_DAILY_COUNT=3
ANIFLOW_DAILY_CONCURRENCY=2
```

`Daily Animation Factory` 默认每天北京时间 02:30（UTC 18:30）执行，也可以手动 Run workflow。

每日结果写入：

```text
data/daily/history.json
data/daily/runs/<run_id>.json
```

最终 MP4 写入：

```text
aniflow/final/<episode-id>.mp4
```

## 5. 当前故意没有做的事

V0.1 不自动发布 TikTok / YouTube / Instagram，也不自动把所有 AI 通过的视频视为可发布内容。

正确顺序是：

1. 先完成 30 条风格 Benchmark；
2. 校准视觉评分；
3. 连续生成一批 Daily 内容；
4. 确认严重缺陷漏检率足够低；
5. 再接现有私有前端和外部发布。

这样可以把 Agnes 的免费生成能力大量用于实验，但不把低质量自动内容直接发布出去。
