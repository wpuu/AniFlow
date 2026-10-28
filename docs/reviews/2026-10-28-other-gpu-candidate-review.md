# Other GPU candidates under the existing quota: read-only review

> 后续已完成账户实读与正式退出，以下“等待接回/未完成刷新”为此前历史。[2026-10-28 10:32实际结果](2026-10-28-other-gpu-live-results.md)。

北京时间2026-10-28。Owner要求先查清其他GPU实例，不再重复容量不足的g7e.2xlarge、g6e.2xlarge、g6e.xlarge，不提额、不升级、不降低画质。本轮RunInstances/DryRun/云资源变更/模型下载均0，生产硬件门槛未改。

## 已完成与未完成

已复核官方实例目录及CPU配额规则，发现此前漏查的 **G7（不是G7e）g7.2xlarge**。官方确认Ohio提供此系列，配置8 vCPU、32 GiB RAM、单RTX PRO 4500 Blackwell、名义32 GB显存。它是值得优先补查的新候选，**不是已证明有现货或能完成原工作流的实例**。G7驱动需要按官方要求核对，发布说明列出R595要求；没有部署或运行验证。

本轮账户实时查询尚未完成：Luna/high读取授权页时只有root空快照，没有可见输入框/密码框；它将此误判为需登录并主动handOff。该观察不能证明AWS登录过期。控制已交还用户，按Ego指南等待用户明确允许接回同一空间，随后先修复页面显示并继续只读查询；不要求用户先提供密码或MFA。新目录的批量只读查询已准备，尚未执行。本次未完成的临时登录进程及其CLI子进程已精确退出，授权文件已清理，私有认证文件及缓存均0；浏览器保持交还状态。[本地收尾证据](2026-10-28-other-gpu-auth-pending-cleanup.json)。

可引用的最后账户实读是北京时间2026-10-28 00:38:27：Ohio G/VT按需L-DB2E81BA=8 vCPU、非终止实例0。20个启用区域仅Ohio G/VT按需非零的全区记录来自10月27日，**不能标作本轮实时刷新**。[历史区域记录](2026-10-27-all-enabled-gpu-quotas.json)。

## 根据官方目录与最后已知额度筛选

- **首选补查 g7.2xlarge：** 8 vCPU/32 GiB RAM、RTX PRO4500/名义32 GB显存。按上次8核额度，单台规格符合；尚待新账户查询、实时价格和最终开机验证。
- **第二梯队 g5.2xlarge：** 8 vCPU/32 GiB RAM、A10G/名义24 GB显存。显存小于单份约26.615 GiB的FP16专家权重，必须依赖分层权重搬运；不能据此宣称不可能，也不能保证在4小时内按原参数完成。
- **第二梯队 g6.2xlarge：** 8 vCPU/32 GiB RAM、L4/名义24 GB显存，具有相同的显存约束和更频繁权重搬运风险。GPU变小本身不等于降低画质；本轮未改精度、权重、分辨率、帧数或步数。
- **不建议作为原目标首选 g4dn.2xlarge：** 8 vCPU/32 GiB RAM、T4/16 GiB显存。相对上述候选显存更紧，尚无原工作流成功或时限证据。
- **超出现有已知额度 gr6.4xlarge：** 最小16 vCPU/128 GiB RAM、L4/名义24 GB；不能通过关闭核心或超线程把配额消耗改成8。它和WorkSpaces Personal的同名桌面产品是不同的配额与创建路径。

原目标保持此前已批准的Wan2.2-I2V-A14B四份FP16权重、800×1376/121帧/24fps/20步，最终按原方案裁成774×1376/120帧/5秒，不改为其他模型、量化或CPU推理。32 GiB系统内存仍有加载风险；Comfy按层/阶段换入权重的源码路径只说明可研究，不能当作真实GPU验证。原厂命令说明至少80 GB显存，因此32/24/16 GB均不能称为原厂已验证配置。

## 下一步及证据边界

用户允许接回后，先刷新20区实际G/VT按需、G/VT Spot及P配额；仅在有非零G额度的区域完整枚举g* GPU目录，按默认vCPU及当前用量筛选，再补可用区offering和原生Linux共享按需价格。机器目录及offerings只证明该区域提供型号，不能证明实时按需容量；DryRun也不证明容量。**本轮只查，不创建新候选，不重试旧失败型号。**

[结构化来源与历史账户观察](2026-10-28-other-gpu-candidate-sources.json)。PR #7保持Draft，main未合并，原ZIP和D/G归档未改。

官方来源：

- [G7产品规格](https://aws.amazon.com/ec2/instance-types/g7/)
- [G7发布说明与驱动要求](https://aws.amazon.com/blogs/aws/announcing-amazon-ec2-g7-instances-accelerated-by-nvidia-rtx-pro-4500-blackwell-server-edition-gpus/)
- [EC2加速计算完整目录](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html)
- [CPU选项不影响默认vCPU配额计数](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-optimize-cpu.html)
- [DescribeInstanceTypeOfferings定义](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstanceTypeOfferings.html)
- [原厂Wan2.2-I2V-A14B说明](https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B)
- [固定Comfy内存管理源码](https://github.com/Comfy-Org/ComfyUI/blob/63be2f9b82ad0dac88a7ceaa28a9cf3154125a18/comfy/model_management.py)
