# 东京WorkSpaces执行进度：赠金另计，自付最多USD1

2026-10-26，Asia/Shanghai。用户已明确允许消耗赠金，限制为抵扣后自付不超过USD1，不升级计划。此前按抵扣前总服务费USD1作出的预算否决已被澄清，不再据此停止。本轮继续原H3、原视频质量、真实5秒、Windows本地下载目标。

## 已完成与证据

- 主代理通过授权Ego读取、子代理只查公开资料或修改分配的本地文件；没有多个代理操作AWS资源。
- 未提交的手动创建向导已实际选择东京 `Graphics.g6.4xlarge with Windows (Server 2022 based)`，公开bundle ID `wsb-9zg6r5j55`。显示DCV/WSP、16vCPU、64GiB主存、24GiB显存、根卷200GB/用户卷150GB及`GraphicsG6Drivers`，运行模式AUTO_STOP。未显示驱动版本，不能据此说CUDA13兼容已通过。
- 东京已注册WorkSpaces目录为0；本轮另读到可注册的未注册Directory Service目录也为0。手动向导没有可用目录。官方Quick Setup仍有新建SimpleAD例外，但默认AlwaysOn有高额月费风险，未提交；Custom/BYOL并不是本次Windows许可包含的等价免AD方案。
- 2026-10-25末次读取赠金：结算剩余USD91.14，预计剩余USD49.31，五笔Active；不是2026-10-26实时余额。既有五笔适用产品已匹配WorkSpaces、DirectoryService、SSM、VPC等。Free/Paid没有找到明确文字字段，未进行计划转换。
- [双停止模板](../../infra/workspaces/guard-template.yaml)与[审阅](2026-10-26-workspaces-guard-review.md)已完成。东京Primary为每分钟Scheduler→Lambda；新加坡Backup为独立SSM Automation与角色，须先启动并确认等待固定截止。模板cfn-lint两区域无诊断，嵌入Python语法通过。**尚未部署；静态通过不代表停机已落实。**
- 本机Bridge已最小兼容WorkSpaces gate，服务赠金与配额核验不再沿用EC2字段；账户服务资格、未升级计划分别核验。赠金实验预算至多USD20，自付上限USD0–1；东京、私有SSM、主/备停止、最长4小时、workflow SHA及真实CUDA仍必需。默认REAL禁用，未生成可通过真实gate。相关REAL/Mock契约共41项通过，ruff及差异检查通过。所有测试用模拟接口，**不是H3真实推理**。[Bridge运行说明](../runbooks/2026-10-25-local-real-h3-bridge.md)。
- 本机没有既有AWS CLI/SSM插件。已从官方包在工作区解包，版本检查分别为AWS CLI2.38.5、插件1.2.896.0，下载包/插件Amazon Authenticode签名有效；未运行全局安装、未修改全局PATH。MSI解包运行已通过本机版本检查，不称AWS正式认证的portable安装方式。官方支持`aws login --remote`以控制台身份获取短期会话，不需长期AK；本轮短期登录未完成，未创建密钥，也未把认证URL/授权码/缓存上传Git。

## 费用口径与剩余门槛

本次Personal Windows许可包含报价不另加Pools的USD4.19用户费。目录按常规两台Managed AD Standard合计USD0.146/h估算，不自动假设一次性30天试用资格。公网IPv4为USD0.005/IP/h。SSM取消Advanced Tier的日期应为2026-06-30；2026-09-30起hybrid会话USD0.05/session、RunCommand USD0.002/次，无每节点注册小时费。

10月25日按剩余7/31估算基础费USD6.774，桌面2h USD9.66、AD4h USD0.584、IPv4四小时USD0.02、4次会话和50次命令USD0.30，示例约USD17.338；未计实际网络、日志及可能税费。10月26日若按6/31估算，示例约USD16.370，仍不是最终账单。GPU不足一小时按一小时；停止后基础费仍在。原两小时服务费目标可在赠金预算20以内留部分余量，但必须以当日余额、实际收费路径、清理及税核验为准。

固定停止建议在首次两小时窗口内提前触发，主约1h40、备约1h45；四小时是最长限制，不默认跑满。主/备都依赖东京停止接口，必须确认STOPPED，不能用Windows关机、客户端断开、API200或AutoStop闲置设置替代。先下载并校验MP4，再终止本次桌面并清理专建目录/网络，避免赠金到期后费用。模板只停止、不终止桌面，清理流程仍须落实，不能把它当费用自动归零。

首次SSM注册需要初始化入口：G6的DCV支持WebAccess，创建接口没有UserData，不能按EC2直接注入SSM。合理路径是启用目录WebAccess后首次浏览器桌面初始化，再注册SSM hybrid并验证在线，之后部署/连接走SSM私有通道。实际驱动、首次管理员登录、SSM节点及隧道均未验证。

## 当前阻塞与下一步

2026-10-26恢复时，Ego从0.6.0.22更新至0.6.1.11，原任务空间11返回`task space not found`。未接管其他用户自有空间，先请求重建许可。用户已明确允许后，建立新的AWS专用工作区2；目标赠金页面跳转AWS Sign-In，登录会话失效，尚未刷新当日余额。已将登录页handOff给用户；密码与MFA由用户在浏览器完成，不在聊天收集。认证是当前实际阻塞，重建许可已解除。

等待期间完成本地修改与审计归档。恢复后依次：刷新赠金及账户资格；完成真实驱动/初始化方案与完整费用核对；部署并验收两套保护；仅在全部门槛通过后创建单台AutoStop GPU、先诊断驱动，不兼容立即停止；再运行唯一真实任务、记录显存/耗时/费用、下载校验及清理。不得把未验证字段标true。

**本轮新增云资源0，计划升级0，新增实验服务费用0，真实H3视频0，本地真实生成MP4为0。目标尚未完成。** 本轮未改两个原始ZIP、未合并main、未联系AWS支持、未申请提额。

官方资料：[WorkSpaces计费](https://aws.amazon.com/workspaces/desktop-as-a-service/pricing/)、[FAQ](https://aws.amazon.com/workspaces-family/workspaces/faqs/)、[QuickSetup](https://docs.aws.amazon.com/workspaces/latest/adminguide/managing-wsp-personal.html)、[目录价格](https://aws.amazon.com/directoryservice/pricing/)、[VPC价格](https://aws.amazon.com/vpc/pricing/)、[SSM价格](https://aws.amazon.com/systems-manager/pricing/)、[DCV WebAccess](https://docs.aws.amazon.com/workspaces/latest/userguide/amazon-workspaces-web-access.html)、[Hybrid安装](https://docs.aws.amazon.com/systems-manager/latest/userguide/hybrid-multicloud-ssm-agent-install-windows.html)、[CLI登录](https://docs.aws.amazon.com/cli/latest/reference/login/)、[配置缓存](https://docs.aws.amazon.com/sdkref/latest/guide/feature-login-credentials.html)。
