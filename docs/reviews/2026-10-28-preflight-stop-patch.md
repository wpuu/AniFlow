# 仅本地停机修正草案：尚未部署或真实复验

本轮m首次真实G6已验证硬件/私有通路，但API确认Terminated耗时601.51秒、超过严格600秒门槛1.51秒，独立Stop/Cleanup步骤均Failed。[实际状态与CloudTrail/SSM证据](2026-10-28-fleet-m-result.md)。所有m资源已释放，无继续计费的本轮资源；本草案没有重新开机、修改AWS资源或执行视频。

## 本地准备的改动

新增独立的`infra/ec2/preflight_guard.py`、`infra/ec2/preflight_templates.py`及`tests/test_preflight_guard.py`；**原g7_guard、g7_templates、wan_deadline及生产Bridge未改**。未来调用方需要明确选择新草案，它不会自动替换已有路径。

- 仅面向无模型、可丢弃临时盘的GPU预检，代码与IAM同时要求精确ExperimentId及`ExperimentPhase=gpu-preflight`。缺/错phase直接拒绝；不会把不匹配实例隐去后当作“零实例成功”。不适用于有模型/视频未落盘写入的任务。
- Stop与Terminate均显式`Force=True`和`SkipOsShutdown=True`，减少默认正常OS关机等待；仍只允许Stop/Terminate，不能Run/Start或扩容。
- 提供UTC固定截止函数：装置后5分钟Stop、6分钟Terminate，保守舍去微秒，较原7/8分钟更早留出控制面和观测余量。**不延长任何正在运行实例的截止**，本轮m已终止，不进行追溯修改。
- 创建云端EC2 client后，在任何查询或停机前检查StopInstances/TerminateInstances的服务模型均支持Force、SkipOsShutdown；任一不支持或无法检查即失败，不退回慢停机。未来真实主/备用无目标验证也会先检查云端SDK能力，未通过不得创建GPU。
- 主25秒、单次SDK尝试；独立备用四步骤、每脚本150秒/1attempt、内部120秒及迟到Stop不能推迟Cleanup的边界沿用。确认必须是实际Stopped/terminated，ack、Stopping和Shutting-down均不算完成。

## 验证与限制

**17项纯本地测试、Ruff和差异检查通过**：双标签/错区域拒绝、强制参数、真实后续终态才成功、短超时、IAM无Run/Start、UTC5/6分钟、SDK支持与旧模型缺字段拒绝；测试不读AWS凭证、无AWS调用。代码可内联进Lambda/SSM，仍需未来真实部署/无目标证明/权限正反例/备用等待和真机计时复验。

本轮m没有新phase标签，且当时执行的是旧保护，**不能用m的GPU结果证明本草案有效，也不能保证下次≤600秒**。AWS底层或控制面延迟不能仅靠本地测试消除；未来必须保留真实终态计时，失败就清理并停止下一阶段。

[AWS Stop接口](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_StopInstances.html)说明Force仍会先尝试正常OS关机；SkipOsShutdown可跳过该过程但可能丢失未落盘数据。[Terminate接口](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_TerminateInstances.html)也说明默认OS关机及跳过参数。本草案只适合无模型临时预检，**报告必须先完成私有S3保存、本机下载和哈希核对**；不静默用于模型归档、真实生成或生产任务。

下一次如获准使用，需要新唯一实验、全部实例/卷/网卡phase标签、新5/6分钟模板参数及UserData、全新主备实际证明、当前赠金/预算，并最终真实GPU计时。现有一次真实容量授权已经消费，不因参数修正额度尚余而重新开机。原模型和画质参数不变。

**尚未把新草案接入任何实例启动器。** 本轮m的历史启动模板只有原ExperimentId/Name，不能直接配新guard使用；未来必须先接入启动标签和新截止、验证标签与IAM一致，再做真实无目标及GPU复验。不能仅部署这三个文件就声称保护可用。
