# 目标纠正：仅使用现有 AWS 赠金生成视频

日期：2026-10-25，Asia/Shanghai。用户明确拒绝把赠金问题改成外部平台自付费；此前外部 API / GPU 的优先推荐不符合本次核心目标，现撤回。只继续研究、核查可由本人现有 AWS 赠金抵扣的真实视频路径；不自动购买外部服务，不申请配额，不升级付款计划。

## 对旧判断的实质纠正

之前直接用 Marketplace 一般排除条款否决 Bedrock Ray2，证据不足。五笔赠金的实际完整服务清单逐字都含 **AmazonBedrockFoundationModels**；Ray2 的官方 Price List 服务代码也为 **AmazonBedrockFoundationModels**，名称为 **Luma Ray2 (Amazon Bedrock Edition)**。这形成具体的产品级匹配证据，不能只看到 Marketplace 字样就机械判为不适用。仍未获得该账户 Ray2 的实际抵扣账单，不能声称已验证零自付。

官方证据：[Ray2 模型卡](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-luma-ai-ray2.html)、[价格目录服务代码说明](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html)、[固定版本 Ray2 价目表](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrockFoundationModels/20261012084008/us-west-2/index.json)、[Explore AWS 活动](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans-activities.html)。

## 本轮账户只读核查

- 东京 SageMaker：搜索 `ml.g` 得到388项，按 Applied account-level quota 降序查看，最大仍为0；搜索 `ml.p` 同样最大0。涉及不同用途的GPU配额，不能拿CPU默认额度代替。
- 弗吉尼亚 SageMaker：`ml.g` 按同一账户实际配额降序查看，最大仍为0。
- 弗吉尼亚、俄勒冈 EC2 G/VT 按需：0；弗吉尼亚、爱尔兰 G/VT Spot：0。未扫描全球所有项目。
- **俄勒冈 Ray2 并发**：`L-3447D96F`，Applied=**0**、AWS default=1、不可调整。必须区分账户读数与公开默认，不能称已经可生成。
- Ray2 官方模型目录详情和 Playground 可以打开，模型ID `luma.ray-v2:0`。Playground提示需创建S3桶且会产生存储费；**已取消，没有确认创建，也没有运行**。
- 模型访问页提示已退休，模型会在首次调用时自动开通。但尚无证据证明自动开通会把账户Applied=0恢复成默认1；不能把订阅开通当作配额提升证明。
- 官方Bedrock配额文档说明实际配额可能低于默认，配额增加不会自动获批；只读GetFoundationModelAvailability不含quota字段，因此模型权益可用也不能推翻已观察到的0。[配额说明](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas.html)、[可用性API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_GetFoundationModelAvailability.html)。
- Free/Paid计划仍未取得明确字段证明；未升级。余额沿用当日账户估算$49.96，非秒级实时账单。

对应本人登录入口：[东京 SageMaker](https://ap-northeast-1.console.aws.amazon.com/servicequotas/home/services/sagemaker/quotas)、[弗吉尼亚 SageMaker](https://us-east-1.console.aws.amazon.com/servicequotas/home/services/sagemaker/quotas)、[Ray2账户并发](https://us-west-2.console.aws.amazon.com/servicequotas/home/services/bedrock/quotas/L-3447D96F)、[Ray2模型详情](https://us-west-2.console.aws.amazon.com/bedrock/home?region=us-west-2#/model-catalog/serverless/luma.ray-v2:0)。

## 仍值得验证的 AWS 内路线

**Bedrock Ray2**：无需本人EC2 GPU实例；支持首帧图生、5秒/9秒、9:16和S3 MP4。官方540p价$0.75/秒，5秒$3.75；720p价$1.50/秒，5秒$7.50，均未包含S3和税费。只有账户并发/访问有效、赠金覆盖与其余费用明确后才能形成可执行方案。若改用Ray2，必须向用户说明它不是H3，不能静默改模型。[功能](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-luma.html)、[价格](https://aws.amazon.com/bedrock/pricing/)。

**SageMaker Processing/Notebook**：与EC2配额独立，AWS有ComfyUI Processing官方方案及Wan图生视频教程；本次已查区域实际GPU仍为0，尚未形成可启动资源。若其他区域已有可用额度，仍需对应模型、价格、赠金与双停机核查，不能声称已经可用。[Processing官方方案](https://aws.amazon.com/blogs/machine-learning/running-comfyui-workflows-on-amazon-sagemaker-ai-processing-jobs/)、[Wan图生视频官方教程](https://aws.amazon.com/blogs/machine-learning/generate-images-and-video-with-vllm-omni-on-sagemaker-ai-part-2/)。

纯CPU补查曾发现东京 Standard Applied 配额5 vCPU，但**用户已明确否决CPU，要求保留原视频质量**。该分阶段候选不实施；[CPU历史评估](2026-10-25-aws-cpu-video-option.md)仅留档，不再作为当前推荐，不切换模型、不降低分辨率/帧率。Nova Reel 1.0/1.1已EOL，不能作为当前可行方案。

## 状态

本轮仅只读核查；未创建S3/EC2/SageMaker资源、未调用视频推理、未升级计划、未充值或订阅外部平台。**真实视频仍为0；尚未证明一条可以立即执行且零额外自付的路线。** 后续决策必须围绕AWS赠金可用的视频服务，不再把外部付费作为本次解决方案。

用户已明确拒绝联系 AWS 客服。咨询草稿已取消，未发送；不继续申请客服授权，不申请配额，不升级计划。下一步仅评估无需审批、仍能使用现有赠金的技术候选。
