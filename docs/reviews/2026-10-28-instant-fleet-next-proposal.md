# 下一步：一次请求，在两款未试GPU与三个可用区中只选一台

状态：**具体待批准方案，未实现新的云端启动器、未创建资源、未下载模型。** 上一轮G5.2xlarge的资源已全部释放，真实GPU预检与视频仍为0。Owner要求继续推进，本轮先完成只读研究和独立Luna/high审查。

## 采用的具体方式

使用AWS EC2 Fleet的`instant`方式，仅发一次同步请求，目标容量为1台按需实例、Spot为0。候选仅限尚未试过的 **g6.xlarge（优先）和g5.xlarge**，分别列出Ohio三个已有默认子网，共6个“机型×可用区”选项。所有权重为1，容量单位为实例数，最多实际创建1台；不包括任何已经容量拒绝的2xlarge、L40S或G7类型，不自动补机，不定时重试。

[AWS官方说明](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instant-fleet.html)确认instant是同步一次请求，响应直接给出实际实例和各候选错误；[按需优先级](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_OnDemandOptionsRequest.html)可配置。这个方式改善一次请求内的选择范围，**不会产生新库存，也不保证成功**。此前auto请求不能视作全部可用区的逐一容量证明。[创建接口](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_CreateFleet.html)。

两款候选以今日10:32账户目录实读为依据，尚未在本方案中重新刷新：[账户候选记录](2026-10-28-other-gpu-live-results.md)。

| 候选 | CPU / 系统内存 | GPU目录显存 | 已查Ohio Linux按需价 |
|---|---|---|---:|
| g6.xlarge | 4 vCPU / 16 GiB | L4，22,888 MiB（约22.35 GiB） | $0.8048/小时 |
| g5.xlarge | 4 vCPU / 16 GiB | A10G，22,888 MiB（约22.35 GiB） | $1.006/小时 |

**与此前批准的G5/G6.2xlarge相比，CPU、系统内存减半；显存没有增加。** 原FP16权重、800×1376/121帧/24fps/20步与5秒裁边方案不变，不启用CPU推理，不通过降低精度、分辨率、帧数或步数救场。16 GiB主存不能完整驻留单份约26.615 GiB专家；磁盘映射与按层搬运有代码路径，但本工作流尚未在该硬件实测，可能内存不足、显存不足或超过4小时。成功完成CUDA预检也不代表能生成原画质视频。

## 预算和执行门槛

以较贵G5.xlarge为上界，10分钟计算约0.167667美元；原预检辅助费用约0.067262美元，另加0.01美元新流程日志/操作余量，服务费约0.244929美元；再留等额税/误差缓冲，**抵扣前约0.489857美元，预算取0.50美元以内**。这是本轮估算，不能冒充最终抵扣、税额或历史项目总账。创建前须重新核定当前价、赠金余额与券范围、配额、原有计划状态和无Marketplace官方镜像；不调用收费Cost Explorer API。

[AWS FAQ](https://aws.amazon.com/ec2/faqs/#EC2_Fleet)确认Fleet本身不额外收费，只支付其启动的底层资源；[官方先决条件](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-fleet-prerequisites.html)说明instant不需要创建EC2 Fleet专用服务关联角色。本方案不采购预留实例、Savings Plan、容量预留或容量块，不升级计划、不提额。小时价限制不能代替运行时间或总账保护。

Owner明确接受4 vCPU/16 GiB风险后，先在新唯一实验目录实现并验证启动器，再允许云端操作：

1. 全新部署Ohio主停机保护、新加坡独立备用及私有报告资源；主无目标真实调用/IAM正反例/备用四步骤逐项Success。固定装置后7分钟停止、8分钟兜底终止，两栈更新完毕、实际读到备用等待正确时点后才能发请求，不延长运行中截止。
2. 启动模板写入同一不可续期本机截止，实例/卷/网卡与Fleet均标记本轮实验；官方免费镜像、180GB加密gp3、无入站端口、仅443出站、IMDSv2、关机停止。模板及Fleet也纳入本轮精确清理。
3. 请求前持久化唯一ClientToken与意图，SDK总尝试1；只调用一次CreateFleet。逐项处理返回的Instances与Errors，不能把Fleet的fulfilled状态当开机成功；部分成功也立即纳入保护。超时/未知结果按原Fleet、请求键及标签核对，绝不新建请求。
4. 本地先验证候选白名单、目标1/Spot0/权重1、部分成功、空实例、多实例异常、超时与标签缺失的处理。共享保护沿用既有模块，本轮仍需重新部署和真实无目标验证；本地模拟不计为真实GPU成功。
5. 若有实例，只做真实硬件/FP16 CUDA/SSM/私有S3预检，最多10分钟并确认实际Stopped或terminated；不下载模型。保存小报告并验证哈希，清理所有本轮计算、卷、网卡、Fleet、启动模板和辅助资源，官方退出。未知实例状态先保留双保护。

本轮研究AWS资源变更0、创建0、模型下载0；原ZIP、D/G归档、Bridge和画质设置未修改，PR #7保持Draft、main不合并。没有获得Owner对新CPU/内存规格的明确同意前不创建此方案资源。
