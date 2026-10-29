# 新G6真实预检通过，已停止并保留同一实例

北京时间2026-10-29 08:58:57实际创建Ohio2a g6.xlarge，08:59:18观测Running。真实L4/CUDA FP16运算、SSM机上命令、加密私有S3往返均通过；从请求到实际Stopped在600秒内，整体预检为true，实例与180GB磁盘保留，没有执行旧全删流程。

## 真实证据

- [实际创建与权限证明](2026-10-29-g6-o-creation.json)，不是DryRun或本地Mock。
- [真实预检、GPU与状态时间线](2026-10-29-g6-o-preflight.json)。L4的CUDA可见23661248512字节、4逻辑CPU、2物理核、RAM16109846528字节；PyTorch2.11.0+cu130、驱动595.112.07。小型FP16矩阵10.6905秒，不是视频速度或模型显存需求。
- [私有S3下载到Windows的两报告及SHA256](2026-10-29-g6-o-saved-reports.json)，原始GPU报告1065字节，SHA256 `4258c3f9455fa7d4e397304c6eba980af77a4c2fad132170f47943d4753c20f9`。
- [赠金当前服务范围](2026-10-29-g6-credit-scope.json)、[新价格及账户配额](2026-10-29-g6-o-eligibility.json)、[n与o合并预检预算](2026-10-29-g6-o-budget.json)，合并未抵扣前含等额预留0.94507619美元，低于0.95门槛；不是已入账费用。

新保护43项本地测试后，主Lambda/独立SSM真实无目标与IAM正反例通过才请求GPU。与失败n不同，本轮Stopping只重试Stop、不Terminate；Stopped保留。实际备用自动化总状态Success，但IndependentStop因未在该步骤窗口内见终态而Failed，后续IndependentCleanup确认计算已停止为Success。不能把总Success写成所有实际步骤均Success，也不能将创建前无目标演练当实际GPU停机。

## 未完成部分

ComfyUI、模型仍未部署，真实视频0。FFmpeg/FFprobe实测尚无；Linux bootstrap仅本地准备，31项测试不是真部署。G6.xlarge已获准的16GiB内存风险尚未模型实测，不改FP16/分辨率/帧数/20步，不用CPU推理。

下一阶段须在同一Stopped实例上先核定生产预算、更新并验证主/备/机内截止，再Start。旧截止不能直接重启。赠金预计42.64美元、账面91.14分开；到期仅知10月30日、具体时间未显示；税率仍未知，不能将历史零税零税基推断免税。

首帧与动作尚未收到，Owner要求先看到实例，不能擅选素材或提交占位工作流。原ZIP/D/G归档保留，PR7仍Draft、不合并main。[前一轮保留失败及修正](2026-10-29-g6-n-retention-failure.md)完整保留。
