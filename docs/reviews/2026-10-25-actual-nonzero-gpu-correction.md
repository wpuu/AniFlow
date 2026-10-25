# 纠正：现有非零GPU额度与最优候选

> 补充核查：[H3硬件与赠金抵扣边界](2026-10-25-workspaces-h3-fit-credit-assessment.md)。当月账单已读总税费$0.00，但不等于未来永久免税；WorkSpaces实际驱动及完整成片尚未验证。

2026-10-25，Asia/Shanghai。本轮按用户要求查询账户实际Applied值，不再把“目录可选”“可提交提额”混作“当前有额度”。之前范围不完整，未及时发现俄亥俄与WorkSpaces独立额度，导致反复讨论零额度型号，现作实质纠正。

## 已确认不是0的入口

1. **美国俄亥俄EC2，us-east-2：G/VT按需8 vCPU，默认0，利用率显示0，实例列表为空。** 可在额度维度容纳一台g7e.2xlarge（8 vCPU、64 GiB RAM、单卡RTX PRO6000 Blackwell 96GB）。控制台Linux报价$3.36312/h，4h纯计算$13.45248。已在启动向导选择该类型查看，未点击启动、未升级计划，仍不能据此声称库存与全部启动资格已通过。
2. **日本东京WorkSpaces Personal：Graphics.g6.4xlarge Applied=1台、默认0。** 1×L4／24 GiB、16 vCPU／64 GiB RAM。这是独立桌面GPU额度，不受东京EC2 G/VT=0直接限制。另有g6.2xlarge、gr6.4xlarge、g6.16xlarge等多项Applied=1，完整17项中有14项非零；不能把这些额度合成一张更大显卡。当前东京WorkSpaces目录列表为“没有目录”，准确含义是**没有已注册WorkSpaces目录**，并未检查Directory Service是否存在可注册的旧目录。

[全部脱敏账户读数、控制台链接与价格字段](2026-10-25-actual-nonzero-gpu-evidence.json)。[俄亥俄G类配额本人登录入口](https://us-east-2.console.aws.amazon.com/servicequotas/home/services/ec2/quotas/L-DB2E81BA)。[东京WorkSpaces g6.4xlarge配额本人登录入口](https://ap-northeast-1.console.aws.amazon.com/servicequotas/home/services/workspaces/quotas/L-40A36AF9)。

## 如何选择最优路线

**按原H3目标：优先验证东京WorkSpaces Graphics.g6.4xlarge的完整可执行性。** 日本地域保留原许可方向，64 GiB主存对CPU卸载更有余量；但显卡是L4 24 GiB，不能冒充L40S48GB。Comfy官方支持H3量化与低显存卸载，因此它是实际候选，不代表本账户已经证明原质量、时间或内存峰值。它需要Windows版ComfyUI、目录与SSM hybrid接入，原定Linux EC2安装流程不能直接照搬。通过费用与保护门槛并获得路线选择后才实施。

**按GPU容量、费用与现成EC2额度：俄亥俄g7e.2xlarge更有优势。** 单卡96GB、4h计算约$13.45，不需要重新申请提高G额度，且EC2的SSM和停机设计更接近现有Bridge方案。但H3社区许可明确排除美国，不能将大陆用户/大陆输出作为在美国运行模型的地域豁免。因此俄亥俄不能直接部署原H3，需要用户另选允许美国运行的视频模型，例如Apache-2.0的Wan2.2。更换模型并不是已经获得授权，也不保证与H3同效果。

H3条款原文确定排除美国，并限制模型自身使用及复制；将Ohio服务器加载/执行视为美国运行，是条款与技术事实的解释，而不是声称原文逐字列举EC2服务器。[正式H3许可](https://huggingface.co/MiniMaxAI/MiniMax-H3/raw/main/LICENSE)、[Comfy官方低显存说明](https://blog.comfy.org/p/minimax-h3-day-0-support-in-comfyui)、[Wan许可](https://github.com/Wan-Video/Wan2.2/blob/main/LICENSE.txt)。

## 东京WorkSpaces费用窗口：不能只算小时价

统一口径为Windows许可包含、Basic utilities、AutoStop。公开目录发布日期2026-10-16，生效日2026-10-01；各型号默认卷不同：g6.2根150GB/用户100GB，g6.4根200GB/用户150GB，gr6.4根250GB/用户200GB。

按10月25日创建、保守按首月剩余7/31计基础费估算，不是最终账单：

| 候选 | vCPU／RAM；GPU均L4 24GiB | 每小时＋月基础费 | 2h估算 | 3h估算 |
|---|---|---:|---:|---:|
| Graphics.g6.2xlarge | 8／32GiB | $3.25＋$25 | $12.15 | $15.40 |
| **Graphics.g6.4xlarge** | **16／64GiB** | **$4.83＋$30** | **$16.43** | **$21.26** |
| Graphics.gr6.4xlarge | 16／128GiB | $5.40＋$35 | $18.70 | $24.10 |

推荐继续核64GiB的g6.4xlarge、最多约2h实验窗口，保留其他费用余量；32GiB虽能留3h费用窗口，但主存更紧。128GiB的2h已约$18.70，余量过小；扩大CPU/RAM不增加显卡显存。

如需新Managed Microsoft AD，东京Standard公开价为每域控制器$0.073/h、默认两台，即$0.146/h；假设目录总存活4h另约$0.584。g6.4的2h加该目录约$17.02，**仍未计网络、SSM、维护运行及税，不能承诺总费用必低于$20或零自付**。Simple AD不能直接假设新账户可开：2026-07-30后首次开通受限。网络方案不得默认增加NAT Gateway；权重下载路径、数据处理费和关联资源清理需单独核算。

来源：[东京WorkSpaces公开目录](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonWorkSpaces/current/ap-northeast-1/index.json)、[计费说明](https://aws.amazon.com/workspaces/desktop-as-a-service/pricing/)、[东京Directory Service公开目录](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSDirectoryService/current/ap-northeast-1/index.json)、[Simple AD变更](https://docs.aws.amazon.com/workspaces/latest/adminguide/launch-workspace-simple-ad.html)。

五笔赠金适用清单均包含EC2、WorkSpaces、Directory Service、Systems Manager、VPC；这是产品匹配证据，不取代Free/Paid、税费、实际SKU与关联费用核查。WorkSpaces停止后仍有月基础费，实验后必须按批准的清理方案释放，不能留到赠金过期后继续收费。

## 账户范围完整性

账户区域设置实际显示17个默认启用区域，加香港、台北、海得拉巴3个已启用区域，共20。其余14个为禁用，未擅自启用。对20处逐一读取G/VT和P的按需及Spot实际值，共80个GPU额度值；本轮非零仅有俄亥俄G/VT按需8。

| 区域 | G按需vCPU | P按需vCPU | G Spot vCPU | P Spot vCPU |
|---|---:|---:|---:|---:|
| us-east-1 | 0 | 0 | 0 | 0 |
| us-east-2 | 8 | 0 | 0 | 0 |
| us-west-1 | 0 | 0 | 0 | 0 |
| us-west-2 | 0 | 0 | 0 | 0 |
| ap-east-1 | 0 | 0 | 0 | 0 |
| ap-east-2 | 0 | 0 | 0 | 0 |
| ap-south-1 | 0 | 0 | 0 | 0 |
| ap-south-2 | 0 | 0 | 0 | 0 |
| ap-northeast-1 | 0 | 0 | 0 | 0 |
| ap-northeast-2 | 0 | 0 | 0 | 0 |
| ap-northeast-3 | 0 | 0 | 0 | 0 |
| ap-southeast-1 | 0 | 0 | 0 | 0 |
| ap-southeast-2 | 0 | 0 | 0 | 0 |
| ca-central-1 | 0 | 0 | 0 | 0 |
| eu-central-1 | 0 | 0 | 0 | 0 |
| eu-west-1 | 0 | 0 | 0 | 0 |
| eu-west-2 | 0 | 0 | 0 | 0 |
| eu-west-3 | 0 | 0 | 0 | 0 |
| eu-north-1 | 0 | 0 | 0 | 0 |
| sa-east-1 | 0 | 0 | 0 | 0 |

这份EC2结论不能扩大成“整个AWS没有GPU”：东京WorkSpaces已实际发现非零。东京AppStream的G6/G6e过滤并按Applied降序查看，最高仍0；旧Graphics Design/Pro的退役默认值不能充当现成GPU入口。本轮没有扫描每个区域的所有独立托管服务。

## 创建前仍未完成

- Free/Paid计划未取得明确字段证明；未升级。GPU可以在未提交EC2向导中被选择，但这不保证启动API、库存、计费及计划检查通过。
- WorkSpaces未注册目录；旧目录可注册资格、新目录权限、Windows公开bundle和初始化入口待确认。
- H3在Windows＋L4下的加载、质量、耗时未测；Ohio若换Wan也未测，不能把配额和显存当视频成功。
- 原Bridge没有接通任何真实GPU。WorkSpaces须通过SSM hybrid注册，不能假设原EC2实例角色和Linux安装脚本直接可用。[官方SSM集成](https://aws.amazon.com/blogs/desktop-and-application-streaming/automating-aws-systems-manager-activation-for-amazon-workspaces/)。
- 云端绝对时限定时停止、独立备用停止及实验后清理均未部署；AutoStop闲置停止不等于4小时硬停止。未通过前不创建。[StopWorkspaces API](https://docs.aws.amazon.com/workspaces/latest/api/API_StopWorkspaces.html)。

## 本轮实际完成

完成20个已启用区域EC2核查、东京WorkSpaces非零GPU核查、Ohio价格/空实例列表/未提交类型选择、东京WorkSpaces费用及已注册目录检查。新建资源0、提额申请0、对外客服消息0、模型调用0、真实视频0；未修改前端、Bridge或模型工作流，CPU视频方案继续保持用户已否决。下一步优先做东京WorkSpaces的完整可执行预检；若用户选择更换模型，再推进Ohio GPU方案，不暗改路线。
