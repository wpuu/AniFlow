# 东京WorkSpaces执行进度：赠金另计，自付最多USD1

2026-10-26，Asia/Shanghai。用户已明确允许消耗赠金，限制为抵扣后自付不超过USD1，不升级计划。此前按抵扣前总服务费USD1作出的预算否决已被澄清；本轮实际因单次G6创建请求被区域上限0拒绝而停止云创建，已知本轮资源清理已确认。原H3、真实5秒及Windows本地下载目标尚未实现；最终费用未结算。[创建拒绝记录](2026-10-26-workspaces-create-rejection.md)。

## 已完成与证据

- 主代理通过授权Ego读取、子代理只查公开资料或修改分配的本地文件；没有多个代理操作AWS资源。
- 未提交的手动创建向导已实际选择东京 `Graphics.g6.4xlarge with Windows (Server 2022 based)`，公开bundle ID `wsb-9zg6r5j55`。显示DCV/WSP、16vCPU、64GiB主存、24GiB显存、根卷200GB/用户卷150GB及`GraphicsG6Drivers`，运行模式AUTO_STOP。未显示驱动版本，不能据此说CUDA13兼容已通过。
- 东京专建目录`d-95679b1f48`曾Active且已注册WorkSpaces，Internet已启用、AGA已禁用，Web Access已读回enabled；首次Web桌面登录未发生。现已取消注册后成功删除，重新加载后目录列表0、无旧banner；东京桌面列表也确认0。
- 2026-10-26登录恢复后刷新赠金：结算剩余USD91.14，预计剩余USD48.28，五笔Active，到期显示2026-10-30；显示余额存在更新延迟，精确到期时刻仍未确认。既有五笔适用产品已匹配WorkSpaces、DirectoryService、SSM、VPC等。Free/Paid没有找到明确文字字段，未进行计划转换。
- [双停止模板](../../infra/workspaces/guard-template.yaml)与[审阅](2026-10-26-workspaces-guard-review.md)已完成；两栈创建前均`UPDATE_COMPLETE`，主/备截止05:50/05:55 UTC（中国时间13:50/13:55），东京Primary 04:06:38 UTC真实扫描读到deadline_due=false、matched=0，但没有真实桌面停止证据。清理后两栈在deleted筛选均为`DELETE_COMPLETE`；旧备用`582f4e3c-d28e-419b-b276-9a7fef208212`与新备用`a1bbf66d-fa49-4ab2-8574-ae2e99566dc1`均已Cancelled。[执行明细](2026-10-26-workspaces-live-execution.md)。
- 04:08:27.650 UTC只提交一次单台G6 Create，返回`ResourceLimitExceededException`，表示本区域`Graphics.g6.4xlarge`最多0台；与此前控制台Applied=1矛盾，原因未确认。已停止创建，无重试、提额、客服或升级。证据为本机`work/aws-workspaces-execute-20261026/create-rejection.json`及[Git摘要](2026-10-26-workspaces-create-rejection.md)。
- 本机Bridge已最小兼容WorkSpaces gate，服务赠金与配额核验不再沿用EC2字段；账户服务资格、未升级计划分别核验。赠金实验预算至多USD20，自付上限USD0–1；东京、私有SSM、主/备停止、最长4小时、workflow SHA及真实CUDA仍必需。WorkSpaces强制固定后处理预设，原始MP4与SHA保留，最终严格120帧、24fps、774×1376、5秒才显示完成。REAL预检独立显示本地审计投影，不冒充AWS实时查询。默认REAL禁用，未生成可通过真实gate。相关REAL/Mock后端58项、前端7项契约测试通过，**都是本机模拟/合成素材，不是H3真实推理**。[Bridge运行说明](../runbooks/2026-10-25-local-real-h3-bridge.md)。
- 本机REAL8768现已实际启动，健康ready/tunnel/gpu均false，预检十项均null、launch_allowed=false。Ego切REAL确认生成按钮disabled；弹窗顶部溢出修复和最终UI证据仍待完成。
- 已从官方包在工作区解包AWS CLI/SSM插件，版本检查分别为AWS CLI2.38.5、插件1.2.896.0，下载包/插件Amazon Authenticode签名有效；未运行全局安装、未修改全局PATH。MSI解包运行已通过本机版本检查，不称AWS正式认证的portable安装方式。官方CLI短期登录已完成，仅本机缓存，没有创建长期AK。首次SSM激活通知曾意外输出激活码，该激活已撤销确认；替代激活未注册节点，清理后已删除成功，混合激活列表0。当天11:08 UTC+8创建的本轮hybrid默认角色确认无注册/活动后已删除。记录不复写激活码或认证缓存。
- 两个本轮约18KB S3模板对象均已成功删除、failed=0；空桶因创建归属未知而保留。既有VPC及网络未修改、未删除。

- [原生Windows只读诊断与锁定清单](2026-10-26-windows-h3-bootstrap-readiness.md)已准备：ComfyUI v0.42.1固定提交/资产哈希、四个H3权重修订及哈希、驱动/RAM/SSM/loopback检查；PowerShell AST解析零语法错误。脚本未执行，不安装、不下载、不更新驱动、不生成视频，DeploymentReady始终false；实际GPU兼容仍待实机。

## 本轮费用估算与结算边界

目录存在时间从02:54 UTC至约04:15 UTC，按常规两台Managed AD Standard合计USD0.146/h，不假定试用抵免，保守按2小时估算为**USD0.292**。辅助日志、调用、S3等费用另计；此数不是本轮总费用或最终账单。

GPU没有创建成功，但未取得GPU小时/月费的已核账单证据，不能据此声称发票为0。最终新增费用、赠金抵扣和税尚未结算，不承诺自付为0，也不把显示预计余额当作实时结算结果。

实际驱动、首次管理员登录、SSM节点及隧道均未验证；保护实际扫描和资源清理验收也不能代替真实桌面停止测试。

## 当前阻塞与下一步

2026-10-26恢复时，Ego更新后原任务空间11不可用。经用户允许重建AWS专用工作区2并由用户完成登录，浏览器认证阻塞已解除，当日赠金已刷新。密码和MFA不在聊天收集。

当前实际阻塞是创建接口报告区域Graphics.g6.4xlarge上限0，不能以控制台Applied=1覆盖该错误，也不自动执行错误文本建议的提额/联系支持。主代理已停止云创建，已知本轮目录、保护栈、备用执行、未使用SSM激活、hybrid角色及模板对象的清理验收完成。仍待最终UI溢出修复证据和实际费用/赠金/税结算核验；没有真实视频可下载。不得把未验证字段标true。

**GPU桌面0，单次创建被拒，计划升级0，真实H3视频0，本地真实生成MP4为0；已知本轮资源清理已确认。目标尚未完成，最终账单仍待结算。** 不能称新增云资源、发票或自付为0。本轮未改两个原始ZIP、未合并main、未联系AWS支持、未申请提额。

官方资料：[WorkSpaces计费](https://aws.amazon.com/workspaces/desktop-as-a-service/pricing/)、[FAQ](https://aws.amazon.com/workspaces-family/workspaces/faqs/)、[QuickSetup](https://docs.aws.amazon.com/workspaces/latest/adminguide/managing-wsp-personal.html)、[目录价格](https://aws.amazon.com/directoryservice/pricing/)、[VPC价格](https://aws.amazon.com/vpc/pricing/)、[SSM价格](https://aws.amazon.com/systems-manager/pricing/)、[DCV WebAccess](https://docs.aws.amazon.com/workspaces/latest/userguide/amazon-workspaces-web-access.html)、[Hybrid安装](https://docs.aws.amazon.com/systems-manager/latest/userguide/hybrid-multicloud-ssm-agent-install-windows.html)、[CLI登录](https://docs.aws.amazon.com/cli/latest/reference/login/)、[配置缓存](https://docs.aws.amazon.com/sdkref/latest/guide/feature-login-credentials.html)。
