# 东京WorkSpaces能否跑H3、赠金能否全抵

> 预算已澄清：用户允许消耗赠金，自付最多USD1。此前“总服务费USD1不可创建”仅为澄清前记录，不再作为当前费用否决。最新执行状态与剩余门槛见[10月26日WorkSpaces进度](2026-10-26-workspaces-progress.md)。

> 最新税务核查：已读到税务设置地址国家CN、卖家AWS Inc.及当期税费$0；预计不因选择东京而自动加日本10%税，无需修改税务资料。详见[税务所在地与处理建议](2026-10-25-aws-tax-jurisdiction-assessment.md)，不作永久免税保证。

2026-10-25，Asia/Shanghai。用户询问Graphics.g6.4xlarge是否够运行H3，以及赠金能否完全抵扣。本轮只读检查当月账单/税务页，核对官方模型要求与已有五笔服务清单；未创建资源或调用模型。

## 硬件判断

该型号实际配额1，硬件为L4 24 GiB显存、16 vCPU、64 GiB主存。具备官方量化加动态显存卸载的试验依据；尚不能把它判为已验证稳定运行或保证2小时内成片。

保留原官方pruned_int8_convrot（约21GB）和默认attention，不擅自换成更低精度w6a8、缩小画面或减少采样步数。权重体积不等于峰值显存：还需文本编码器、视频/音频VAE及工作张量。因此不能将“21GB文件小于24GB显存”当成全载显存已足够，必须借助主存卸载。官方称H3可在RTX3060级GPU动态卸载运行，但未找到该Windows WorkSpaces/L4/64GiB组合的精确显存、速度基准或硬性最低RAM说明。

Windows兼容仍是实质门槛：当前Comfy NVIDIA Portable与预编译CUDA内核路径要求合适的NVIDIA驱动；相关当前CUDA13包要求r580+，实际WorkSpaces镜像驱动未读取。需核对实际安装版本，不能在未确认驱动时宣称可直接跑。Comfy Kitchen **attention backend**不支持int8_convrot，保留默认attention；不能误说整个量化库不支持INT8。

这里是自部署开放权重，不是调用按条计费的MiniMax视频API；不会因本地推理自动产生H3 API费。许可仍按正式社区协议和既定地域核查，不暗中购买商业授权或其他软件。

来源：[AWS规格](https://docs.aws.amazon.com/workspaces/latest/adminguide/bundle-options.html)、[Comfy当前H3教程](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)、[官方低显存说明](https://blog.comfy.org/p/minimax-h3-day-0-support-in-comfyui)、[Windows系统要求](https://docs.comfy.org/installation/system_requirements)、[官方CUDA内核库](https://github.com/Comfy-Org/comfy-kitchen)。

## 赠金抵扣判断

五笔完整适用服务清单均逐字包含WorkSpaces、Directory Service、Systems Manager、VPC、Data Transfer、CloudWatch、Lambda、CloudWatch Events和S3。这支持按合格产品使用赠金抵扣相关AWS服务费用；本方案不依赖外部平台充值。**尚未产生该WorkSpaces账单，因此不能说该实例实际抵扣已经验证，更不能保证全部费用100%零现金。**

本轮通过本人Ego账单页读取：2026年10月当前“总计税费”为USD0.00。记录只保存税费金额，不公开账户编号、地址或税号。该值是本期已发生费用的状态，不是未来WorkSpaces税率或永久免税证明。AWS赠金条款明确不抵交易税；如新费用产生税费，不能自动假定赠金会覆盖。[AWS赠金条款第7项](https://aws.amazon.com/awscredits/)。

[脱敏核查证据](2026-10-25-workspaces-h3-fit-credit-evidence.json)。

## 预算含义

已核东京Windows许可包含、AutoStop、Basic utilities为$4.83/h＋$30/月基础费。按10月25日创建、首月剩余7/31估算，2小时约$16.43；若新Managed Microsoft AD目录总存活4小时，另约$0.584，合计约$17.02。未包含网络、SSM、日志、维护运行及可能税费。报价的默认根卷200GB、用户卷150GB已在该口径内；不能误把它当纯小时价。

因此“2小时受控首验有预算窗口”不等于“$20全包”“2小时一定出片”或“剩余赠金可永久包费用”。安装、权重下载、驱动检查也消耗该窗口。网络出口需明确，不默认创建NAT Gateway；不购买Marketplace预装软件、Office Plus或额外商业许可。停止WorkSpace仍会有月基础费，试验后须按预先批准的清理方案释放，不能留到赠金过期后继续收费。

## 下一步与当前状态

下一步是把实际镜像驱动、目录资格、网络收费路径、账户计划、完整预算以及两套独立停止/清理保护核清；在这些条件通过前不创建。若驱动不兼容或完整费用不能控制在获准范围内，应停止该路线，而不是未经同意付现或降低目标质量。

本次创建0、模型调用0、真实MP4为0；不修改前端、Bridge或模型工作流。准确结论是：**H3有量化卸载试验依据；已确认主要AWS服务的赠金适用产品匹配，当前账单税为0；稳定成片与全额零自付尚未证实。**
