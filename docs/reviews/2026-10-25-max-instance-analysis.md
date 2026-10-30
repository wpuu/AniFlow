# 现有额度允许的最大实例组合及用途

日期2026-10-25。范围为已核实的东京额度与控制台目录，不冒充全球所有区域最大值。“能申请到”按现有额度无需申请提高理解；若是指提额申请可能获批多少，则无法事先保证。仅分析，无启动请求。此前CPU视频方案仍为用户已否决状态，本次CPU用途分析不构成重启该实验。

## 直接结论

当前东京可用GPU额度为0，无法形成任何有GPU的EC2组合。普通CPU按需额度5 vCPU、Spot额度另5 vCPU；总使用均观察为0。这两类额度不能合并让一台默认8 vCPU实例启动，也不能拿去抵G/P/X额度。

- **现代单机候选**：r7a.xlarge，4 vCPU（4物理核心）、32 GiB RAM、GPU0。
- **现代按需组合**：r7a.xlarge + r7a.medium，共5 vCPU／40 GiB，两台独立机器。
- **现代按需加Spot组合**：上述组合分别用按需和Spot各一组，共4台、10 vCPU／80 GiB；单进程仍不能使用跨机80 GiB。Spot库存未验证，不能称必定能开满。
- **已查目录中的旧代大内存候选**：m2.2xlarge，4 vCPU／34.2 GiB、GPU0；再加r7a.medium可达按需总5 vCPU／42.2 GiB。如果两组分别用按需和Spot，账面合计10 vCPU／84.4 GiB；旧型号Spot供应及兼容AMI未验证，这不是可执行推荐。

这些是配额允许的组合和目录候选，不是已验证启动资格、即时库存或全目录穷举的性能冠军。“最大”按vCPU/内存分别描述，不把老架构多一点RAM当成计算性能更强。

## 东京实际完整类别读数

按需：Standard5；DL、F、G/VT、High Memory、HPC、Inf、P、Trn、X各0。Spot：Standard5；DL、F、G/VT、Inf、P、Trn、X各0。[结构化脱敏证据](2026-10-25-max-instance-evidence.json)。

X2iedn.xlarge虽为4 vCPU／128 GiB，但属于X独立额度，当前为0，所以不能拿Standard5开它。关闭超线程或减少启用核心也不能绕配额，AWS按实例默认vCPU计数。[配额分类](https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-quotas.html)、[CPU Options规则](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-optimize-cpu.html)、[X2i规格](https://aws.amazon.com/ec2/instance-types/x2i/)。

普通CPU实例不能外接一张EC2显卡，也不能把系统RAM当CUDA显存；需选择自带GPU的G/P实例并满足对应额度。上述所有CPU组合GPU均为0。

## 基础Linux计算费

| 方案 | CPU／RAM | 每小时 | 24小时 |
|---|---|---:|---:|
| r7a.xlarge | 4／32 GiB | $0.36708 | $8.80992 |
| r7a.medium | 1／8 GiB | $0.09177 | $2.20248 |
| 两台r7a按需组合 | 合计5／40 GiB | $0.45885 | $11.01240 |
| m2.2xlarge | 4／34.2 GiB | $0.57500 | $13.80000 |
| m2加r7a.medium | 合计5／42.2 GiB | $0.66677 | $16.00248 |

均为本次或同日授权控制台读数。Spot价格随可用区和时间变化，本轮没有报价，不假设固定折扣。磁盘、IPv4、传输、SSM网络端点、日志、税费不在表内；预计赠金余额不能等同实时消费硬限额。账户Free/Paid和全部费用资格仍未完全确认，未授权实际创建。

M2仅比r7a.xlarge多2.2 GiB内存，计算费高约56.6%；架构更老、镜像兼容与库存未验证，不建议为这点容量优先使用。[R7a官方规格](https://aws.amazon.com/ec2/instance-types/r7a/)、[旧代M2目录](https://aws.amazon.com/ec2/previous-generation/)。

## 这些CPU机器可以做什么

以下是按硬件与软件能力做的用途判断，不是本账户实测吞吐承诺。

1. **已有视频的批量后期**：FFmpeg裁剪、拼接、转码、烧录已有字幕、加水印、裁成竖屏、音轨处理、提取封面和校验MP4。可以处理已有高分辨率文件，但4核重编码耗时取决于编码器、滤镜与素材，不保证实时；没有GPU硬件编码加速。单台r7a执行处理，medium可做任务调度。[FFmpeg官方文档](https://ffmpeg.org/ffmpeg.html)。
2. **AniFlow任务后台**：托管Bridge/API、历史数据库、作业队列和自动下载校验，供开发验证；这只提供调度和存储，后端仍需要真正的视频推理算力。不能把网站跑起来当H3视频成功。
3. **轻量文本AI**：使用支持CPU的量化推理器试运行小型文本模型，辅助写脚本、标题、分镜和整理提示词。32 GiB可为某些量化模型及上下文留空间，但是否装得下取决于权重、量化和KV缓存；速度受4核及带宽约束，未实测，不承诺大模型高并发。[llama.cpp维护者资料](https://github.com/ggml-org/llama.cpp)。
4. **数据与开发工作**：素材去重、哈希、数据清洗、索引构建、程序编译、前端构建，以及开发规模数据库/缓存；32 GiB RAM对内存密集任务有价值，4核仍是算力边界。
5. **多机并行独立任务**：若Spot实际可用，可把互不依赖的视频转码或数据处理拆成小任务分发，单份任务完成即保存。Spot可被中断，因此不把它用于不可恢复的长任务；更不能宣称四台CPU可以自动合并成一块显卡。[Spot配额](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-spot-limits.html)、[中断行为](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-instance-termination-notices.html)。

## 与你的视频目标的关系

若目的是在赠金到期前得到原质量的真实图生视频，这些无GPU的组合仍不解决核心阻塞。它们更适合作为已有视频后期或开发/文本处理机器。当前不建议仅为消耗赠金而开满额度，也不建议为额外2.2 GiB选择旧M2。

若将来另选CPU用途，应先明确要交付的实际任务，再选一台现代机器；没有并行任务时无需开满四台。本次没有启用任何资源，也没有改变用户对CPU视频方案的否决。
