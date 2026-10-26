# 东京WorkSpaces配额对账与AWS真实视频候选｜2026-10-26

**首选候选改为东京GameLift Streams gen6n_pro＋原H3：已读到独立Gen6n GPU额度1，旧5笔赠金清单均包含该服务，不需先换模型或降低目标画质。但尚未创建容量、未做GPU/CUDA预检，且会话/断网语义与原主机不同，需用户决定。东京WorkSpaces“显示1、创建判0”的根因仍未知；此前将Applied=1当作可创建依据不充分。**

用户约束保持：利用现有AWS赠金，抵扣后自付≤USD1，初次服务费目标约USD20，GPU最长4小时；不提额、不升级计划、不找AWS客服、不转外部自费平台、不擅自降低画质。更换H3模型须用户明确同意。赠金10月30日到期的精确时刻/时区未在本记录重新核实。

## 1. 真实账户证据与创建请求已对齐

以下账户事实由主负责人通过授权浏览器实读；本记录代理只读了脱敏CloudTrail白名单文件，没有访问账户。

| 检查项 | 实际结果 |
|---|---|
| 同账户比对 | same=true；不保存/输出账户ID |
| 东京精确配额 | L-40A36AF9，Graphics.g6.4xlarge WorkSpaces：Applied=1、AWS default=0、usage=0 |
| 东京总WorkSpaces | Applied=1、default=1、usage=0 |
| 公共bundle | wsb-9zg6r5j55；主负责人再次读回Graphics.g6.4xlarge、Windows Server 2022、16vCPU、64GiB RAM、24GiB名义显存 |
| 实际调用 | 2026-10-26T04:07:58Z；CreateWorkspaces；workspaces.amazonaws.com；ap-northeast-1 |
| 请求数量及配置 | 1项；同bundle；AUTO_STOP，断开后120分钟；root200GiB/user150GiB；原ExperimentId标签 |
| 错误 | ResourceLimitExceededException，错误正文明确允许Graphics.g6.4xlarge数量为0 |
| CloudTrail eventID | e4c2d63e-9e7a-466b-9033-f4398bcb38bd |

本地白名单证据：`work/aws-quota-reconciliation-20261026/cloudtrail-create-whitelisted.json`。结构化伴随JSON记录其SHA256和requestID，没有复制登录身份、目录用户、账户ID或token。官方说明WorkSpaces的创建操作会记录于CloudTrail，事件可还原请求和错误：[WorkSpaces CloudTrail文档](https://docs.aws.amazon.com/workspaces/latest/adminguide/cloudtrail_logging.html)。

## 2. 可确定和不能确定的原因

官方定义G6.4xlarge额度为本账户当前区域该类型WorkSpaces最大数量；它不是EC2 vCPU数。总WorkSpaces额度另列。旧“Graphics WorkSpaces”项注明退休旧Graphics bundle，不能据此构造所有G6共享的父配额。[官方配额表](https://docs.aws.amazon.com/workspaces/latest/adminguide/workspaces-limits.html)

本次已用相同账户、东京区域、准确quota名称/代码、实际公共bundle和单项请求完成交叉核验，因此错账户、错区域、错机型及一次请求多台均已排除。仍不能断言Free Plan、底层EC2 G/VT父限、额外Graphics父限或同步bug导致报错；这些目前都是没有账户/服务端定因证据的假设。账户计划通用限制条款本身也不能解释这条具体请求。[账户计划说明](https://docs.aws.amazon.com/us_en/awsaccountbilling/latest/aboutv2/free-tier-plans.html)

后续若只读证据仍然一致，应记录为Service Quotas显示与创建端执行结果矛盾。不能反复重建目录/桌面当成无成本诊断，也不能用“等一会必然恢复”作承诺。已有一次真实拒绝，没有GPU创建成功证据。

## 3. 已读配额边界

- 东京SageMaker：ml.g6e.2xlarge、ml.g6.4xlarge、ml.g5.4xlarge已检查的所有用途Applied=0。
- 东京AppStream image builder：G6e L-C9C1E1C3=0，G6 L-4EFC345A=0。
- 今日Ohio EC2按需G/VT：Applied=8vCPU、default=0。此数值不代表任何具体实例有库存，也不代表已经创建。
- 东京GameLift Streams：独立Gen6n GPUs（L-9F99CEA2）Applied=1/default=0；Gen6e（L-BD8BFCD5）Applied=0/default=0。额度不等于实际供给或已创建容量。
- 东京Deadline Cloud按需G（L-5D6BA491）Applied=0。Lightsail Instances（L-4259AF9B）Applied=4/default=20，但描述单位是vCPU；Research GPU资格未确认，不能当成4个GPU名额。
- 已完成10个已启用且按H3地域筛选合规区域的SageMaker ml.g/ml.p筛选，分别按Applied降序，观察到最高值均为0：东京、大阪、新加坡、悉尼、香港、台北、孟买、海得拉巴、加拿大中部、圣保罗。只记录本范围和最高值，不使用可能陈旧的aria filtered_count，不泛称全球所有区域均0。证据：`work/aws-quota-reconciliation-20261026/sagemaker-regional-readback.json`，SHA256及观察时间见伴随JSON。

## 4. 首选候选：东京GameLift Streams＋原H3

本轮新的脱敏配额快照见[Gen6n账户实读](2026-10-26-gamelift-gen6n-quota.json)：2026-10-26T05:43:10Z再次读到Applied=1、default=0、usage=0。它不是容量分配成功证据。

主负责人通过授权Ego实读东京GameLift Streams Gen6n GPU额度1；这是独立服务的名额，不用推断或借用EC2/WorkSpaces额度。旧5笔赠金服务清单 `work/aws-audit-20261025/credit-services-0.txt` 至 `credit-services-4.txt` 均有Amazon GameLift Streams，本记录已逐份核对文字；这是2026-10-25的资格证据，不代替创建前刷新余额、到期和附加项目抵扣。

官方gen6n_pro为单会话全L4、24GB显存、64GB RAM、16vCPU，可用Ubuntu22.04 LTS；官方当前驱动Linux/Proton580.95.05，Windows581.42。这里是官方配置与驱动表，不是实机nvidia-smi结果。保留原H3四权重pruned_int8_convrot、默认attention、20步；目标仍为800×1376/124真实帧/24fps，最终仅裁边到774×1376并取前120帧，形成9:16、短边774、5秒，不插帧或放大生成视频。[官方配置](https://docs.aws.amazon.com/gameliftstreams/latest/developerguide/configuration-options.html)

建议将首次分配后的前10分钟限定为真实GPU、显存、驱动、CUDA13、用户态依赖和安全结果通路预检；失败即主动停止并释放/删除容量，不继续加载H3或提交视频。L4/64GB尚无本工作负载实测，不能承诺在两小时窗口完成。Linux应用需要重新打包；Windows Portable准备文件不能直接宣称适用于此Ubuntu运行时。

**连接和恢复差异须用户选择：** CreateStreamSessionAdminShell通过Session Manager plugin提供应用同级权限的shell，不能当成通用SSM端口转发或root主机。会话仍需WebRTC客户端连接；断线重连等待最多3600秒（默认120秒），CONNECTED无用户输入60分钟会终止。Linux会话结束后应用进程被杀、文件系统修改丢弃，因此不能承诺原主机方案的4小时断网继续生成。admin shell自身最长30分钟、空闲15分钟，需重新连接，不能把shell存活当作WebRTC已连。必须如实处理未知提交结果与已知prompt_id，不能超时重连后自动再提交。[Admin shell](https://docs.aws.amazon.com/gameliftstreams/latest/developerguide/troubleshoot-admin-shell-guide.html)、[会话API](https://docs.aws.amazon.com/gameliftstreams/latest/apireference/API_StartStreamSession.html)、[进程/文件清理](https://docs.aws.amazon.com/gameliftstreams/latest/developerguide/infrastructure-security-tenancy.html)

结果拟由应用临时IAM角色只写本次私有S3前缀，再由本机Bridge下载、恢复并核MP4和SHA256；不公开Comfy端口、不导出AWS凭证。该服务需要新的Bridge适配器，**本轮未改实现、未验证私有传输**；原WorkSpaces/通用SSM桥不能冒充已直接兼容。

**保护仅为建议，尚未部署：** 先显式创建AlwaysOnCapacity=0、MaximumCapacity=0、TargetIdleCapacity=0的组，避免省略容量参数时默认分配；在任何正容量前落实并验证主、备用独立执行。建议固定T0后主90分钟：Terminate会话，再将三个容量值全置0，轮询实际AllocatedCapacity归零；备用95分钟：独立DeleteStreamGroup并确认GetStreamGroup返回NotFound。四小时仍是用户绝对授权上限，不能随进度延长。

官方允许任意状态的stream group进入删除，删除会主动结束流并释放计算资源，但过程异步，仍须处理API冲突/重试并验收不存在。仅将capacity目标改0可能等待活动会话结束；仅Terminate会话则容量可能保持、继续计费。**会话终止不等于停止计费；HTTP204或DELETING不等于完成释放。** 旧WorkSpaces Stop保护不能直接拿来保证此服务。应用内容与私有S3如仍保留，存储等费用仍可能继续；计算资源释放不能表述为全部账单归零，取回视频后须另核最小保留及清理。[组管理及缩容/删除](https://docs.aws.amazon.com/gameliftstreams/latest/developerguide/stream-groups.html)、[删除API](https://docs.aws.amazon.com/gameliftstreams/latest/apireference/API_DeleteStreamGroup.html)、[容量字段](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-gameliftstreams-streamgroup-locationconfiguration.html)

官方公开价格数据中，东京Linux gen6n_pro为USD2.3028/分配小时；按GPU容量占用2小时估算USD4.6056，另加内容存储、私有S3/请求、网络及可能的辅助保护用量，仍以总服务费约USD20、抵扣后自付≤USD1约束。官方按已分配容量逐秒收费，idle仍收费，实际计费结束以释放为准；此处不是账单，也不保证异步释放恰好两小时完成。[官方计费语义](https://aws.amazon.com/gamelift/streams/pricing/)、[官方价格数据](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/gameliftstreams/USD/current/gameliftstreams.json)

东京可直接作为primary region，源S3、application和stream group均放东京，只启用东京location；不需要美国primary。创建前须读取实际LocationStates/ReplicationStatuses，避免把权重分发到H3排除地域。50GiB单份应用按730小时/月、每GB月USD0.0322估算，2小时存储约USD0.005；源S3和其他费用另计，不假定免费试用。[东京primary端点](https://docs.aws.amazon.com/general/latest/gr/gameliftstreams.html)、[同区域及复制规则](https://docs.aws.amazon.com/gameliftstreams/latest/developerguide/stream-groups.html)

GameLift Streams没有AWS Free Tier免费额度，这与“本笔赠金适用服务包含GameLift Streams”是两回事。账户Free/Paid计划尚无明确实读状态；不得将赠金资格或Applied1替代计划/创建资格。若服务要求升级或无法满足净自付上限，停止创建，不改账户计划。

## 5. 其他候选与不可直接采用的路径

| 路径 | 当前判断 | 事实与待验证项 |
|---|---|---|
| 东京GameLift gen6n_pro + 原H3 | 首选候选，待用户接受会话差异与真实预检 | 独立Gen6n额度1、旧5笔赠金列表含该服务；尚未分配GPU、未推理、未部署新保护 |
| 东京WorkSpaces + H3 | 创建阻塞 | 精确机型仍被实际0额度错误拒绝；根因未知，不能宣称可创建 |
| Ohio g7e.2xlarge + Wan2.2-I2V-A14B | 降为备选，仍待用户明确同意换模型 | Ohio已有8vCPU额度；该机型公开规格为8vCPU/64GiB系统RAM/96GB GPU。原生864×1536、5秒、24fps是候选目标，未实测，不能承诺主观画质等于H3或窗口内成功 |
| Ohio + H3 | 许可适用未澄清 | 美国被排除，使用/复制受领土限制；没有按服务器物理位置判定的专门条款，不能编造“服务器所在地禁令”，也不能仅凭操作者和输出在大陆就标许可通过 |
| Bedrock Ray2 | 不符合保持分辨率要求 | 官方API最高720p，低于短边≥768目标；不能用放大替代原生要求。Marketplace计费背景不等于可机械认定赠金不适用，具体产品映射仍须账户证据 |
| Bedrock Nova Reel | 已EOL | v1:0/v1:1官方EOL为2026-09-30，已过期移除；不能照旧教程调用 |
| Marketplace MiniMax H3 SaaS | 预算不符 | 公开最低预付合约USD10,000，且listing标注Deployed on AWS=No；不符合USD20实验。常规赠金对Marketplace有排除并保留AWS明确授权例外，本次未证实此SaaS特批 |

G7e规格见[AWS官方机型页](https://aws.amazon.com/ec2/instance-types/g7e/)。[Wan官方仓库](https://github.com/Wan-Video/Wan2.2)与[官方I2V-A14B模型页](https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B)标注Apache-2.0；单GPU示例需至少80GB显存，示例针对720p面积，并非864×1536/5秒基准。96GB显存规格不能替代该目标下的峰值、64GiB系统RAM、帧网格/FPS与耗时实测。原生目标不可悄悄改成720p再放大。此候选需用户明确接受换模型，再核Ohio具体机型供给、最新Linux价格/附加费用、赠金抵扣及双独立停机保护，才可能进入创建评估。

H3许可依据固定官方修订的I.3/I.5/I.6、II、V.4和附件A.1：[官方LICENSE](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/42ed227ee7df40d41602854ae760620d6eb651fe/LICENSE)。将权重存入/加载于美国服务器涉及美国境内复制与运算，是有文字依据的解释，但不是条文直接规定服务器判准；现状态为未澄清，不能作无依据法律保证。

Ray2见[官方参数](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-luma.html)；Reel见[官方EOL表](https://docs.aws.amazon.com/en_en/bedrock/latest/userguide/model-lifecycle-legacy.html)；H3 SaaS见[官方Marketplace报价](https://aws.amazon.com/marketplace/pp/prodview-wi37h23rw6ed6)；通用赠金例外与限制见[AWS赠金条款](https://aws.amazon.com/tw/awscredits/)。不拿Activate专项权益替代本人Explore AWS赠金资格。

## 6. 实际完成、未知与下一步

已完成配额详情、CloudTrail创建请求及真实bundle三方对账，并保留脱敏事实；已更正“Applied1即可创建”的判断。未查明为什么创建端判定0，未生成真实视频。已有静态H3工作流不能作为模型成功证据。

本次对账与公开方案研究未新增收费资源、未调用生成、未提额、未升级、未联系客服，也未下载模型；这不等于历史目录/保护资源必然没有费用或已清理，历史清理和账单须另按实际记录。

下一步由用户决定是否接受东京GameLift Streams保持原H3/画质、但需受限会话连接和新Bridge适配器的方案；同意后先完成打包、私有结果适配及零容量下的独立停止保护，再进入10分钟真实预检。Ohio+Wan仅保留为需另行同意换模型的备选。本轮用户只要求查清和给方案，没有创建GameLift资源、部署新保护或调用生成；不能把候选写成已获准启动或承诺10月30日前成功。
