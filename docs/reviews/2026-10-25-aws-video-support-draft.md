# AWS 账户/账单支持咨询草稿（用户已否决，未发送）

2026-10-25 决策：用户明确要求不要联系 AWS 客服。此草稿已取消，不发送，也不继续等待发送授权。下文仅作为历史记录保留。

本草稿只核实已有账户的视频生成资格、赠金与账户限制；不授权升级付款计划、不订阅付费支持、不申请8 vCPU GPU配额，不请求创建或调用任何计费资源。发送给AWS工作人员前需要用户明确授权。

## 主题

已有 Free Tier/Explore AWS 赠金将于2026-10-30到期：请确认 Bedrock Ray2 的赠金抵扣资格和账户并发0原因

## 正文

您好，我希望在现有赠金到期前，用本人AWS账户生成少量真实视频，费用控制在赠金覆盖范围内，不增加额外自付费用。

账户Credits页面有5笔活动积分，到期日期均显示2026-10-30；预计剩余总额USD49.96（页面提示约24小时更新）。逐笔Applicable products中均包含AmazonBedrockFoundationModels、Amazon Bedrock、Amazon Simple Storage Service等服务。

我在官方Price List发现，Luma Ray2（Amazon Bedrock Edition）的服务代码为AmazonBedrockFoundationModels。我能在Oregon地区打开模型详情和Playground，但Service Quotas显示：

- 区域：us-west-2。
- 模型：luma.ray-v2:0。
- 配额：On-demand model inference concurrent requests for Luma Ray V2。
- 配额代码：L-3447D96F。
- Applied account-level quota value：0。
- AWS default quota value：1。
- Adjustability：不可调整。

目前尚未调用模型、创建S3桶或升级账户计划。请帮助确认：

1. 本账户上述现有赠金是否明确抵扣Ray2的AmazonBedrockFoundationModels计费，以及所需S3存储费用？是否有模型级别例外、税费或其他无法被赠金抵扣的费用？
2. Ray2账户实际并发为0而默认为1，是账户计划、未开通权益还是账户级服务限制？在不升级付款计划、不增加额外自付费用的条件下，是否有正常的开通或纠正途径？请不要将“首次调用自动订阅”当作已经确认提升实际配额。
3. 若Ray2不能使用，请告知本账户当前有哪些已有权限/额度的AWS视频生成服务可使用这些赠金，以及2026-10-30到期的准确时刻/时区。

我不要求创建资源、启用付费支持、自动升级计划或发起GPU额度增加；请先解释当前资格与限制，任何账户变更前请征得本人同意。

感谢。
