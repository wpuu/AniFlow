# 已批准：G6.xlarge / G5.xlarge一次instant Fleet择一预检

Owner明确同意[具体方案](2026-10-28-instant-fleet-next-proposal.md)，接受4 vCPU/16 GiB内存不足及超时风险，原画质不变；只创建最多1台、最多10分钟真实GPU预检，不下载模型、不提额、不升级。原单机G5实验已完整清理，本轮全新k目录只复制执行源码，不复制认证、创建意图或旧保护证明。

[本轮新账户读取](2026-10-28-fleet-k-eligibility.json)：Ohio G/VT按需8核、非终止实例0，原有PAID/ACTIVE，预计赠金43.45美元。g6.xlarge为0.8048美元/小时，g5.xlarge为1.006美元/小时；两款4 vCPU/16 GiB、目录显存22,888 MiB。官方Amazon PyTorch2.11 Ubuntu24.04镜像可用且没有Marketplace产品码，默认VPC三个可用区子网及公网出站条件确认。目录提供不是库存证明，硬件未在机上测量。

[本轮新Billing券范围](2026-10-28-fleet-k-credit-scope.json)确认五笔Active、2026-10-30到期，预计余额43.45与账面91.14分开；预计20美元Lambda券覆盖本轮十项服务。EBS/IPv4仍是EC2/VPC服务级映射，未单独UI确认。税区unknown，未改税务资料或推断免税，不调用收费Cost Explorer API。

[当前完整预算](2026-10-28-fleet-k-budget.json)：按较贵G5.xlarge，10分钟计算0.167667美元；180GB加密gp3最多1小时、IPv4、双保护与证明、日志、私有S3小报告/KMS/少量传输，再加0.01美元流程余量，服务费约0.244929美元；留等额税/误差现金缓冲，**抵扣前约0.489857美元，小于批准的0.50美元估算上限**。它不是最终税额、已发生费用或历史项目总账保证。未来赠金核销与税以账单为准。

执行白名单仅g6.xlarge与g5.xlarge×Ohio三子网共6个候选；固定Type=instant、总目标1、按需1、Spot0、units实例单位、每个权重1，G6优先，G5其次。只用固定版本启动模板；小时价限制1.006美元不能当总费用硬帽。单次CreateFleet前落盘唯一ClientToken和意图，SDK总尝试1；没有维持、补机、定时重试或旧失败类型。未知/不完整响应先查原Fleet和标签，不发新请求；部分成功同时存在Errors也保留所有实际实例ID，不能把fulfilled或错误列表当GPU成功/零实例。

新增纯本地构建/响应安全模块与38项测试通过，Ruff通过；[本地SDK参数结构检查](2026-10-28-fleet-k-local-schema.json)也通过。对新增Fleet/模板清理另做[21项本地安全回归](2026-10-28-fleet-k-local-cleanup-tests.json)，覆盖有活动实例、标签缺失/错误、关联清单漏项、非instant、删除失败及精确删除条件，全部通过。它们均无AWS调用、不代表真实GPU成功。独立Luna/high只读审查私有控制器和保护/清理边界；主负责人独占AWS资源写入，另一Luna/high仅Ego官方临时授权与Billing只读。

创建计算前仍须全新三栈实际CREATE_COMPLETE、主无目标真实调用/IAM正反例/独立备用四步骤逐项Success；以装置后7分钟停止、8分钟兜底终止固定截止，两保护栈UPDATE_COMPLETE、备用实际等待正确时点后，才建带固定UserData与所有资源实验标签的启动模板并发唯一请求。不延长运行中截止。机上本地截止守护是第三层；无入站、仅443出站、IMDSv2、磁盘及网卡随实例删除。

若创建成功，只实际验证4逻辑CPU/2物理核/每核2线程、至少13 GiB实际系统内存、L4或A10G且CUDA显存至少21 GiB、保守驱动门槛525、FP16矩阵计算、SSM与加密私有S3往返。原FP16权重、分辨率/帧数/步数均未改变且本轮不加载，预检不能证明16 GiB主存可完成原工作流或4小时出片。收到实际Stopped/terminated状态响应后的UTC，加单调时钟下限，保守请求到终态须不超过600秒。

收尾先确认全部关联实例确已terminated，核实卷/网卡不存在；小报告先本地保存并核对SHA256，再清对象/桶。Fleet清理使用[DescribeFleets](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeFleetInstances.html)内的instant实例清单（不调用不支持instant的DescribeFleetInstances），并按[官方删除规则](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DeleteFleets.html)使用TerminateInstances=True；它只在所有实际实例已终止后执行。确认Fleet删除终态及精确启动模板不存在，再取消备用并删除本轮辅助资源、官方CLI退出。Fleet删除后的保留记录不等于继续计费资源；未知计算状态保持保护，不能提前撤除。

本文件记录执行前事实，不声称本轮保护已经部署或GPU已经创建。[批准范围](2026-10-28-fleet-k-approval.json)、[源码哈希](2026-10-28-fleet-k-sources.json)。ZIP、D/G归档、Bridge与画质参数不改，PR #7保持Draft，main不合并。
