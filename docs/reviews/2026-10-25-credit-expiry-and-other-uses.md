# 现有AWS赠金的其他用途及延期边界

2026-10-25，Asia/Shanghai。用户询问赠金还能做什么、能否延长有效期。本轮仅查官方规则和已保存的五笔完整适用服务清单；未联系AWS客服、未申请提额、未升级计划、未调用收费服务。

## 延期结论

目前没有已核实可由用户自行延长这五笔赠金有效期的机制，应按控制台显示2026-10-30到期安排，不能承诺延期成功。账户计划Free/Paid仍未明确；不能拿通用Free Tier的6个月或12个月说明覆盖这五笔实际到期日，也不能把升级计划说成重置赠金有效期。

官方规则将赠金的生效、到期与账户计划区分开。AWS条款第9项另写明：已经兑换的赠金可抵扣到期所在整个账单周期的合格费用。这是账单抵扣规则，不等于余额延期或滚存至未来账期；不能仅凭它保证本账户10月30日后仍可调用或免自付，不改变原有提前停止策略。

来源：[赠金条款第1、3、7、9项](https://aws.amazon.com/awscredits/)、[赠金状态与抵扣说明](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/useconsolidatedbilling-credits.html)、[账户计划规则](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html)。

赠金不是可提现/退款或转卖的现金余额。不能通过暂停资源、换区域、购买新实例延长其有效期；预付费用（例如Savings Plans/Reserved Instances首付款）以及域名注册/转入通常不适用，不能以此预存未来一年使用费。存入S3的素材在到期后继续保存仍会产生存储费用，不能当作免费长期储存方案。

## 与内容生产有关的其他用途

逐笔复核五份已保存完整列表，下列产品在五笔中均出现：Amazon Bedrock、AmazonBedrockFoundationModels、Amazon Polly、Amazon Transcribe、Amazon Translate、Amazon Textract、AWS Elemental MediaConvert、Amazon Simple Storage Service。

清单适用只说明产品匹配，不证明本账户已有模型/任务调用权限或非零配额；具体型号、区域、关联费用和许可仍需在调用前核查。这些托管服务不使用本账户EC2 G/VT额度，但有各自额度。

1. **AI图片素材**：Bedrock托管图像模型可作为角色概念图、分镜、封面和视频首帧素材候选，无需创建本人EC2 GPU。当前官方Stable Image Ultra 1.0模型卡显示Active、俄勒冈可用；本账户图像模型权限/配额未查，不能宣称已能生成，也不把图片当视频成功。[模型卡](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-stability-ai-stable-image-ultra-1-0.html)。
2. **配音文件**：Polly将脚本合成为语音，下载本地供视频制作使用；具体中文音色、质量及账户资格待核查。官方允许缓存和重播已生成语音而无需再次支付合成费用。[Polly说明](https://docs.aws.amazon.com/polly/latest/dg/what-is.html)。
3. **字幕和素材整理**：Transcribe将已有音视频转为文字，Translate翻译脚本/字幕，Textract提取文档文字。可下载文本作为后续制作资产；语言、排版和识别错误需校对。[Transcribe说明](https://docs.aws.amazon.com/transcribe/latest/dg/what-is.html)、[Translate说明](https://docs.aws.amazon.com/translate/latest/dg/what-is.html)、[Textract说明](https://docs.aws.amazon.com/textract/latest/dg/what-is.html)。
4. **已有视频后期**：MediaConvert用于已有文件的转码、字幕和图层处理；它不是图生视频模型，不需要本人的G类GPU实例，但任务额度、IAM角色、S3和价格未核查。[MediaConvert说明](https://docs.aws.amazon.com/mediaconvert/latest/ug/what-is.html)。
5. **文本策划和资料处理**：Bedrock文本模型辅助脚本、分镜、标题、提示词及资料整理。调用权限与模型额度待核查；不是另充值外部AI服务，也不是视频成片方案。

## 建议与实际状态

若接受把部分赠金用于内容资产，优先考虑能在到期前生成并下载到Windows的图片、配音、字幕、脚本；这些已交付文件可在相应使用条款下继续用于后续制作，不依赖到期后持续开机。若只接受原质量真实图生视频，当前GPU/Ray2资格阻塞仍未解决，不能把上述用途冒充替代成片成功。

不建议为消耗赠金空跑CPU、长期保留S3或购买不适用的预付项目。本次新增云资源0、收费调用0、真实视频0，CPU视频方案继续保持用户已否决。下一步若选定某项用途，应先只读核查该服务的实际资格和预算，再决定是否执行；本分析不授权开通或调用。
