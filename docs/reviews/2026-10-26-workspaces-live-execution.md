# 东京WorkSpaces云端执行状态

2026-10-26，Asia/Shanghai。预算已明确为赠金另计、自付最多USD1，首轮赠金实验预算不超过USD20。唯一一次单台G6创建请求被实际区域上限0拒绝，云创建已停止。**GPU桌面和真实视频均为0，已知本轮资源清理已确认；最终费用、抵扣与税尚未结算。** [脱敏状态JSON](2026-10-26-workspaces-live-execution.json)、[创建拒绝说明](2026-10-26-workspaces-create-rejection.md)。

## 实际完成

1. 用户在重建的Ego专用工作区2完成登录。赠金页刷新为预计剩余USD48.28，结算剩余USD91.14，五笔Active、到期日均为2026-10-30。余额有更新延迟，精确到期时刻仍未确认。
2. 官方CLI通过现有浏览器会话完成短期登录，仅在本机工作目录缓存，没有创建长期AK。首次SSM激活通知曾意外输出激活码；该激活已撤销并确认，不在记录中复写激活码。替代hybrid激活曾创建、注册上限1、未注册节点，现已删除成功，混合激活列表0；SSM隧道未建立。
3. 东京主栈`aniflow-h3-primary-20261026`于02:45:30 UTC创建完成，创建被拒前已确认`UPDATE_COMPLETE`；04:06:38 UTC真实CloudWatch日志读到deadline_due=false、matched=0。这是实际Scheduler/Lambda执行，不能据此声称真实桌面停机已测试。清理后已在deleted筛选中确认`DELETE_COMPLETE`。
4. 新加坡备用栈`aniflow-h3-backup-20261026`于02:49:51 UTC创建完成，创建被拒前已确认`UPDATE_COMPLETE`，备用document v2中05:55 UTC截止已读回。新执行`a1bbf66d-fa49-4ab2-8574-ae2e99566dc1`曾在等待中；清理后与旧执行`582f4e3c-d28e-419b-b276-9a7fef208212`均确认`Cancelled`。备用栈已在deleted筛选中确认`DELETE_COMPLETE`。
5. 两套保护使用唯一实验标签`ExperimentId=aniflow-h3-tokyo-20261026-a`。更新后的主/备截止为**2026-10-26 13:50/13:55中国时间**（05:50/05:55 UTC），两栈更新均已完成。先前04:45/04:50 UTC为旧参数。随后仅提交一次单台G6创建请求，没有桌面创建成功。
6. 东京目录`d-95679b1f48`曾Active且已注册WorkSpaces，Internet已启用、AGA已禁用，Web Access已读回enabled。现已成功取消注册并删除，重新加载后Directory Service目录列表0、旧banner消失。Microsoft AD Standard两控制器按常规合计USD0.146/h估算，不假定试用抵免。既有默认VPC及网络未修改、未删除，没有创建NAT。
7. 本机REAL/Mock后端58项测试及前端7项契约测试通过。它们使用本机模拟接口及合成视频，不是H3真实推理，不证明AWS停机、实际显存或真实账单。
8. 04:08:27.650 UTC，唯一一次单台`Graphics.g6.4xlarge`创建返回`ResourceLimitExceededException`，明确说明该区域最多可创建数量为0。此前控制台Applied=1与创建接口实际限制矛盾，原因未确认；没有重试、申请提额、联系支持或升级计划。脱敏原始错误保留在本机`work/aws-workspaces-execute-20261026/create-rejection.json`，[Git记录](2026-10-26-workspaces-create-rejection.md)保留必要字段。
9. 本机REAL服务8768已实际启动；健康返回ready=false、tunnel_connected=false、gpu_connected=false，预检十项均null、launch_allowed=false。Ego切换REAL确认生成按钮disabled。弹窗已改为顶部对齐并保留滚动，Ego在701px高视口实读标题区顶部24px、关闭按钮顶部约44.6px，滚动到底可达账户资格及独立停机检查。最终[本机接口证据](2026-10-26-local-real-disabled-evidence.json)不代表真实生成成功。
10. 云资源清理后，已通过AWS官方`logout --profile aniflow-tokyo`删除本轮CLI登录缓存，再逐个删除本轮目录密码、已撤销激活码和登录临时文件；未退出用户浏览器账户，没有创建长期AK。固定版H3的16节点工作流与来源锁定已归档到`infra/workspaces/h3-workflow/`，仅静态准备，未下载权重或执行推理。

备用CloudFormation曾短暂提示模板改变。主代理通过Ego S3控制台下载上传对象后，核对字节数18,669和SHA256 `34801aa95ddcbdb366349fb147472c0726b2727d1fe9dbe1e9fc6821ec358d56`，与Git中已审阅模板完全一致，再提交；没有盲目接受未知变化。原始截图含账户头部，仅在本机中间目录，不上传Git；归档只保留脱敏字段与摘要。

## 未完成、执行门槛与清理责任

当前阻塞是创建接口实际执行的区域Graphics.g6.4xlarge数量上限0，不是目录未就绪或保护更新尚未完成。控制台Applied=1及服务包可见不能推翻创建拒绝。账户Free/Paid字段仍未明确显示，本轮没有执行计划转换。

主代理已停止云创建并完成下列已知本轮资源清理；不采用错误消息中的提额/联系支持建议，不自动重试。没有GPU，实际驱动、SSM hybrid Online、私有隧道及H3推理均未验证。保护验收不能代替真实桌面停止测试，本机契约不能代替真实成片。

目录从02:54 UTC至约04:15 UTC存在，按常规USD0.146/h、保守2小时估算为**USD0.292**；辅助日志、调用、S3等费用另计。实际最终费用、赠金抵扣与税尚未结算，不能称“新增实验费用0”或“自付0”。没有GPU小时/月费的已核账单证据，不能据GPU创建0推断发票0。实际显存、推理耗时及真实MP4均无；没有升级计划、申请提额、联系支持或更换模型。

清理已由主代理通过Ego确认：东京桌面列表0；专建目录取消注册后删除并重载列表0；东京主栈与新加坡备用栈均`DELETE_COMPLETE`；两个备用执行均`Cancelled`；替代SSM激活删除成功、混合激活列表0。本轮默认hybrid角色`AmazonEC2RunCommandRoleForManagedInstances`创建于当天11:08 UTC+8，确认无注册/活动后已成功删除。两个本轮约18KB S3模板对象均删除成功、failed=0；空桶因创建归属未知而保留，既有VPC与网络未动。此为已知本轮资源清理验收，不是全账户零收费或最终账单结清声明。
