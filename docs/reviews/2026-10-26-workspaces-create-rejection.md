# 东京 WorkSpaces G6 单次创建被拒

2026-10-26，Asia/Shanghai。**仅提交一次单台 `Graphics.g6.4xlarge` 创建请求，实际被区域上限0拒绝；GPU创建成功数为0，真实H3视频为0。** 主代理已停止云创建，已知本轮资源清理已确认。预算仍为赠金实验最多USD20、抵扣后自付最多USD1；没有升级计划、申请配额、联系AWS支持或重试，最终费用未结算。

## 实际请求结果

脱敏本机证据：`work/aws-workspaces-execute-20261026/create-rejection.json`。记录观察时间为 **2026-10-26T04:08:27.650Z**，区域 `ap-northeast-1`，bundle `wsb-9zg6r5j55`，机型 `Graphics.g6.4xlarge`。

创建接口返回的错误类型与原文为：

> ResourceLimitExceededException: You cannot create more than 0 number of Graphics.g6.4xlarge WorkSpaces in this region. Request a limit increase by contacting AWS Support.

此前控制台观察到 Applied=1，实际创建接口却执行最多0台限制。**两者矛盾的原因尚未确认，以真实创建拒绝判定本次阻塞。** 这不是机型已创建、驱动不兼容或视频生成失败，也不能据此把整套AWS账户的所有GPU配额都推断为0。错误文本中的提额/联系支持建议没有执行。

## 创建前已确认与仍未完成

- 创建被拒前主/备CloudFormation均已`UPDATE_COMPLETE`，截止分别为05:50/05:55 UTC。东京主04:06:38 UTC日志读到deadline_due=false、matched=0；没有真实桌面停止证据。
- 新加坡备用document v2的05:55 UTC截止曾读回，新执行`a1bbf66d-fa49-4ab2-8574-ae2e99566dc1`曾在等待中。旧执行`582f4e3c-d28e-419b-b276-9a7fef208212`当时已Cancelled。以上为创建被拒前状态；两个执行后续均Cancelled，栈删除终态见清理段。
- 目录`d-95679b1f48`已Active且已注册，Internet enabled、AGA disabled、Web Access已读回enabled。没有成功创建GPU桌面，因而实际驱动、首次桌面登录、SSM hybrid节点/隧道及H3模型推理都未验证。
- 本机58项后端与7项前端契约测试通过，使用模拟接口和合成视频；不是H3真实视频，不证明实际显存、推理耗时、真实停机或账单。
- 本机REAL8768已实际启动，健康ready/tunnel/gpu均false，预检十项均null、launch_allowed=false；Ego切REAL确认生成按钮disabled。弹窗已修复顶部溢出，实际浏览器确认标题/关闭按钮可达且能滚动至最后检查项。这是本机禁用状态验收，不是云端推理。

## 清理及费用

主代理通过Ego完成以下清理验收：东京桌面列表0；专建目录取消注册后删除，重新加载目录列表0且旧banner消失；东京主栈/新加坡备用栈在deleted筛选均`DELETE_COMPLETE`；两个备用执行均`Cancelled`；替代SSM激活删除成功且混合激活列表0。本轮默认hybrid角色`AmazonEC2RunCommandRoleForManagedInstances`创建于当天11:08 UTC+8，确认无注册/活动后已成功删除。两个本轮约18KB S3模板对象成功删除、failed=0。空桶因创建归属未知而保留；既有VPC与网络未改、未删。此结论仅覆盖上述已知本轮资源，不表示全账户不存在收费资源。

目录从02:54 UTC至约04:15 UTC存在，按常规USD0.146/h、保守2小时估算为**USD0.292**；辅助日志、调用、S3等另计。实际最终费用、赠金抵扣与税尚未结算；没有GPU小时/月费的已核账单证据，不声称发票或自付为0，也不把预计余额当作实时结算余额。[完整执行记录](2026-10-26-workspaces-live-execution.md)、[脱敏状态JSON](2026-10-26-workspaces-live-execution.json)。
