# G7首次准入与真实GPU预检计划

Owner已明确授权g7.2xlarge：先完整预算和双停机，赠金抵后自付≤1美元才最长10分钟真实GPU预检；先实例、不下载模型，不提额、不升级、不降画质。本计划为新唯一实验h，日期命名空间沿用既有安全模板20261027，但实际执行日期为2026-10-28。

最新官方CLI只读确认Ohio G/VT按需8、实例0，G7 Linux共享按需2.52美元/小时、8物理核/8vCPU、32GiB RAM/32GiB GPU；免费Amazon官方PyTorch2.11 Ubuntu24.04镜像，无Marketplace产品码。Ego由Luna/high完成官方临时连接及Billing核查，随后停止Ego；主负责人唯一执行云资源操作。

## 预算与抵扣

[当前赠金UI证据](2026-10-28-g7-h-credit-scope.json)：五笔Active，均2026-10-30到期；账面91.14美元与预计44.06美元分开，按更保守预计值计。EC2/VPC/SSM/S3/Lambda/CloudWatch/CloudWatch Events/CloudFormation均列入服务范围；一笔预计20美元券另实读包含KMS和DataTransfer。控制台没有逐项EBS/IPv4条款，[映射记录](2026-10-28-g7-h-credit-mapping.json)明确这是原生服务映射：gp3价格接口ServiceCode=AmazonEC2，AWS文档将IPv4计入AmazonVPC；不伪称逐项UI确认。[AWS说明](https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html)。

[完整费用估算](2026-10-28-g7-h-budget.json)包含最多10分钟GPU0.42美元、180GB加密gp3最多1小时0.021429美元、IPv4、SSM证明与正式执行共8步/4脚本硬150秒、Lambda最多62次25秒128MB、日志/S3/KMS/小额传输。合计服务费约0.487262美元，另留等额税和误差现金缓冲，**未计任何赠金前合计约0.974524美元**。这是操作边界内的保守估算，不是最终账单或税率声明；并未凭“当前税0/税登记API未找到”推断免税。Tax UI有1笔登记、卖方AWS Inc.，国家/州unknown，资料未修改。赠金不抵税按[官方条款](https://aws.amazon.com/awscredits/)处理。移除收费CostExplorer API，不使用Marketplace、目录服务、NAT或付费端点。

## 新保护修复与准入

旧方案备用15分钟及多次长重试不能满足本轮，新增独立G7变体，不改旧WAN保护：主Lambda25秒、EventBridge及Lambda异步0重试；新加坡独立Automation依次WaitStop、IndependentStop、WaitCleanup、IndependentCleanup，Stop失败仍Continue到Cleanup，脚本150秒/单次，内部最多120秒并按Cleanup截止收紧。部署后实际主调用、IAM正反例及四个无目标备用步骤都成功，才允许固定装置Stop=当时+7分钟、Terminate=+8分钟；必须实际读到备用正在等待正确Stop时刻。机内也保留一次读取、不能续期的本地停机服务。

新G7保护36项测试及既有WAN/本地截止测试合计76项通过，Ruff通过。单元测试不等于云端停止成功。主负责人要实际观察Stopped/terminated，不把API确认当最终状态。最多一次auto新G7请求；先持久化唯一ClientToken，未知响应先核对，不重复提交；明确容量拒绝就清理，不试旧失败型号或横跳其他规格。

成功开机后仅运行镜像自带PyTorch真实FP16 CUDA矩阵运算、核对NVIDIA驱动≥595/RTX4500/实际CPU物理核和内存、SSM私有控制、S3加密角色读写。源依据：[官方DLAMI环境路径](https://docs.aws.amazon.com/dlami/latest/devguide/aws-deep-learning-x86-gpu-pytorch-2.11-ubuntu-24-04.html)、[G7驱动要求](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/public-nvidia-driver.html)。不安装或下载视频模型，不生成视频。

GPU测试完成或失败立即停止，观察请求到非运行的保守时间上界≤600秒。独立终止作为兜底。本轮不授权继续模型阶段；小报告先保存私有S3再本地校验哈希，随后释放实例、磁盘、网卡及三套辅助栈，核验资源缺失后退出临时连接。预检释放后不代表保留GPU物理库存，后续正式运行仍须重新验证准入。旧ZIP、D/G归档保持，Bridge门槛不改，PR7保持Draft。

执行前源码摘要：[哈希记录](2026-10-28-g7-h-execution-sources.json)。本文件是计划，不是实例创建或GPU成功证明。
