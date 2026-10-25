# AWS 东京 H3 账户只读核查

核查日期：2026-10-25，Asia/Shanghai。基线：PR #7，`b65a9f64`。账户及 Credits 均通过用户授权的 Ego 浏览器读取；未使用 AWS CLI/SDK、未导出凭证。

**结论：停止云端创建，继续本地开发。东京 G/VT 按需配额为 0 vCPU，目标实例需要 8 vCPU。** 用户随后明确不走申请配额路线，要求先给详细替代方案供其决定。曾查看申请历史并在表单填入 8，未提交；表单已取消。不得将该准备动作写成已申请。

## 已读取的账户证据

| 项目 | 实际读数与边界 |
|---|---|
| 赠金余额 | 月度结算口径剩余 $91.14；预计剩余 **$49.96**，预计已用 $50.04。页面明确估算约每 24 小时更新，不能称秒级实时余额。 |
| 赠金到期 | 5 笔 Active 积分均显示 **2026/10/30**；页面没有给时刻或时区。不得猜成中国时间或 UTC 午夜。 |
| 逐笔适用产品 | 五笔全部打开完整服务列表，均含 Amazon Elastic Compute Cloud、Amazon Virtual Private Cloud、AWS Systems Manager、AWS Data Transfer、CloudWatch Events、AmazonCloudWatch；活动名称包含 EC2/Bedrock/Budgets/Lambda/RDS，不等于只能用于该活动同名服务。 |
| Free/Paid | 检查 Free Tier、账单首页、账户、入门页面；未见明确 Free/Paid Plan 字段。**保持未知**，不能把 Free Tier 产品列表或 Support Plan 当付款计划证明。 |
| 东京配额 | `Running On-Demand G and VT instances`，`L-DB2E81BA`，应用账户配额 **0**，利用率 0；申请历史显示 0 个请求。 |
| 价格 | 东京控制台按需 Linux **$3.25168/小时**；4 小时仅计算 **$13.00672**。系统为 Ubuntu 的具体 AMI 必须核实是否带 Pro/Marketplace 软件费用；不能据另一系统价格直接启动。 |
| 型号与区 | g6e.2xlarge：8 vCPU、64 GiB RAM、1×NVIDIA L40S，控制台显存显示 44.7 GiB（约 48 GB 十进制），列出 1a/1c。**列出的可用区不是实时库存证明**。 |
| SSM | 可进入 Session Manager 与目标选择向导；没有与所需 IAM 角色关联的实例。未启动会话；未证明实例角色、StartSession、端口转发或本机凭证会话可用。 |
| H3 地域 | 用户明确：本人及本次视频仅在中国大陆使用/展示。中国大陆不在社区许可排除地域；本次地域检查通过。其他许可条款仍需遵守。 |
| 停机保护 | 未部署、未测试；不允许据方案或预算告警声称已落实。 |

账户源页面：[Credits](https://us-east-1.console.aws.amazon.com/costmanagement/home#/credits)、[东京 G/VT 配额](https://ap-northeast-1.console.aws.amazon.com/servicequotas/home/services/ec2/quotas/L-DB2E81BA)、[实例规格及价格](https://ap-northeast-1.console.aws.amazon.com/ec2/home?region=ap-northeast-1#InstanceTypeDetails:instanceType=g6e.2xlarge)、[Session Manager](https://ap-northeast-1.console.aws.amazon.com/systems-manager/session-manager?region=ap-northeast-1)。这些页面需本人登录。脱敏事实另存同目录 JSON；不提交完整账户 ID、赠金 ID、Cookie、密钥或账单联系人。

## 配额申请方案（用户已否决，未提交）

先查现有申请，已确认无记录。拟申请东京 EC2 的 `Running On-Demand G and VT instances` **总配额 8 vCPU**，不填成 8 台实例，也不申请无关 Standard/P 系列配额。

若 Support 要用途说明：单台 g6e.2xlarge、H3 图生视频研究验证、首次最长 4 小时、首轮预算 $20、赠金抵扣、预先落实主定时停止与独立备用停机，完成后停止并处理残留存储。当前表单只有数值栏，没有预先虚构“已提交用途说明”。

AWS 可批准、部分批准或拒绝，时限不能保证。批准后仍需回查 applied quota ≥ 8、真实库存、赠金/税费、账户计划、SSM 与双停机措施，才能启动。若要求 Free→Paid，停止并交用户决定。10 月 30 日前未通过就不为消耗赠金绕过门槛。

官方依据：[申请区域配额](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html)、[审批状态与限制](https://docs.aws.amazon.com/servicequotas/latest/userguide/request-quota-increase.html)、[G/VT 默认 0 且可调整](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-on-demand-instances.html)。

## 费用与停止保护设计边界

公开官方东京价源：gp3 $0.096/GB-month，200 GB 在 10 月保留 4 小时约 $0.1032；单个公共 IPv4 $0.005/小时，4 小时 $0.02。这些与 4 小时计算合计约 $13.13，**不是含税、流量及所有关联资源的最终报价或硬上限**。EBS 停机后仍继续计费；磁盘删除前不能声称完全停止费用。

EC2 Session Manager/Run Command 本身无额外费用；日志、PrivateLink、NAT 等依赖另算。Scheduler 前 1400 万次/月有免费额度，东京超额价 $1.25/百万次；需核账户已有用量。税费不能笼统算作赠金覆盖。

未来主停机应由云端独立 Scheduler 以最小执行角色调用 StopInstances，备用为实例内持久化 systemd 硬截止关机；二者不能依赖用户 Windows、Bridge、浏览器或当前聊天保持在线。启动前还须验证 systemd 关机行为确实停止 EC2、计时从实例启动而非开始推理计算，且主/备截止都不超 4 小时。这里只记录设计，未创建或测试资源。

官方价格与规则：[EBS 价源](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ebs.json)、[EBS 计费](https://aws.amazon.com/ebs/pricing/)、[IPv4](https://aws.amazon.com/vpc/pricing/)、[SSM](https://aws.amazon.com/systems-manager/pricing/)、[Scheduler](https://aws.amazon.com/eventbridge/pricing/)、[东京 Events 价目表](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSEvents/current/index.json)、[Scheduler 通用目标](https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets-universal.html)、[促销金税费和到期条款](https://aws.amazon.com/awscredits/)。

## 官方 H3 源与未完成验收

[社区 LICENSE](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) 排除美国、欧盟、英国、韩国，并覆盖输出的使用和展示；商业产品/服务年收入超过 $20M 需另行书面授权。不得把东京服务器作为绕过实际使用地域限制的办法。[Comfy 官方许可说明](https://comfy.org/minimax/license)。

官方 ComfyUI [v0.42.1](https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.42.1)，官方 [I2V 模板](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_i2v.json)，[模型卡](https://huggingface.co/Comfy-Org/MiniMax-H3)，核查 revision `e5eb578a89295337b8ff433a035929ce0279e0b6`。INT8 主模型、NVFP4 文本编码器、视频/音频 VAE 合计约 40.07 GB，含 Turbo LoRA 约 42.03 GB。文件体积不等于峰值显存；L40S 目标竖屏推理可行性仍未实测。

未下载权重、未部署云端 ComfyUI、未真实推理；5 秒视频、显存峰值、推理耗时、真实账单均**未取得**。本地适配器和离线契约测试仅验证工程路径，不能作为 H3 真实视频证据。
