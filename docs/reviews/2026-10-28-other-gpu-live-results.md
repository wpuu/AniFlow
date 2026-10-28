# 其他GPU实例：现有配额、规格与价格实际核查结果

北京时间 **2026-10-28 10:31:54–10:32:38**，用户允许Luna/high接回后完成本轮只读核查。**新的首选候选是Ohio g7.2xlarge；它与已失败的g7e.2xlarge不同。配额及机型提供已确认，实际开机容量和原工作流成功尚未验证。** 本轮没有请求任何实例，也没有重试旧失败类型。

## 实际账户与覆盖范围

- 20个启用区域、3个EC2配额代码共60个实际值全部读到，无unknown：G/VT按需L-DB2E81BA仅Ohio为8 vCPU，其余19区0；G/VT Spot L-3819A6DF和按需P L-417A185B均在20区为0。
- Ohio非终止实例0，运行/待启动G/VT默认vCPU用量0；当前估算可用8 vCPU。
- Ohio完整g* GPU规格目录返回50种；13种默认vCPU符合现有额度，37种超过额度。13种中3种是此前已容量拒绝的G7e/L40S，本轮没有请求它们；其余10种中包括较小内存规格和3种分割GPU，不能全部当作适合原模型的视频方案。
- 当前账户计划接口实读PAID/ACTIVE，**这是原有状态，本轮没有升级**。赠金余额估算更新为 **44.43美元**，不再沿用旧45.31美元；估算不是最终账单或实时扣费承诺。
- 原始API存档含每个候选的规格、全部三个可用区及精确价格：[完整实读记录](2026-10-28-other-gpu-live-api.json)、[精简汇总](2026-10-28-other-gpu-live-summary.json)。

## 新候选的明确排序

下表显存为本次DescribeInstanceTypes报告MiB换算的GiB；价格为Ohio、Linux、共享按需、无预装软件，生效日期2026-10-01，本次10:32实读。4小时列仅含GPU实例计算费，不含磁盘、网络、保护及税，也不等于个人自付金额。

| 候选 | CPU | 系统内存 | GPU / API显存 | 美元/小时 | 4小时计算费 | 结论 |
|---|---|---|---|---:|---:|---|
| **g7.2xlarge** | 8 vCPU / 8物理核 / 每核1线程 | 32 GiB | RTX PRO4500 / **32 GiB** | **2.52** | 10.08 | 未试型号中显存最大，优先验证 |
| **g6.2xlarge** | 8 vCPU / 4物理核 / 每核2线程 | 32 GiB | L4 / **22.35 GiB** | **0.9776** | 3.9104 | 成本较低，但FP16权重搬运及内存风险更高 |
| **g5.2xlarge** | 8 vCPU / 4物理核 / 每核2线程 | 32 GiB | A10G / **22.35 GiB** | **1.212** | 4.848 | 同样显存约束，保留为备选；未做本工作流性能比较 |
| g4dn.2xlarge | 8 vCPU / 4物理核 / 每核2线程 | 32 GiB | T4 / **16 GiB** | 0.752 | 3.008 | 显存更紧，不推荐作为原目标首选 |

以上四种在本账户Ohio目录中均列出2a/2b/2c；**offerings不是库存证明，本轮没有RunInstances或DryRun。不能宣称其中任何一台已证明能开出来。**

其余新候选：g5.xlarge为4 vCPU/16 GiB RAM、同A10G 22.35 GiB、1.006美元/小时；g6.xlarge为4 vCPU/16 GiB RAM、同L4 22.35 GiB、0.8048美元/小时；g4dn.xlarge为4 vCPU/16 GiB RAM、T4 16 GiB、0.526美元/小时。相对2xlarge，主存减半且GPU显存不增加，不优先尝试。G6f large/xlarge仅约2.79 GiB分割显存，2xlarge约5.59 GiB；它们满足CPU额度，不代表适合该原画质14B工作流，不作为现成替代。

## 排除的路径

Gr6.4xlarge最小16 vCPU/128 GiB RAM，超过现有8核额度；Gr6f以及G5/G6/G7等4xlarge以上规格也不能靠关闭核心或超线程减成8核配额。EC2按默认vCPU计算配额，[官方规则](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-optimize-cpu.html)。本轮Ohio返回的GPU目录没有G4ad或G5g，不将其他区域或官方全局列表中的型号冒充本账户当前可用候选。SageMaker、Deadline及WorkSpaces历史检查没有在本轮重新刷新，不能将本次EC2结论扩大成“所有AWS产品已穷尽”。

## 原画质、费用与下一步边界

保留已批准的Wan2.2-I2V-A14B四份FP16权重、800×1376/121帧/24fps、20步及原裁边成严格5秒方案，不改变精度、模型、分辨率、帧数或步数，不启用CPU推理。**GPU变小不自动降低画质，但仍可能加载失败、显存不足或超过4小时。** 单份专家约26.615 GiB：G7的32 GiB显存还要容纳激活、缓存与CUDA开销，不能仅凭权重小于显存保证成功；G5/G6甚至无法完整驻留单个FP16专家，需要更频繁分层搬运。Comfy固定版本提供换入换出路径不等于本工作流已验证；[原厂命令](https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B)仍写至少80 GB显存。

**建议下一步只对G7做首次受保护GPU预检，再决定是否进入原模型验证。** 它在未试型号中显存最大，CPU也是8个物理核心；32 GiB系统内存仍有加载风险。G6是更便宜的第二选择，不预先承诺速度或成片率。新G7的GPU计算费10分钟约0.42美元；这不是全费用。赠金44.43美元大于4小时10.08美元计算费，但**整条生成/归档/网络/税费以及赠金抵后自付≤1美元尚未重新核定**，不能把“有赠金”当作已经通过现金上限。4小时是GPU运行上限，不是承诺运行满4小时。

本轮授权仅核查，**未创建新候选、未重建保护、未改Bridge硬件门槛、未恢复模型下载**。如后续采用新型号，须先按批准范围重建并实际验证双重停机，再做最长10分钟真实CUDA/私有通路预检并确认Stopped；模型与真实视频验证在实例解决后进行。失败停止清理，不能降画质救场。

## 连接与收尾

Luna/high接回原空间后，正常显示的主内容为“Continue with an active session”，不需要用户重新输入密码。官方验证码是长文本；此前空快照和短码筛选误判已纠正。本次新连接成功，业务只读API由主负责人顺序执行；云资源变更0、创建0、模型下载0、真实GPU预检0、视频0。临时CLI已官方退出、认证缓存0、全局配置与浏览器登录未改，[退出证据](2026-10-28-other-gpu-live-auth-cleanup.json)。子代理误调用finish，工作区2已结束；原三页未操作，当前核查及官方退出均已完成，不构成本轮业务查询阻塞。

PR #7保持Draft，main未合并，原始ZIP、D盘H3归档与G盘未完成文件保持原样。

参考：[AWS G7规格与驱动说明](https://aws.amazon.com/blogs/aws/announcing-amazon-ec2-g7-instances-accelerated-by-nvidia-rtx-pro-4500-blackwell-server-edition-gpus/)、[实例规格目录](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html)、[Offerings接口定义](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstanceTypeOfferings.html)。
