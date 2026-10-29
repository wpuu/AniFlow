# AniFlow AWS东京H3｜Work模式执行交接｜2026-10-25

> **2026-10-29 14:14赠金实用核查：9月Finalized抵扣$8.86；10月可见Estimated抵扣$48.93，其中EC2 $45.38。** 累计预计已用$57.81/剩余$42.19包含9月，明细合计差$0.02照录；Bills仍Pending且0估算，不是最终零税/零自付证明。Bedrock命名奖励券实际抵扣Service是EC2，不能据券名推断调用Bedrock。详细固定版本/12步流程/停机幂等恢复/未验证项已形成[复用报告](../reviews/2026-10-29-aws-credit-video-reuse-report.md)与[实际应用历史](../reviews/2026-10-29-aws-credit-actual-usage.json)。用户最新要求到期后不用；当前实例仍Stopped保留，最终清理未执行、未设自动删除，真实视频0。下方历史中‘到期次日任何使用一律不抵扣’过于绝对，当前官方通用条款第9条涉及到期账期，详见复用报告；仍不据此承诺延期免费使用。

> **2026-10-29 14:00收尾完成：原Ohio G6已再次实查Stopped，实例和180GB加密卷保留，过期主规则DISABLED，备用均已终态。** 未再开机；本机前台真实Wan离线/禁止生成、目标L4/16GiB显示正确，队列0。CLI已退出缓存0。账户API赠金$42.19，原PAID/ACTIVE未升级；本次服务范围已核，实际账单抵扣与税待结算。停机存储约$24.40/月，Oct30到期后不能继续抵扣；完整本机Wan归档未验证，不擅删成功实例。下次启动须新三重截止，完整视频推理和持久开机服务仍未完成。[实际封存回执及费用](../reviews/2026-10-29-g6-o-stopped-closeout.md)。下面的待认证/未封存状态均为历史。

> **2026-10-29 部署后检查点：四份FP16模型约68.8GB、ComfyUI与真实Bridge已部署并连通，真实视频0。** 最后实际Stopped观测10:16:41；10:17:48一次同实例Start被容量不足拒绝，未重试。模型和180GB加密卷保留，修复前台的在线GPU复验未完成。AWS重新认证阻塞旧保护封存，严禁直接手动开机。停机磁盘当前约$24.40/月；Oct30赠金到期后不能再抵扣后续存储。持久启动服务、本机完整Wan归档均未完成。[实际部署、费用及剩余阻塞](../reviews/2026-10-29-g6-o-deployment-checkpoint.md)。以下预检及更早状态为历史。

> **2026-10-29 09:09：当前o实例真实预检通过，已停止保留，尚未部署模型。** Ohio2a g6.xlarge于08:58:57真实创建、08:59:18 Running；L4/CUDA FP16矩阵10.6905秒、SSM命令Success、加密私有S3往返通过，09:08:41实际Stopped，请求到终态584.466128秒<600，整体preflight=true。实例ID已直接交给Owner，Ego原空间2已打开同实例详情，磁盘和保护均保留，严禁旧全删/Fleet清理。正式独立自动化总Success，但Stop步骤Failed、后续Cleanup确认Stopped为Success，不能写成全部步骤都成功。两份小报告已落Windows并SHA256通过，GPU报告1065字节hash4258c3f9…；模型/视频仍0。当前修正43项本地测试，Stopping只Stop、Shutting-down只看、Terminate仅Pending/Running。此前n真实创建但因旧Stopping兜底逻辑被删，已明确向Owner承认并全清，不能掩盖。新Linux官方FP16 bootstrap和G6 Bridge候选支持已准备；Mock测试不是真部署。下一步在同一Stopped实例上核定生产预算/更新主备机内截止后再Start，不得直接用旧截止重启。赠金当前估算42.64/账面91.14、足额20券覆盖10服务、Oct30到期具体时间unknown、税率unknown。原ZIP/D/G保留，PR7仍Draft、不合并main。[当前真实成功及全部证据](../reviews/2026-10-29-g6-o-retained-success.md)、[n保留失败](../reviews/2026-10-29-g6-n-retention-failure.md)。以下均为历史。

> **2026-10-28 21:14：实例阻塞已实际突破，但严格停机终态验收未过。** m第1个非DryRunCreateFleet于20:56:22真实创建Ohio2a g6.xlarge，Running后实测L4/CUDA可见22.036GiB、4CPU/实际15.003GiB RAM，FP16矩阵5.7728秒、SSM/私有S3通过。没有模型/视频。GPU检查passed，但21:06:23.942才观测Terminated，保守请求到终态601.511584秒>600，多1.511584秒，overall preflight=false。正式独立Stop/Cleanup均Failed（未在有界等待内确认终态）；root21:05:06曾补Force+SkipOsShutdown释放。21:08:51所有m资源/Fleet/模板/卷/ENI已清，21:09:08退出缓存0；额外只读SSM/CloudTrail审计也于21:14:35退出缓存0。两份小报告下载本机并SHA256通过，GPU计算保守估算上界.134471美元，辅助/税/抵扣待账单；赠金本轮估算43.45、服务范围核实，合并预算.866905≤.90创建前通过。真实容量已成功，账本created，参数次数剩余不能用于新开机。停机修正仅本地草案17测试通过、未部署未实机复验；原ZIP/D/G/Bridge/画质不改，PR7 Draft、main未合并。[本轮实际结果与全部证据](../reviews/2026-10-28-fleet-m-result.md)、[停机本地草案](../reviews/2026-10-28-preflight-stop-patch.md)。下方均为历史。

> **2026-10-28 20:35 l已全清：** Owner批准修复后再发一次，l新实读赠金43.45/配额8/实例0，合并k辅助及本次预检含等额预留.644381≤.65自动门槛通过。全新三栈、主无目标/IAM正反例/备用四步Success，固定停止20:35/终止20:36，实际更新及等待后20:29:37唯一非DryRunCreateFleet被InvalidParameterCombination拒绝：prioritized与MaxTotalPrice不能同设；按ClientToken＋请求号＋错误精确CloudTrail匹配，Fleet/实例/卷/ENI/EIP0，未测容量。另两次显式只读DryRun（原非法与修正组合）均DryRunOperation，不能当参数兼容/库存证明。本轮非DryRun请求未重发。已改lowest-price保留小时价、去Priority，40项本地测试通过；20:35:29全部资源/模板不存在，20:35:45官方退出缓存0，备用Cancelled。历史容量拒绝28不变，另2次Fleet参数拒绝；GPU/机上预检/模型/视频均0。下步有界参数修正方案尚未获准或实现，不自动执行。[本轮实际证据与修正](../reviews/2026-10-28-fleet-l-result.md)、[下一步待批准方案](../reviews/2026-10-28-fleet-bounded-validation-proposal.md)。下方均为历史。

> **2026-10-28 19:24 instant Fleet k已收尾，尚未实际测试六候选容量：** Owner接受G6.xlarge/G5.xlarge、4vCPU/16GiB风险后，实读赠金43.45、配额8/实例0、价格.8048/1.006h、预算抵扣前含等额缓冲.489857。全新三栈及主无目标/IAM正反例/独立四步Success，固定停止19:22:01/终止19:23:01，两栈更新完成、备用实际等待后，19:16:23唯一CreateFleet被InvalidParameter拒绝。CloudTrail按原ClientToken精确证实ValidUntil不支持instant，未创建Fleet或GPU；**这次是提交参数组合错误，不是容量失败，既有28次容量拒绝不变**。删除该冗余参数的修正已完成，39项构建/响应及29项本地清理回归通过，但未重发。19:24:07本轮全部资源及模板不存在，19:24:20官方退出缓存0、正式备用Success；Ego空间2 active、自有页关闭。GPU/机上预检/模型下载/视频均0，原ZIP/D/G/Bridge和画质不改。下一次修正准入须Owner新同意，不擦除旧意图或自行重放。[实际原因、修正、清理与下一步](../reviews/2026-10-28-fleet-k-validation-correction.md)。下方均为历史状态。

> **2026-10-28 18:25 G5单次实验已结束：** Owner明确同意一次G5后，新j实验重新实读Ohio配额8/实例0、G5.2xlarge 1.212美元/小时、预计赠金44.06/五笔Active Oct30到期；预算服务约.269262＋等额税/误差缓冲、抵扣前约.538524美元。全新三栈、主无目标调用与IAM正反例、新加坡备用四步骤逐项Success；固定停止18:28:57/终止18:29:57，两栈实际更新且备用18:23:09等待确认后，18:23:18唯一auto请求也容量不足，无实例ID。18:24:53全部资源核实不存在，18:25:05官方退出缓存0。累计28次容量拒绝（G7e8/L40S2x13/L40Sx4/G7 1/G6 1/G5 1），真实GPU预检/模型下载/视频均0。显存风险未测试，不自动换型/重试，不降画质。原ZIP/D/G及Bridge门槛保留；Ego空间2 active、自有页已关，根无在运行控制器。下方进行中均为历史。[实际结果及完整证据](../reviews/2026-10-28-g5-j-result.md)。

> **2026-10-28 G6单次实验已结束：** Owner接受G6.2xlarge显存风险、不降画质后，i新实验先核定服务约.230195＋等额缓冲、未抵扣前约.460390美元，预计赠金44.06。新建三栈、主调用/IAM正反例、独立备用四步骤逐项Success，固定停止13:26:20/终止13:27:20，实际更新完成及备用等待确认后，13:20:39唯一auto请求也容量不足，无实例ID。零实例/卷核对后已全部清理、官方退出缓存0。累计27次容量拒绝（G7e8/L40S2x13/L40Sx4/G7 1/G6 1）；显存风险未实际测试，GPU预检/模型下载/视频均0。修正单次入口归档拦截及终态响应后计时，4项本地回归非GPU证明；未改共享保护/Bridge门槛。原ZIP/D/G归档保留；Ego空间2保持活跃，Luna停止操作。下方进行中均为历史。[实际结果及全部证据](../reviews/2026-10-28-g6-i-result.md)。

> **2026-10-28 12:12 G7本轮已结束：** Owner授权后新h实验先核定完整预算（服务约.487262＋等额税/误差缓冲，未抵扣前约.974524美元；预计赠金44.06），修复G7专用双保护并通过76项测试。三栈实际创建、主无目标调用与IAM正反例、独立备用4步骤逐项Success；固定停止12:16:17/终止12:17:17，两栈更新完成、备用真实等待后，12:10:45仅一次auto G7.2xlarge返回容量不足，无实例ID。未换区或改机型。12:12:32全部资源逐项核实不存在，12:12:48官方退出/缓存0。累计26次容量拒绝（G7e8/L40S2x13/L40Sx4/G7 1），GPU预检/模型下载/视频均0；Bridge门槛未改。Ego空间2保持活跃，Luna停止操作。下方仍在创建/等待授权均是历史。[实际结果与全部证据](../reviews/2026-10-28-g7-h-result.md)。

> **2026-10-28 10:32其他GPU实读完成：** 20启用区60项EC2配额全部读到，无unknown；仅Ohio G/VT按需8，其他区0、20区GSpot/P按需0。Ohio实例0，50种GPU规格中13种符合CPU额度，其中3种旧失败未重试、10种未试（含小内存和分割GPU）。新优先候选g7.2xlarge为8物理核/32 GiB RAM/RTX PRO4500 32 GiB，2.52美元/小时；G6.2xlarge为0.9776美元/小时、G5.2xlarge1.212美元/小时，两者显存22.35 GiB且主存32 GiB。三可用区offering不证明库存；本轮创建0、未改Bridge、模型下载0。赠金估算44.43美元，整条生成自付≤1尚未重核。CLI已官方退出缓存0；子代理误finish导致Ego空间2结束，原3页未动，当前只读核查已完成。[完整结果和API证据](../reviews/2026-10-28-other-gpu-live-results.md)。

> **2026-10-28其他GPU只读补查（未完成账户刷新）：** Owner要求停止重复容量失败机型，先查其他现有额度内GPU。官方目录发现此前漏查的G7 g7.2xlarge（8 vCPU/32 GiB RAM、RTX PRO4500名义32 GB），不是已失败G7e；G5/G6 2xlarge也符合上次8核额度但显存更紧，Gr6最小16核超额。Luna/high将空快照误判为需登录并主动handOff，登录过期未确认；等待Owner允许接回后先修复显示再执行已备只读查询。本轮EC2/配额业务查询、资源创建及模型下载均0，未改Bridge门槛。[来源、风险和待核查项](../reviews/2026-10-28-other-gpu-candidate-review.md)。

> **2026-10-28小规格实际结果：** Owner已同意的g6e.xlarge（4 vCPU/32 GiB、L40S）在新双保护实际验证及备用等待后，也对auto+2a/2b/2c四次全部返回容量不足，没有实例ID。当前累计25次容量拒绝（G7e.2xlarge8、G6e.2xlarge13、G6e.xlarge4）。本轮全部资源已逐项核实删除、临时CLI退出/认证缓存0。GPU/机上预检/模型加载/视频均0、模型下载仍暂停；Bridge门槛未改，也未触发或验证模型内存风险。[本轮完整证据](../reviews/2026-10-28-g6e-xlarge-g-result.md)。未创建定时重试或监控任务，未承诺30日前可用。

> **Owner已明确选择下一规格：** 同意试Ohio g6e.xlarge（4 vCPU/32 GiB、同L40S），接受内存不足风险；原模型和画质、赠金抵后自付≤1美元及双停机条件不变。该批准现已执行完毕：新独立实验g6x-g四次开机均容量不足，清理和临时连接退出已核验；Bridge原硬件门槛尚未改，模型未下载。下方“等待选择”已成为历史，不再重复询问同一硬件授权。

> **2026-10-28接续L40S收尾：** 继续此前已批准的8 vCPU/64 GiB g6e.2xlarge，新唯一实验f双保护实际验证/备用实际等待后，auto+2a/2b/2c四次请求也全部容量不足。当前接续8次失败（G7e4、L40S4），历史累计21次容量拒绝；GPU/预检/模型/视频均0，模型下载暂停。本轮所有资源已核实删除、CLI退出缓存0。[完整结果及待选方案](../reviews/2026-10-28-l40s-f-result-and-option.md)。只读核出g6e.xlarge价1.861美元/小时、同L40S但4 vCPU/32 GiB；未创建或改Bridge门槛，因CPU/RAM减半与模型加载风险，等待Owner选择。保留8 vCPU/64 GiB错时重试是另一选择。

> **2026-10-28 00:10本轮收尾：** Owner要求继续最高配置g7e.2xlarge；Luna/high仅完成Ego临时授权后停止，主负责人以唯一顺序执行器重建并实际验证双保护、确认备用真实等待，再做auto+2a/2b/2c四次真实请求，全部容量不足，无实例ID。累计容量拒绝17次（G7e8、L40S9），GPU/机上预检/模型部署/视频均0。模型下载仍暂停。本轮所有资源已逐项核实删除、CLI退出/认证缓存0。[本轮完整证据](../reviews/2026-10-28-g7e-e-result.md)。没有升级、提额或并行AWS资源操作者。下方为历史，不能把已清理保护视为仍部署。

> **本轮最终补查：** CLI退出后仅利用原Ego已登录会话，在Tokyo与Ohio WorkSpaces Applications分别搜索G6e，各16条Accelerated.g6e Fleet/Image Builder配额应用值及默认值均0。[两区实际UI证据](../reviews/2026-10-27-applications-g6e-quotas.json)。Tokyo Graphics仅可见25行也均0，不代表穷尽所有图形机型；Ohio Graphics未另查。没有重新建立CLI登录、没有创建任何资源。当前仍未找到可直接启动的新增GPU路径，已有Ohio按需额度仍面临实际容量拒绝；GPU/模型部署/真实视频0、模型下载继续暂停。

> **2026-10-27 22:39全区只读补查：** 全部20个启用区域EC2 G/VT Spot（L-3819A6DF）和按需P（L-417A185B）均通过Get实读为0、无unknown；SageMaker全分页筛中6151项G数字/P数字系列GPU实例配额，全部0、无空值或分页失败，覆盖G6e/G7e及P4/P5/P6，但正则未匹配gr6，不泛称穷尽所有AWS GPU服务。[20区汇总及原始完整记录哈希](../reviews/2026-10-27-all-region-gpu-quotas-complete.json)。Deadline Cloud独立GPU两码在10区实读均0，另10区NoSuchResourceException保留unknown，不算0。[Deadline证据](../reviews/2026-10-27-deadline-gpu-quotas.json)。东京/Ohio现有SageMaker Domain数均0、AI落地页未见明确验证待办，验证资格仍unknown；[Domain计数](../reviews/2026-10-27-sagemaker-domain-counts.json)、[页面观察](../reviews/2026-10-27-sagemaker-verification-observation.json)。官方说明账号验证后有默认GPU额度，但没有保证创建Domain能解锁，因此未创建Domain或申请配额。五笔同日完整赠金清单另确认均含Amazon Deadline Cloud及Amazon WorkSpaces Applications，仅是历史服务范围证据，[明细](../reviews/2026-10-27-managed-gpu-credit-scope.json)。本轮云资源变更0、模型下载0；CLI已退出、认证缓存0、精确文件清理，全局配置与浏览器登录未改，[退出回执](../reviews/2026-10-27-gpu-complete-auth-cleanup.json)。

> **2026-10-27 22:26实际配额补查：** 唯一Luna/high操作者恢复官方CLI只读连接，东京完整分页读取2268项SageMaker配额、其中122项G6e/G7e相关值全部0；Ohio读取2383项、其中142项全部0，覆盖Notebook、Studio、Training、Processing、Transform、Endpoint、Cluster等用途。[目标2xlarge明细及全量原文哈希](../reviews/2026-10-27-sagemaker-two-region-quotas.json)。此前两区unknown已解决为实际0，其他区域不能外推。本轮云资源变更0、模型下载0；官方CLI退出并精确清理认证文件/缓存，全局配置与浏览器登录未改。[退出证据](../reviews/2026-10-27-sagemaker-quota-auth-cleanup.json)。继续只读补齐其他区域Spot/P及SageMaker其他GPU类型的未查部分，不创建新服务。

> **剩余方案核查补充：** 本地重新检查同日05:15Z保存的五笔完整可抵扣服务原文，全部明确含Amazon SageMaker、Amazon Bedrock及AmazonBedrockFoundationModels；不是此次重新读取控制台，也不代表模型调用、GPU配额或所有产品费用已获准。[历史清单脱敏证据及原文哈希](../reviews/2026-10-27-sagemaker-credit-scope.json)。SageMaker为独立配额候选，官方已确认[Studio支持G7e](https://aws.amazon.com/about-aws/whats-new/2026/02/g7e-new-launch-sagemaker-studio-notebooks/)及[Notebook支持G6e](https://aws.amazon.com/about-aws/whats-new/2026/03/g6e-new-launch-sagemaker-notebook-instances/)；[10月15日公告](https://aws.amazon.com/about-aws/whats-new/2026/10/sagemaker-studio-new-sign-in-options/)描述验证客户默认GPU访问，但不能据此断言本账户已适用。Luna只读查询Ohio实际配额时页面导航及frame读取超时，按时限停止，当前值为unknown、不是0。[未读到的准确记录](../reviews/2026-10-27-sagemaker-quota-unknown.json)。本轮未创建SageMaker/其他资源、未下载模型；其他区域Spot/P尚未补查，不能将Ohio的0外推。

> **19:51只读补查：** Ohio的G/VT Spot及按需P配额均为0，[证据](../reviews/2026-10-27-ohio-spot-p-quotas.json)。该结论不外推其他区域；没有新增创建或重新建立CLI连接。当前已核实按需路径需等待Ohio容量恢复，未承诺到期前可用。模型下载继续暂停。

> **2026-10-27 19:47本轮最终：** 全20个启用区域G/VT按需配额仅Ohio8、其余19区0；本轮新L40S实验d在双保护实际验证/备用实际等待后，auto+2a/2b/2c四次真实请求全部容量不足，无实例ID。所有实验资源终态已核实不存在，官方CLI退出/缓存0；GPU/机上预检/模型部署/视频均0，模型下载保持暂停。[本轮实际结果与完整证据](../reviews/2026-10-27-l40s-d-instance-result.md)。下方“正在部署/登录/创建”均为历史，不得当作当前状态。

> **2026-10-27 19:20真实核查：** Owner再次授权继续后，Luna/high在原空间恢复官方临时CLI连接，未用剪贴板、未输出验证码。已逐一读取账户全部20个启用区域的On-Demand G/VT配额：仅Ohio us-east-2为8，其余19区为0。[完整区域证据](../reviews/2026-10-27-all-enabled-gpu-quotas.json)。Ohio用量/实例0，g6e.2xlarge现价2.24208美元/小时，赠金估算余额45.31美元；两个机型的offerings仅说明区域提供，不说明容量。本轮GPU创建仍0，正在重新核实费用和双保护门槛，模型下载保持暂停。税务注册API未找到记录，不能视为免税证明。下方登录硬停段落已成为历史，不再是当前阻塞。

> **本轮恢复后的最新状态：** Owner明确“继续解决实例”后，Luna/high成功接回同一个空间，准备l40s-d；在官方临时登录验证码步骤再次收到新的控制权硬停止。未完成CLI登录、未刷新区域配额、AWS API调用0、创建0；模型下载保持暂停。临时登录进程及本轮授权文件已收尾。仅凭现有日志无法判断中断发生于Copy按钮还是后续读取动作，不能断言是用户点击或AWS问题。新目录误复制的9份旧模板输出、intent和费用快照已隔离移除，未用作本轮有效证明；后续仅复用源码，所有保护/赠金须重新实读。当前浏览器中的官方页面用途是临时连接授权，非实例创建或付款。

> **2026-10-27 17:40本轮停止点：** 明确指定gpt-6-luna/high的唯一AWS操作者，在原Ego空间2恢复临时登录时收到“Control of this task space is with the user; browser commands are paused. Do not retry or take control back on your own.” 已停止浏览器操作、终止本轮登录等待并移除本轮授权URL；本轮AWS API操作0、GPU创建0，全区域配额补查尚未完成。模型下载保持暂停，用户东京页面未操作。等待Owner明确允许接回原空间；不将此前额度记录当作本轮新核查。

> **Owner最新指令：先解决实例，暂停模型下载、归档补传及部署。** 本机进程复核未见模型下载任务；G盘未完成文件保留，不恢复下载。只有取得真实实例ID并确认Running后，才进入既定10分钟GPU预检；预检通过且实际Stopped后，再处理模型与生成。Ego继续明确使用gpt-6-luna/high，由单一代理操作AWS，主负责人不并行写云资源。当前实例仍0，正在补查其他已启用区域的真实配额及同款实例路径；不把区域提供该机型当作有库存，不改变既有费用、停机、地域及机型授权边界。下方为此前执行证据。

> **2026-10-27 16:46当前：按用户要求，本轮Ego明确交给gpt-6-luna/high独立上下文子代理，后续云端协调也由同一Luna独占，主负责人停止AWS写入。** 新L40S实验c再做1次真实自动准入，仍InsufficientInstanceCapacity，GPU/模型部署/视频均0；已核查所有资源删除及CLI退出/缓存0。[本轮执行与模型指定记录](../reviews/2026-10-27-l40s-retry-luna.md)、[真实请求](../reviews/2026-10-27-l40s-retry-admission.json)、[清理](../reviews/2026-10-27-l40s-retry-cleanup.json)。另更正G盘权重下载已中断、约15.34GB/68.78GB、完整校验0，早前“后台继续”说法不准确。当前优先GPU实际Running，再处理模型。下方为历史。

> **2026-10-27 15:44当前：用户已同意L40S，并要求先开出实例再处理模型。g6e.2xlarge本轮4次真实请求（自动、2a、2b、2c）均InsufficientInstanceCapacity，另外2次截止拦截未提交；GPU/预检/模型部署/视频均0。三个L40S实验栈已删除并逐项核查全无残留，CLI已logout/缓存0。** [L40S实际进度](../reviews/2026-10-27-l40s-admission-status.md)、[真实请求](../reviews/2026-10-27-l40s-admission-result.json)、[清理证据](../reviews/2026-10-27-l40s-cleanup-verification.json)。七个其他常用区域G/VT额度实读均0，Ohio仍8核；不提额、不升级、不联系客服。下一阶段先以真实实例ID及Running为门槛，再部署模型；已准备的本地白名单不是实云成功。下面记录均为历史。

> **14:01收尾补充：官方临时CLI已logout、缓存0，浏览器登录未退出；G盘11.14/68.78GB、校验0份，后台下载继续。L40S候选待用户明确选择，未改机型。** [认证退出证据](../reviews/2026-10-27-wan-ohio-auth-cleanup-after-capacity.json)。

> **2026-10-27 13:58当前：g7e.2xlarge三个Ohio可用区＋自动选择共4次真实准入均InsufficientInstanceCapacity；配额仍8核，不是额度0。实际GPU/预检/视频均0。主已取消备用，删除3个实验栈并逐项核查IAM、Lambda、规则、日志、SSM、安全组、S3及实例/卷/ENI/EIP均不存在。G盘权重继续下载、完整校验尚未完成。** [实际准入](../reviews/2026-10-27-wan-ohio-capacity-result.json)、[清理证据](../reviews/2026-10-27-wan-ohio-cleanup-verification.json)、[当前报告](../reviews/2026-10-27-wan-ohio-preparation.md)。同FP16/同规格的g6e L40S方案仅已分析，未改机型或创建，等用户明确选择：[备选方案](../reviews/2026-10-27-wan-l40s-proposal.md)。下方记录为历史，不可把已删除的保护当作仍部署。

> **2026-10-27 13:36恢复：用户已确认AWS登录及G盘Wan归档。五笔赠金完整服务范围全部核实，估算余额45.84美元；Ohio配额8核、实例0、免费官方DLAMI/网络已实读。主/备用及私有资产三个栈已部署，实际无目标执行和IAM正反例通过；正在确认未来固定截止的备用真实等待，GPU仍未创建、视频0。G盘权重下载进行中、0份完整校验；本地Linux导出及每次开机固定关机已新增并测试。** [当前进展](../reviews/2026-10-27-wan-ohio-preparation.md)、[脱敏证据](../reviews/2026-10-27-wan-ohio-resumed-checkpoint.json)、[完整预算](../reviews/2026-10-27-wan-ohio-budget.json)。原D盘H3及两个ZIP保留。下面12:49及更早记录仅供历史追溯。主负责人唯一操作AWS，不延长运行中截止；未知创建先按请求键核对。Singapore更新连接超时已核对旧实际参数，再用原截止与原请求键补交。

> **2026-10-27 12:49当前：用户要求继续Ohio EC2＋Wan候选。已实读G/VT8核、实例0、g7e.2xlarge 64GiB/96GiB、Linux USD3.36312/h、PAID/ACTIVE及赠金估算USD46.49；实际库存/完整费用尚未通过。逐笔赠金与AMI复查期间AWS要求重新登录，Ego同一专用空间已交给用户；另待确认是否将放不下D盘的新Wan包改存G盘。新云资源0、真实GPU/视频0。Wan双保护、工作流、Bridge/Grok前端本地适配已完成，131 Python+14前端契约/类型/构建通过，均不是实云成功。** 先读[Wan当前准备与阻塞](../reviews/2026-10-27-wan-ohio-preparation.md)；不得重开已清理的东京gr6方案。

> **2026-10-27 00:02最终：gr6唯一创建也被实际上限0拒绝，CloudTrail排除错区/错服务/错套餐；GPU、真实预检、视频均0。本次桌面0、目录不存在、三个临时栈及私有S3不存在、激活/管理节点0、备用Cancelled，官方临时连接已退出且缓存0。停止云端创建；不提额、不升级、不重试、不联系支持。D盘模型/环境及原ZIP保留、main未合并。** [最终证据](../reviews/2026-10-26-gr6-final-absence.json)、[本轮完整记录](../reviews/2026-10-26-gr6-remaining-gpu-audit.md)。以下“正在清理”均为历史状态。

> **2026-10-26 23:54实际结果：唯一一次东京gr6创建也返回实际上限0；请求号88083dc2-77ad-4c6a-bab7-0682564eeb48。CloudTrail、重新读取包及创建后库存已排除错误区域/服务/套餐，配额接口仍显示1，内部原因未知。GPU/真实预检/视频均0，停止云端创建，不提额、不升级、不重试、不联系支持。私有S3及接入角色已确认不存在，目录注销且正在删除，保护仍保留到目录消失；最终清理记录待补。** 优先读[拒绝与清理记录](../reviews/2026-10-26-gr6-remaining-gpu-audit.md)。下方“准备创建”的内容为历史状态。

> **2026-10-26 23:35最新：浏览器及临时CLI登录已恢复，按用户给定东京EC2入口进入；本次目录d-95679b0534实读Active，GPU仍未请求创建。GPU为0时重设首次启动前保护：北京时间27日01:08:57停止、01:13:57终止及清理。两个栈UPDATE_COMPLETE；旧新加坡备用已Cancelled，新备用88953ad2-72b0-4672-a721-202610260005实读aws:sleep等待新截止。私有SSM引导本地测试通过，远端节点及CUDA仍未验证，不得宣称已部署。** 下方23:29/23:34时刻与Creating/认证阻塞为历史。继续前先读[gr6最新记录](../reviews/2026-10-26-gr6-remaining-gpu-audit.md)。

> **2026-10-26 21:25后续：用户同意继续核查东京gr6与剩余GameLift位置。东京gr6.4xlarge页面及两个配额接口均为1，确切Windows包已找到；实际准入未验证。GameLift返回的42项GPU配额全部0。新主备保护已部署、读通并通过标签权限正反例；新加坡备用已实际等待固定时刻。专用目录Creating，尚未请求新桌面；不要将旧Stop-only保护或历史额度当本轮已开机。** 先读[gr6最新核查与受控验证安排](../reviews/2026-10-26-gr6-remaining-gpu-audit.md)。

> **2026-10-26 GameLift 最新核验：同账户、同东京配额 L-9F99CEA2，当前控制台和 API 均为 0，非全局配额。未启动 GPU、未执行真实 H3 预检、未生成视频。** 历史控制台确实记录过 Applied=1，该原文保留；变化原因未查明，不能继续作为可开机依据。47.4GB 原始模型及环境包已全部保存至 D:/AniFlow-H3-Archive-20261026，9 个源文件两次完整哈希核验通过；本轮流组、应用、私有 S3 桶及四个临时栈均已确认不存在，本次 CLI 登录缓存也已清除。辅助费用、抵扣和税仍待最终入账。先读[当前执行与阻塞证据](../reviews/2026-10-26-gamelift-execution.md)。下列“配额1候选、尚未执行”段落为历史状态。

> **2026-10-26 配额对账及新方案：已通过CloudTrail排除错账户、东京区域和G6服务包；WorkSpaces显示1却执行0的内部原因仍未查明。新读到东京GameLift Streams Gen6n独立GPU配额1，作为保持原H3的新候选，尚未创建或实测。** 先读[配额对账与视频方案](../reviews/2026-10-26-quota-reconciliation-and-video-options.md)。用户本轮要求先分析方案；不得把候选或Applied=1当作已批准创建，连接方式/断网最多一小时的差异须说明，新保护和Bridge适配尚未实现。

> **2026-10-26 最新执行结果：东京 WorkSpaces G6 单次创建被 AWS 实际上限 0 拒绝，GPU 与真实视频均为 0；已知本轮目录、保护栈、激活及模板对象清理已确认。** 控制台 Applied=1 与实际创建限制矛盾，原因未知；不重试、不提额、不联系支持、不升级计划。最新预算为赠金另计、抵扣后自付最多 USD1，最终辅助费用与税仍待结算。请先读[真实执行记录](../reviews/2026-10-26-workspaces-live-execution.md)与[创建拒绝证据](../reviews/2026-10-26-workspaces-create-rejection.md)。以下原交接保留为历史，不代表当前资源或登录状态。

## 目标与边界

用户已授权：先核实本人AWS赠金能否支付东京g6e.2xlarge，再在资格与实际费用明确时创建单台受控实验GPU，用安全连接部署MiniMax H3图生视频，最后接入AniFlow Grok Studio前端，并能把真实MP4保存到本人Windows磁盘。

**Chat当前事实**：已连接浏览器读取失败：Browser access requires originating browser context。不能把这当作已经核验AWS。用户报告2026-10-13余额约USD91.14，赠金10月30日到期；这只是历史数值，Work必须重新读取实时余额/有效期及Eligible Services。Chat无法替用户切换为指定的GPT-6.1 Sol High，须用户从工作模式入口选择。

## Work进入后子任务建议

1. **AWS资格只读审计 Agent**：使用用户本人已登录、已授权的Ego浏览器，核对AWS账户当前Free/Paid Plan、赠金实际余额、截止时刻/时区、Eligible Services是否明确含Amazon EC2，是否存在未支付费用及账户限制；记录截图或脱敏出处。禁止暴露Account ID/密钥。发现不适用、需要信用卡直接付款或Free→Paid转换，停止创建并请求明确决策，不擅自升级付款计划。
2. **东京配额与价格 Agent**：仅看 ap-northeast-1；核对g6e.2xlarge、On-Demand G/VT vCPU配额至少8、实例可用性及实时区内价格。确认AMI、200GB gp3 EBS、公共IPv4、数据出站、SSM/CloudWatch/EventBridge潜在费用是否适用赠金。不得引用过时单价当最终报价。
3. **H3许可与ComfyUI Agent**：核对模型官方发布/下载源、Applicable Territory、输出权利和商业使用边界；优先Comfy-Org官方 H3 FL2VA pruned int8，最先验证一张本机图片 → 5秒、9:16、768p短边；若许可证地域不符，不下载权重也不运行。ComfyUI官方工作流权重、模型版本、VRAM/RAM最低要求记录。
4. **AniFlow工程 Agent**：以Draft PR #7的Grok Studio为基线，保留原始两个ZIP与PR #2既有Windows原系统；先Mock端到端与新增的AWS预检面板；设计Provider接口、SQLite任务存档、幂等任务恢复、本机MP4分块下载/SHA256/ffprobe，隔离Mock与Real；真实回传之前不在UI显示“成功”。发布证据进入GitHub隔离分支，不直接改main。

## 创建开机门槛（先核实，失败任一项就停止）

- 本人AWS赠金仍有效，明确适用于目标EC2实例相关费用；如果存储/公网IP/流量单独自费需有明确总额。
- 账户允许使用该GPU，东京 G/VT 8vCPU配额及实时实例容量均足够。
- H3 license允许AWS所在及用户实际使用地域，商业推广前另核正式输出授权。
- 记录按需计费单价、费用预计，并选仅**一台**g6e.2xlarge；严禁无界扩容。
- 创建前落实**主动定时停机+失联后的第二独立停止手段**，而不是依靠AWS Budget告警作为硬上限。初次GPU实验建议控制在最多4小时、首轮总费用软预算USD20以内；如果无法保证避免超出本人愿意承担的额外自付，须暂停并报告。
- 禁止在公网开放8188 ComfyUI、22 SSH、8765/8767 Bridge；优先IAM最小权限 + SSM Session Manager隧道，用户本机AWS CLI使用已有会话，不导出AK/SK。
- 若发现Free Plan阻止G6e，严禁擅自升级为Paid。该动作可能开始扣取信用卡费用。

## 真实部署与验证步骤

预检通过并获得平台必要操作权限后：选择支持SSM的Ubuntu AMI、受控安全组、gp3 EBS持久模型/成果，开机后确认nvidia-smi GPU=48GB L40S，部署锁定版本ComfyUI/H3 FL2VA量化权重及官方工作流，绑定ComfyUI至实例本地127.0.0.1:8188，通过SSM隧道从Windows代理连接。尽量提前准备可复用的无GPU安装脚本减少GPU空转。

首次真实测试只创建**一条**5秒雪所长合法首帧生成任务，记录 ComfyUI prompt_id、推理耗时、显存峰值、输出MP4校验、尺寸/秒数、真实消耗。通过本机AniFlow Bridge下载到Windows用户指定目录并核sha256与ffprobe。不能仅在云端截图代替本地落盘。不通过则立即释放GPU运算，留下失败证据。

生成任务状态要能在用户Windows断网后读恢复已知prompt_id，不再POST；云端停止与取消真实任务是不同语义。用户暂停任务、断网、预算阈值、模型加载失败、磁盘故障需可追踪；停机后EBS/IP仍可能收费，按需求删除残留资源。

## 执行证据与汇报

- 只展示账户审计结果/截图出处、GPU资源信息但不要完整敏感账户标识、东京价格、花费、运行时长、停机安排、ComfyUI版本/哈希、真实MP4下载结果与本机实际路径。
- 所有代码和审计写入 wpuu/AniFlow 原有 PR #7（或明确独立分支），避免与PR #2/正式main误合并。保留每次任务时间、模型与提交SHA。
- 发生浏览器控制丢失、AWS账户未登录、配额0、信用额度不合格、许可证不明确、费用超过门槛时：不创建资源；把已经完成的前端工作与缺失事项准确说明。
- 不能将模拟蓝色视频称为H3真实产物，也不能声称没有实际AWS账单只因没有API调用。
