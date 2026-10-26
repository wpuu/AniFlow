# 东京 gr6 与剩余 GPU 路径核查

2026-10-26，Asia/Shanghai。用户同意继续核查东京 gr6 与 H3 许可地域内其他 GameLift 位置。主负责人是唯一 AWS 操作者；代码审阅代理仅只读本地文件。

**东京 Graphics.gr6.4xlarge 单次创建也被 AWS 实际上限 0 拒绝；复查配额接口仍为 1。CloudTrail 证实本次准确的东京区域、WorkSpaces 服务及 gr6 公共捆绑包，未创建 GPU、未完成真实预检、未生成视频。** 没有提额、升级、重试或联系支持。内部配额矛盾的原因仍未知，不能将配额页面的 1 当可用容量。

## 本次实读

- 浏览器现有登录与临时官方 CLI 身份私下比较，同账户；不输出账号编号或凭证。账户 PAID / ACTIVE，没有转换计划。预计剩余赠金 USD47.25，五笔 Active、到期显示 2026/10/30；页面注明预计数约每 24 小时更新，精确到期时刻未知。[账户及价格快照](2026-10-26-gr6-costs-and-state.json)、[赠金摘要](2026-10-26-gr6-credit-summary.json)。
- 东京 gr6.4xlarge 代码 L-EF6817EC，当前应用值 1、默认 0、使用 0；gr6.8xlarge 独立额度也为 1；总 WorkSpaces 为 1，不能将不同型号额度合并。[页面原文](2026-10-26-gr6-console.txt)、[详情接口](2026-10-26-gr6-exact-quota.json)。
- 东京官方捆绑包 `wsb-5mpqp50vv`：GRAPHICS_GR6_4XLARGE，Windows Server 2022 / WSP，16vCPU、128GiB RAM、单 L4 24GiB显存、根卷250GB/用户卷200GB；没有找到该型 Linux 公共包。四个原 H3 模型可复用，D盘 Linux runtime.tar 不能当成 Windows 可执行环境。[全部列表证据](2026-10-26-gr6-eligibility.json)。
- GameLift 当前应用额度列表包含 42 项 GPU 配额，涉及 Gen4n/Gen5n/Gen6n/Gen6e 和各支持位置，**全部为 0**；控制台两页也未见非零。此结论限该服务当前已返回项目，不等于 AWS 全部服务全球 GPU 都为 0。
- 东京 WorkSpaces 实例 0、已注册目录 0；另用 Directory Service 接口确认目录 0。SSM 管理节点 0，旧 activation-tier 设置值 standard；未修改设置。
- WorkSpaces CreateWorkspaces 请求模型和[官方接口](https://docs.aws.amazon.com/workspaces/latest/api/API_CreateWorkspaces.html)没有 DryRun。DescribeAccount 只描述 BYOL，不提供可替代真实创建的 GPU 准入确认。因此仍可能在单次真实 gr6 创建时遇到服务端上限拒绝；不伪造“只读验证创建成功”。

## 费用与赠金

官方东京当前价格数据发布时间 2026-10-16：Windows 许可包含、Basic utilities、AutoStop 的 gr6.4xlarge 为 **USD5.40/小时＋USD35/月基础费**。小时 SKU `2DYRCHY4BHVXA56R`，基础费 `VP3XC6QH6W9B9ZQK`；未采用 BYOL 或 WorkSpaces Core 的便宜报价。根卷250GB、用户卷200GB保持包默认，不增盘。[官方价格数据](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonWorkSpaces/current/ap-northeast-1/index.json)。

首月基础费按比例计算，不足一小时按一小时计；停止不消除基础费，需要终止桌面避免后续月份续费。[AWS FAQ](https://aws.amazon.com/workspaces-family/workspaces/faqs/)。按10月26日剩余6/31日估算，基础费约 USD6.77；保守按7/31则 USD7.90。

- 一次不超过10分钟 GPU 预检，若发生首次计费运行：小时费 USD5.40，加基础费约 USD6.77～7.90。
- 若预检后停止并在新保护下恢复，两个分别不足一小时的运行段也保守按两小时计费 USD10.80。加新 Microsoft AD Standard 最多4小时、沿用常规两控制器合计USD0.146/h的估算，桌面及目录约 **USD18.16～19.29**；这不是实测账单或完整全包承诺。
- SSM、保护执行、日志、少量网络和请求另计，全部纳入首轮约USD20服务费目标及抵扣后自付≤USD1条件。目录及保护部署前继续确认；不创建 NAT、收费 VPC 端点、Office 包或公共 Comfy/SSH 服务。

本次逐份重新打开五笔赠金完整服务列表，均列有 WorkSpaces、Directory Service、Systems Manager、Lambda、CloudWatch Events、S3、Data Transfer、VPC。[逐笔资格结果](2026-10-26-gr6-credit-eligibility.json)。不代表抵扣已入账；预估余额不是实时硬消费上限，最终抵扣及税仍待结算。本次账单页显示当期总计税费 USD0.00，不能将其当未来永久免税保证。

**SSM旧费率已纠正：** 官方定价说明2026-06-30取消 Advanced Instances Tier，2026-09-30起混合节点 Session Manager 每会话USD0.05、Run Command 每调用USD0.002。不得沿用旧高级节点小时价，也不因旧 standard 设置值就擅自开启付费层级。[官方SSM价格](https://aws.amazon.com/systems-manager/pricing/)。

## 本次受控验证安排

1. 在任何专用目录或桌面前，先部署并核验东京每分钟主保护和新加坡独立 SSM Automation 备用；两者只处理新唯一 ExperimentId 标签的东京实验资源。主路径按固定时刻停止，再于清理截止终止桌面并清理本次目录；备用不调用主 Lambda，独立执行终止与目录清理。退出/断网不影响云端保护。两个路径可能共享区域 API 依赖，不能称绝对无故障保证。
2. 新保护补上旧 Stop-only 模板缺少的桌面终止及目录清理，避免失联后目录和后续月份收费。原始模型/环境已在 D盘校验保存；本轮临时桌面及目录均可清理。旧模板和历史审计不覆盖。
3. 两个模板 AWS ValidateTemplate 均通过；新增8项财务保护相关契约测试与 Ruff 通过。只读审阅发现的网络超时重试问题已修正。这些测试尚不证明真实桌面停止。
4. 只提交一次单台 `wsb-5mpqp50vv` 创建请求，原子带实验标签，AUTO_STOP；若上限0、错误或准入不明，立即进入清理，不重试、不提额、不升级、不联系支持，不上传模型。
5. 创建成功才进入固定10分钟真实 GPU/驱动/CUDA/私有SSM预检；未通过清理。通过后只有在实际 STOPPED、重新生效的主备保护及剩余预算都核实后，才可恢复并运行一条原参数5秒H3，自动保存到本机并校验。未知提交不自动重发；不将本地GPU或Mock当成云端成功。

## 本轮实际执行进度

- 东京 `aniflow-h3-gr6-primary-20261026`、新加坡 `aniflow-h3-gr6-backup-20261026` 均已 CREATE_COMPLETE，后续固定时刻更新完成。新实验标签为 `aniflow-h3-gr6-20261026-b`。
- [保护验证](2026-10-26-gr6-guard-proof.json)：东京主路径真实执行时读到本次桌面和目录均为0；两个独立角色共8组写权限检查均为本次标签允许、其他标签拒绝。没有把“没有目标”当作真实停机成功。
- 新加坡备用验证执行 `7db548da-4c66-4559-976b-202610260002` 四步全部 Success。新的备用执行 `88953ad2-72b0-4672-a721-202610260003` 实际处于 InProgress，aws:sleep 的固定时间已读回；主路径真实返回 stop_due=false、cleanup_due=false。
- 初始固定截止为北京时间 **2026-10-26 23:29:13 停止、23:34:13 终止及目录清理**。目录及启动准备也占用这一窗口；不会在GPU运行中延后截止。GPU AVAILABLE后须将预检保护进一步缩短到10分钟停止/15分钟清理。
- 专用目录首次 CreateMicrosoftAD 因描述含不支持的分号而返回确定的 ValidationException，未创建目录；第一次修正执行又在提交前的只读复查遇到连接超时，未发出创建。之后确认目录0，用官方标准区域端点与单次提交完成创建：[目录回执](2026-10-26-gr6-directory-create.json)，目录 d-95679b0534 于北京时间21:58:22请求创建，21:59:14读到Creating，原子实验标签已确认。未重复提交未知结果，尚未请求创建gr6桌面，没有上传模型。

当前真实驱动、CUDA、GPU显存实测、H3耗时、真实MP4和最终费用均未知。两个原始ZIP保持不变，PR7保持Draft，不合并main。上述本轮新保护栈仍在运行，不能沿用上一轮GameLift“已清理”来声称本轮也已清理。

本机Bridge已补充精确gr6目标校验和128GiB主存展示；gr6的阻塞快照不会借用本机其他ComfyUI GPU，snapshot_only仍不能授权生成。真实本地HTTP预检返回目标gr6、128GiB、GPU未连接、launch_allowed=false、AWS查询0。相关82项Python接口/保护契约及Ruff通过，均非H3真实推理。未更改Grok视觉或降低原工作流质量。

## 认证阻塞历史（已恢复）

目录最后一次成功读取为北京时间22:28:58的Creating。随后本机官方CLI短期凭证返回ExpiredTokenException，Ego原专用空间9也已不存在。按用户此前允许重建的授权恢复专用空间10，AWS重新要求邮箱登录；已将页面控制交给用户，等待本人完成登录及可能MFA。没有读取/索取密码或验证码，没有创建gr6桌面、GPU或上传模型。云端两个服务角色及固定停止/清理执行不依赖过期的本机登录，仍按23:29:13/23:34:13执行；本轮保护栈仍存在，不能宣称本轮已清理。

为Windows候选准备的官方Portable运行包已在本机D盘独立目录完成字节数和完整SHA256核对：[归档清单](2026-10-26-gr6-windows-runtime-package.json)。2,018,444,114字节，仍为ComfyUI v0.42.1固定来源，原47.4GB Linux/模型归档未改；未安装到GPU、未验证CUDA、没有真实成片。登录恢复后先读回当前目录及保护状态，只有固定保护窗口仍足够才继续，不重复提交未知结果。

## 2026-10-26 23:35 更新

用户完成浏览器登录并明确授权继续空间10。已从用户提供的东京 EC2 实例地址进入；EC2 与 WorkSpaces 是不同服务，不以 EC2 列表推断 WorkSpaces 准入。官方临时CLI登录已恢复；15:28:31 UTC 实读本次目录 d-95679b0534 为 Active，实验标签匹配，GPU尚未请求创建。

首次GPU启动前、桌面数量仍为0时，重新设置固定停止为 **2026-10-27 01:08:57 北京时间**，终止及目录清理为 **01:13:57**。两个栈更新完成、参数读回一致，东京主路径真实调用返回未到截止且匹配桌面0。旧新加坡备用 88953ad2-72b0-4672-a721-202610260003 已确认 Cancelled；新备用 88953ad2-72b0-4672-a721-202610260005 已实际读回 InProgress，WaitUntilCleanup 的 aws:sleep 正在等待 17:13:57 UTC。这是GPU为0时的首次启动准备，没有延长运行中GPU的截止。

CloudShell实际提示“无法创建环境”“正在验证您的账户”，没有执行命令。此事实只说明CloudShell受限，不能推断gr6已被拒绝；未联系AWS支持。当前新加坡接口出现过TLS超时，未将网络错误当配额0，未重发任何GPU创建。

只读代理依据[官方协议说明](https://docs.aws.amazon.com/workspaces/latest/adminguide/amazon-workspaces-networking.html)确认Windows Server2022的DCV支持Web Access，WSP为DCV旧名。私有SSM引导脚本已补齐并通过8项本地PowerShell安全门槛测试；没有安装/注册真实节点，尚不能声称远端Online、私有隧道或CUDA通过。实际GPU显存、推理耗时和MP4仍全部未知。

目录注册请求已接受，目录用户已建立并独立读取Enabled；本次目录创建属性已实读允许本地管理员、互联网连接、Web Access，关闭Maintenance。[目录Active](2026-10-26-gr6-directory-active.json)、[注册回执](2026-10-26-gr6-directory-registration.json)、[配置读回](2026-10-26-gr6-directory-config.json)、[首次启动前重设](2026-10-26-gr6-prelaunch-rearm.json)、[新备用](2026-10-26-gr6-prelaunch-backup.json)、[备用等待实读](2026-10-26-gr6-future-backup-status.json)。这些仅是准备完成的证据，仍没有请求创建GPU。

## 23:54 实际拒绝及清理进度

北京时间23:49:01，唯一一次 CreateWorkspaces 请求返回 ResourceLimitExceededException，原文为 "You cannot create more than 0 number of Graphics.gr6.4xlarge WorkSpaces in this region." 请求号 88083dc2-77ad-4c6a-bab7-0682564eeb48。[单次请求及拒绝](2026-10-26-gr6-create-rejection.json)。请求前已确认两个保护、最新PAID状态及赠金估算47.25美元、私有加密S3、单节点激活、已注册目录及Enabled用户；没有以网络未知状态为由重发创建。

随后实际读取东京桌面仍0、应用配额1，重新读取相同 wsb-5mpqp50vv 确为 GRAPHICS_GR6_4XLARGE。[拒绝后复查](2026-10-26-gr6-create-reconciliation.json)。CloudTrail 找到唯一相同请求号，服务 workspaces.amazonaws.com、区域 ap-northeast-1、捆绑包完全一致，并记录相同上限0错误。[CloudTrail脱敏证据](2026-10-26-gr6-create-cloudtrail.json)。这排除了本次错误区域、错误服务或错选G6包；不能据此确定AWS内部为何显示1但执行0。

本轮私有S3桶及Hybrid角色已随专用资产栈删除，S3唯一引导文件已删除，multipart为0，激活已撤销、管理节点0。目录已从WorkSpaces注销，Directory Service实际Stage=Deleting；主备保护继续保留直到确认目录不存在，不能提前称全部清理。[资产清理](2026-10-26-gr6-private-assets-cleanup.json)、[当前清理实读](2026-10-26-gr6-cleanup-inventory.json)。目录、保护及请求可能已有小额辅助费用，最终抵扣和税仍待账单；没有GPU实测费用或视频成功。

独立本地开发已完成Windows首次SSM引导、私有资产模板、单个已提交任务的只读历史轮询及MP4自动保存helper；本轮39项行为/权限测试与Ruff通过。helper验证唯一MP4、边界路径、真实ffprobe时长及尺寸、SHA256后依次上传视频和manifest；已确认阶段持久存档，网络未知PUT仅有限重试同一对象，不再提交Comfy任务。测试中的HTTP和视频探测使用替身，未发生真实远端保存。既有原参数工作流、Grok视觉和两个原ZIP未改。本机Bridge快照已反映实际准入失败，保持launch_allowed=false、GPU未连接、AWS写入0。

## 2026-10-27 00:02 最终清理

[最终实读](2026-10-26-gr6-final-absence.json)确认：东京桌面0、本次已注册目录不存在、本次Directory Service目录不存在；东京主保护、新加坡备用保护、东京私有资产三个栈均ABSENT；私有桶404、激活0、管理节点0，最后备用执行Cancelled。只有确认目录及桌面不存在后才取消备用及删除保护。下文或历史记录中的Creating/Deleting/保护运行状态均已被此结果取代。

[官方临时连接退出回执](2026-10-26-gr6-auth-cleanup.json)确认缓存文件0，精确删除本任务8个认证/目录密码/注册及接入私有文件；没有修改用户全局AWS配置或退出用户自己的浏览器AWS登录。Ego任务空间已结束，保留用户给定的东京EC2页，该页最终快照为“没有实例”。[用户指定入口原文](2026-10-26-gr6-ec2-user-entry.txt)。

[本机真实HTTP复查](2026-10-26-gr6-local-http-after-rejection.json)确认gr6/128GiB目标、实际配额及账户准入均失败、launch_allowed=false、GPU未连接、AWS读写0；不会让本机其他GPU冒充AWS成功。模型及环境保持D盘，未覆盖原ZIP、未合并main。

最终仍为真实视频0、真实GPU预检0、驱动/CUDA/显存/耗时未知。目录、保护和请求辅助费用及赠金抵扣/税需要等待实际账单，不把资源清理当费用已结算。在用户不提额、不升级、不降低画质、不联系支持的约束下，本次已核查的GPU路径受阻，停止继续云端创建。
