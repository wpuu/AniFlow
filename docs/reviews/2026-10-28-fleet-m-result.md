# 已真实开出G6并验证GPU；严格10分钟终态验收差1.51秒，已全清

北京时间2026-10-28 **20:56:22**，m第1次非DryRun CreateFleet成功分配**1台Ohio us-east-2a的g6.xlarge**，随后实际观测到Running。没有参数修正或第二次创建；有界账本终态为created，后续创建禁止。此前“实例始终没开出来”的阻塞在本轮已实际突破，但这不代表保留库存或后续一定能再次分配。

**真实GPU/私有通路通过，整体验收未通过：** L4 FP16运算、SSM只读命令和加密私有S3往返均成功；从请求前意图到API观测Terminated的保守上界为**601.511584秒**，含启动与关机过程，超过≤600秒验收线1.511584秒。因此明确保留`overall_real_preflight_success=false`。不能把CUDA成功、发出停机请求、停止中或终止中当成整体通过。[实际结果与状态时间线](2026-10-28-fleet-m-result.json)。

## 真实硬件和测试证据

| 项目 | 实测 |
|---|---|
| 类型 / 可用区 | g6.xlarge / Ohio us-east-2a |
| CPU | 4逻辑CPU、2物理核、每核2线程 |
| 系统内存 | 实际15.00346 GiB，规格16 GiB |
| GPU | NVIDIA L4，CUDA可见22.03625 GiB |
| nvidia-smi显存 / 驱动 | 23034 MiB / 595.112.07 |
| PyTorch / CUDA构建 | 2.11.0+cu130 / 13.0 |
| 真实FP16矩阵计算 | 5.772765秒，finite检查通过 |
| 该小测试峰值显存 | allocated 44.125 MiB、reserved 62 MiB |
| 私有通路 | SSM命令Success；IAM角色S3 AES256写入/读取和正文一致性通过 |
| 机内固定截止 | journal实际确认已装置21:02:00固定停止 |
| ffmpeg / ffprobe | 未安装 |

这些是小型CUDA硬件测试，不是14B模型显存需求、模型推理耗时或视频显存峰值。[原始GPU报告](2026-10-28-fleet-m-gpu-report.json)1061字节，SHA256为`8b21694ec664857a776406749aa42c633051b99772da7d47c0f45854e3eb1188`；从私有S3下载到Windows后再次完整校验通过。[两份报告及哈希](2026-10-28-fleet-m-saved-reports.json)。本机保存在任务的`work/fleet-admission-20261028-m/saved-preflight-reports/`，没有MP4。

**ComfyUI和模型均未部署，模型下载/加载0、真实视频0。** 16 GiB主存对原FP16工作流的风险尚未实际测试，原画质参数与Bridge生产门槛未改，不能在前端宣称真实视频Ready。

## 赠金、费用和创建前保护

[新Billing观察](2026-10-28-fleet-m-credit-scope.json)确认五笔Active、2026-10-30到期，预计43.45美元与账面91.14分开；预计20美元Lambda券覆盖EC2/VPC/SSM/S3/Lambda/CloudWatch/Events/CloudFormation/KMS/DataTransfer。EBS和IPv4仍是EC2/VPC服务级映射，未逐项UI确认。官方Amazon镜像无Marketplace产品码、账户原有PAID/ACTIVE未升级，无提额/税务变更/付费Cost Explorer API。

[实际新价及规格](2026-10-28-fleet-m-eligibility.json)为G6.xlarge 0.8048美元/小时、G5.xlarge 1.006美元/小时，Ohio配额8/创建前实例0。按601.511584秒和G6单价计算，EC2部分的**保守估算上界约0.134471美元**，低于原预算按较贵G5预留的0.167667美元。它不是已入账费用，辅助服务费、税与最终赠金抵扣仍待账单，不承诺自付为0。[授权合并预算](2026-10-28-fleet-m-budget.json)含k/l辅助费、m完整预检及最多两次未使用的重设预留，抵扣前含等额缓冲约0.866905美元，创建前≤0.90门槛实际通过；排除更早项目历史，不冒充历史总账。

创建前全新三栈实际CREATE_COMPLETE，主无目标调用/IAM正反例和独立新加坡四步骤Success；固定停止21:02:00、兜底终止21:03:00，两栈实际UPDATE_COMPLETE及备用真实等待确认后才提交计算请求。[初始保护证明与真实演练边界](2026-10-28-fleet-m-protection.json)。首次即成功，未消耗批准的两次参数修正额度，也不能把剩余额度用于重复容量申请。

## 真实停机问题与只读复核

状态实读时间为Running 20:56:55、Stopping 20:59:48、Shutting-down 21:03:14、Terminated **21:06:23.942**。CloudTrail确认：根控制器20:59:43发出普通Stop；独立备用21:02起多次Force Stop但未跳过OS关机；主保护21:02:51也发出Force Stop；独立备用21:03:11发出普通Terminate。直到21:05:06，根控制器针对唯一自有实例补发Force＋SkipOsShutdown终止，随后才观测到Terminated。API接受请求不代表终态已经完成。

正式独立备用中WaitUntilStop和WaitUntilCleanup为Success，**IndependentStop与IndependentCleanup均Failed**，原因均是未在各自有界等待窗口内确认计算终态。无目标演练通过不能替代真实GPU停机成功。[SSM四步骤及CloudTrail只读复核](2026-10-28-fleet-m-stop-audit.json)、[精确实例补发强制释放记录](2026-10-28-fleet-m-forced-release.json)。没有证据证明具体底层主机故障；记录只支持API请求已执行、终态较晚返回的结论。

[AWS Stop接口](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_StopInstances.html)说明Force仍先尝试正常OS关机，SkipOsShutdown才绕过该等待；[Terminate接口](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_TerminateInstances.html)同样默认包含OS关机。拟修正仅用于无模型临时预检、提前装置兜底并保留报告先保存与哈希校验，不能静默用于有未保存模型/视频写入的任务。已准备[仅本地、未部署的修正草案](2026-10-28-preflight-stop-patch.md)，本轮m没有该新phase标签，不能算新草案的真实验证，也不能保证下次≤600秒。

## 实际收尾与下一步

21:08:51已核实实例终止，全部关联卷/网卡不存在，Fleet删除终态、启动模板不存在，全部三栈及角色/Profile、Lambda、规则、日志、备用文档、安全组、私有桶不存在；S3小报告先下载校验再清理。[完整清理回执](2026-10-28-fleet-m-cleanup.json)、[Fleet/模板回执](2026-10-28-fleet-m-metadata-cleanup.json)。21:09:08官方CLI退出、缓存0，[退出回执](2026-10-28-fleet-m-auth-cleanup.json)。

为了核实备用失败，又建立了只读审计临时会话，只读取已终止m实例的保留SSM/CloudTrail记录，新资源0；21:14:35也已官方退出、缓存0，[只读审计退出回执](2026-10-28-fleet-m-stop-audit-auth-cleanup.json)。Ego仍Luna/high，自有页关闭、原页及空间2 active保留，无finish/handOff。

当前没有本实验继续计费的资源。历史28次容量拒绝、两次Fleet参数拒绝保留；本轮增加一次真实成功分配和硬件/私有通路成功记录，整体10分钟终态检查仍失败。下一步先审核停机草案并在新的授权/预算下实机复验，再进入原模型内存与原画质5秒视频验证；不自动再开机，不下载模型，不降画质救场。原ZIP、D盘H3及G盘未完成归档保留，PR #7仍Draft、main未合并。
