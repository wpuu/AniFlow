# Cloudflare R2 最短配置（AniFlow 首轮 Benchmark）

目标：只为 AniFlow 提供 Agnes 能访问的公网图片/视频 URL。首轮 30 条 Benchmark 可先使用 Cloudflare 管理的 `r2.dev` 开发 URL，不需要先配置自己的域名。

> `r2.dev` 是开发/测试用途并有速率限制。AniFlow 验证成功并开始长期生产后，再切自定义域名。

## 1. 创建 Bucket

Cloudflare Dashboard → **Storage & databases → R2 → Overview → Create bucket**。

建议名称：

```text
aniflow-media
```

首轮测试无需特殊 Location 或 Storage Class 设置。

## 2. 开启公网开发 URL

进入 `aniflow-media` → **Settings → Public Development URL → Enable**。

按页面要求输入 `allow` 确认。

记录页面显示的 Public Bucket URL，例如：

```text
https://pub-xxxxxxxxxxxxxxxx.r2.dev
```

这个值就是 GitHub Secret：

```text
S3_PUBLIC_BASE_URL
```

末尾不要手工添加 `/aniflow`。

## 3. 创建只针对该 Bucket 的 S3 凭据

R2 Overview → **Manage R2 API tokens** → Create API token。

建议：

- Permission: **Object Read & Write**
- Scope: **specific bucket only**
- Bucket: `aniflow-media`

创建后页面会显示：

- Access Key ID
- Secret Access Key
- S3 API endpoint

Secret Access Key 通常只显示一次，直接保存进 GitHub Actions Secret，不要写入仓库或 Issue。

对应 AniFlow：

```text
S3_ACCESS_KEY_ID=<Access Key ID>
S3_SECRET_ACCESS_KEY=<Secret Access Key>
S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
S3_BUCKET=aniflow-media
S3_PUBLIC_BASE_URL=https://pub-xxxxxxxxxxxxxxxx.r2.dev
```

GitHub Variable：

```text
S3_REGION=auto
```

## 4. GitHub 需要的 6 个 Secrets

`wpuu/AniFlow` → **Settings → Secrets and variables → Actions → New repository secret**：

```text
AGNES_API_KEYS
S3_ENDPOINT_URL
S3_ACCESS_KEY_ID
S3_SECRET_ACCESS_KEY
S3_BUCKET
S3_PUBLIC_BASE_URL
```

`AGNES_API_KEYS` 格式：

```text
key_account_1,key_account_2,key_account_3
```

只用英文逗号分隔，不加引号。

## 5. 一键验证

GitHub → **Actions → Setup Preflight → Run workflow**。

成功结果必须满足：

```text
所有 Agnes account: ok=true
media_upload_ok: true
media_public_read_ok: true
media_delete_ok: true
ok: true
```

Preflight 只产生一个极小临时文本对象，读取验证后马上删除，不会开始生图或生视频。

## 6. Preflight 成功后

按顺序执行：

1. `Build Character References`
2. `Style Benchmark`
3. 人工快速审阅 30 条
4. 再决定 Daily 主风格和评分门槛

## 官方参考

- R2 S3 API: https://developers.cloudflare.com/r2/get-started/s3/
- Public buckets / r2.dev: https://developers.cloudflare.com/r2/buckets/public-buckets/
- R2 API tokens: https://developers.cloudflare.com/r2/api/tokens/
