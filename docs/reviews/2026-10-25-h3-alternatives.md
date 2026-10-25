# H3 配额阻塞后的替代方案

> **已纠正：本文外部付费路线的优先推荐不符合用户“仅利用AWS赠金生成视频”的核心目标，现撤回；Ray2赠金判断也不能仅凭Marketplace一般条款下结论。请以 [最新AWS赠金核查](2026-10-25-aws-credit-video-correction.md) 为准。下文保留为历史方案记录，不作为当前执行建议。**

日期：2026-10-25，Asia/Shanghai。用户要求先详细分析供其决定，**不申请配额、不购买或切换云服务、不调用新付费 API**。

## 结论

换东京 g6e.xlarge / g6 / g5 / g4dn 不能解除同一个 G/VT 配额为 0 的限制。若首要目标是“真实 H3 图生视频 → AniFlow → Windows MP4”，建议 MiniMax 官方按量 API；若目标仍包含“官方 ComfyUI、量化权重、显存峰值实测”，才考虑另租合法地域 48/80GB GPU。

AWS 赠金使用与 H3 跑通应分别决策，不能为赶到期时间把不合格资源、其他模型或 Marketplace 费用当成原方案已完成。

## 已查账户范围

Ego 控制台实读：东京 G/VT On-Demand=0、G/VT Spot=0、P On-Demand=0；新加坡 G/VT On-Demand=0、Spot=0；悉尼 G/VT On-Demand=0、Spot=0。只代表这些项目，**没有扫描全球所有区域或 SageMaker 配额**。

证据入口（本人登录）：[东京 G/VT](https://ap-northeast-1.console.aws.amazon.com/servicequotas/home/services/ec2/quotas/L-DB2E81BA)、[东京 Spot](https://ap-northeast-1.console.aws.amazon.com/servicequotas/home/services/ec2/quotas/L-3819A6DF)、[东京 P](https://ap-northeast-1.console.aws.amazon.com/servicequotas/home/services/ec2/quotas/L-417A185B)、[新加坡](https://ap-southeast-1.console.aws.amazon.com/servicequotas/home/services/ec2/quotas/L-DB2E81BA)、[悉尼](https://ap-southeast-2.console.aws.amazon.com/servicequotas/home/services/ec2/quotas/L-DB2E81BA)。

## 方案比较

| 方案 | 是否解除当前阻塞 | 费用及赠金 | 目标损失/不确定项 | 判断 |
|---|---|---|---|---|
| 东京换 g6e.xlarge | 否，仍用 G/VT 配额；4 vCPU 仍大于 0 | EC2 赠金适用需保留其余门槛 | 同 L40S 48GB，但系统 RAM 从 64 降到 32GiB，不能保证 H3 加载/卸载稳定 | 不作为解决办法 |
| 东京换 g5/g6/g4dn | 否，同配额 | 单价低不等于可启动 | 常见单卡为 24GB/16GB；目标 H3 的稳定性、卸载和耗时未测，不能保证 4h | 不推荐本次首验 |
| 东京 Spot / P 系列 | 已查配额也均为 0 | Spot 有中断风险；P 需另查报价 | 换计费方式/族不能被当作已可用 | 已查路径排除 |
| 新加坡/悉尼 | 已查按需与 Spot 都为 0 | 仍在 AWS，可用赠金需具体资格复核 | 其他区域尚未知，不能声称全球均不可用 | 不重复押审批 |
| SageMaker 自托管 | 未验证；使用独立的区域/型号/用途配额 | 赠金清单有 SageMaker，但具体项/附加费仍需核 | 新部署架构、容器、角色、终止机制；endpoint 空闲也可能计费 | 仅可继续只读排查，非已验证捷径 |
| MiniMax 官方 H3 API | 无需本账户 EC2 GPU 配额 | 旗舰768P 5秒基础价 **$0.40**，另付费，不能抵 AWS 赠金 | 能真实 H3、恢复任务和下载；不能验证自部署 INT8、SSM、显存峰值；最低充值未知 | **业务跑通优先** |
| Comfy Cloud | 无需本账户 EC2 GPU 配额 | 官方宣传新用户5次GPU运行；H3具体免费资格需登录核实。Standard月付 **$20** | 付费API可接程序；免费不能当已具备API。H3每条credits未知，30分钟单工作流限制 | 先只读查资格，暂不订阅 |
| 外部 GPU 自托管 | 不受本账户 AWS 配额约束 | Runpod公示 L40S **$1.09/h**，4h **$4.36**；A100 80GB **$1.79/h**，4h **$7.16**；均另加存储等且另付费 | 实际合法地域/GPU配对库存未知；需新的私有隧道与独立停机；不再是 AWS SSM 验收 | **自部署实验备选** |

## 推荐的执行边界（等待用户决定）

**A：官方 H3 API。** 先查账号可用性、最低充值和实际扣费规则；用户确认小额自付上限后，只跑一条单图、768P、5秒任务。基础价 $0.40 不等于首次需支付 $0.40；不要购买只支持 Hailuo 的视频套餐冒充 H3。首帧图生比例随输入图自动确定，须准备竖屏图。保留未知提交阻断、task_id查询恢复、自动Windows下载和校验；不把服务端费用估算当实测账单。

**B：外部 GPU。** 若必须验证 INT8/VRAM，优先有足够 RAM 的 L40S 48GB 或 A100 80GB；同显存不同架构不能推断同速度。先确定所在国家、真实库存、含存储报价、最低充值，以及双独立4h停止。H3社区排除美国、欧盟、英国、韩国，不能只看最低价就选机器；日本机房存在不代表日本有公示的L40S/A100。第一条先验证，不承诺4h能出多少视频。

**C：只用 AWS 赠金且不另付费。** 可做一次有限的未查区域/服务现有配额排查；仅发现已经可用、无需审批且费用/许可/停机均通过的资源才继续。若仍无可用GPU，则接受本轮无法验收自部署H3，先完成本地工程，不为“用完赠金”创建CPU机器或其他无助于目标的资源。

Comfy Cloud 可在 A/B 决策前先核资格，但不是“5次必定免费的H3视频”：官方页面的免费描述有工作流差异，Partner Node 与原生GPU任务不同。套餐宣传视频数量基于 Wan 2.2，不能套算 H3。Standard $16/月是年付折算，需一次 $192；本方案比较使用月付 $20。

## 不采纳的表面捷径

- 改 Linux 为 Windows、改CPU核数、换同G家族小型号，都不使0配额变正数。[EC2 配额规则](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-on-demand-instances.html)
- CPU-only、Lightsail/Fargate、Inferentia/Trainium并不能直接运行当前CUDA版ComfyUI/H3实验；需重新验证支持和耗时，不能承诺短期替代。
- Bedrock并非所有视频模型都适合本次赠金。Nova Reel 1.0/1.1官方EOL已为2026-09-30；Luma Ray2模型卡明确通过Marketplace计费，普通AWS促销金默认排除Marketplace，且不是H3。未获明确适用证明前不调用。[Nova生命周期](https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle-legacy.html)、[Ray2计费](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-luma-ai-ray2.html)、[赠金条款](https://aws.amazon.com/awscredits/)

## 一手价格与功能来源

- [MiniMax H3 API创建/查询契约](https://platform.minimax.io/docs/api-reference/video-generation-v2-create)、[官方价格](https://platform.minimax.io/docs/pricing/overview)：旗舰768P $0.08/输出秒，任务前5张图免费。本文 $0.40 为单图、无输入视频、输出5秒的基础价推算。
- [Comfy官方价格](https://comfy.org/pricing/)、[H3入口](https://comfy.org/minimax-h3/)、[API计划说明](https://support.comfy.org/articles/2703236295-comfy-api-deploy-your-comfyui-workflow-as-an-api)：具体账号权益未登入核实。
- [Runpod官方GPU价](https://www.runpod.io/pricing)、[计费说明](https://docs.runpod.io/pods/pricing)、[日本地域公告](https://www.runpod.io/blog/runpod-apac-launch-fukushima)：价格不等于指定国家现货，4h数字仅GPU/CPU/RAM组合费，非完整报价。
- [AWS G6e规格](https://aws.amazon.com/ec2/instance-types/g6e/)、[SageMaker资源配额说明](https://repost.aws/knowledge-center/sagemaker-resource-limit-exceeded-error)。

## 本地工程与云端真实结果分别记录

本地新增REAL适配器、真实/Mock模式隔离、SQLite先持久化再唯一提交、后台下载与MP4校验。17项后端契约测试通过；前端严格TypeScript、Vite构建和4项契约测试通过；Ego已实测Mock上传/等待/下载/刷新历史，8767切Real被阻止，8768 Real门槛关闭。

这些全部是工程验收。**真实H3推理0次、真实视频0条、GPU峰值与实际实验费用未知。云端双重停机未部署。** 下载中断会重新下载同一MP4，不重发生成；尚不支持按HTTP Range断点续传。
