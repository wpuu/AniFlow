# WorkSpaces 双停机保护模板审阅

**状态：本地模板与静态审阅完成；未部署、未启动 AWS 执行、未创建桌面。**

## 两次部署

`guard-template.yaml` 使用 JSON 编写，属于合法 YAML 子集，CloudFormation 接受此格式。通过 GuardMode 参数部署两次：

- 东京 ap-northeast-1：Primary，创建 Scheduler、Lambda、两个执行角色和一个保留1天的 CloudWatch Log Group。
- 新加坡 ap-southeast-1：Backup，仅创建独立 SSM Automation 文档及独立角色。脚本固定访问东京 WorkSpaces API，不调用主 Lambda。

模板 Rules 拒绝模式与区域不匹配。没有 WorkSpace、GPU、AD/目录、网络、SSM Managed Node、S3 bucket、订阅或付款计划资源。没有 AWS 凭证。Outputs 只含模式、名称、实验标签和时间，不含账户ID或角色ARN；内部 IAM ARN 使用动态账户ID隔离权限。

## 固定参数与执行行为

两次部署使用相同 ExperimentId、DeadlineUtc、BackupDeadlineUtc。日期严格使用 UTC，正则只校验形状，不校验日历及先后关系。创建桌面前人工核对两个日期有效，主截止早于备用截止，且均留在用户授权窗口内。建议创建前记录 T0，主动约 T0+1小时40分，备用约 T0+1小时45分，以首次两小时服务费窗口为目标；四小时是最长限制，不能默认安排运行四小时。不得随任务进度延后截止时间。

目标桌面必须在 CreateWorkspaces 请求内原子携带本次唯一 ExperimentId 标签，运行模式为 AUTO_STOP。先创建后补标签会产生无保护窗口，禁止。不能删除或修改该标签。同标签的全部东京桌面均会受保护。

主保护每分钟扫描：DescribeWorkspaces 分页，再逐个 DescribeTags；截止前也真实调用只读接口，以便通过日志核验执行通路。截止后仅停止标签匹配、AUTO_STOP 且状态允许的桌面；每批最多25个。检查 HTTP200 内的 FailedRequests，记录错误码并使本次函数失败，下一分钟仍独立扫描。STOPPING 不等于 STOPPED，无匹配也不记作成功。计划没有结束日期，截止后持续处理意外重启，直至人员确认停止、下载完成并清理栈。

Lambda 超时60秒，主日志保留1天。未设置 reserved concurrency，避免新账户区域并发限制导致预留并发配置失败；正常负载由每分钟调度限制。执行只使用服务角色临时凭证，不导出密钥。

**创建备用栈不会自动启动 Automation。** 必须在新加坡 SSM 控制台选择输出文档，启动执行，确认 InProgress 且 WaitForFixedBackupDeadline 正在等待，并保存执行ID与固定UTC时间。启动者需该文档 StartAutomationExecution 与备用角色 iam:PassRole 权限。不要提供长期密钥。

备用由 aws:sleep 等待绝对时间，随后 aws:executeScript 以独立代码和角色扫描东京。每15秒复核并停止，持续约550秒，步骤上限600秒；API异常记录错误类型并重试，末次未确认匹配桌面全部 STOPPED 会失败。它不依赖桌面 SSM Agent、主 Lambda 或主 Scheduler。执行结束后主保护仍继续。

备用输出仅留在 SSM 原生执行历史，未启用额外 CloudWatch 输出；不能声称 SSM 历史也只保留1天。

## 创建前必须验收

1. 本账户赠金清单实际涵盖 Lambda、CloudWatch、EventBridge Scheduler、Systems Manager Automation；模板不能证明赠金资格。辅助服务可能有少量用量费，需合并核算抵扣后自付不超过USD1；任一不适用则不得部署。
2. 东京主栈 CREATE_COMPLETE、Scheduler ENABLED；至少两次真实主日志正常枚举，deadline_due=false，无 AccessDenied、超时、异常。新加坡备用栈 CREATE_COMPLETE，备用 Automation 已启动并处于等待。
3. 两次参数一致、标签唯一。人工审阅独立角色的只读及按标签 Stop 权限。aws:sleep 成功不能证明后续 Stop 权限已实测，可补 IAM Policy Simulator 静态检查，但不能称真实停机测试。
4. 桌面创建后立即确认主日志 matched=1、真实 AUTO_STOP 和标签；未匹配或保护异常时，不继续下载模型，直接云端停止并处理。

## 限制与清理

两条链路分离了东京 Scheduler/Lambda 与新加坡 SSM，但共同依赖账户 IAM 和东京 WorkSpaces Stop API，不能宣称完全消除共同故障。StopWorkspaces 只接受 AUTO_STOP/MANUAL 与 AVAILABLE、IMPAIRED、UNHEALTHY、ERROR。PENDING、STARTING、MAINTENANCE 等不能立即停；官方无精确停止耗时保证，所以提前触发并实际确认 STOPPED。API返回成功不是最终停止证据。

Windows shutdown、关闭Comfy、锁屏、断网、Budget告警不能替代服务停止。AutoStop断开60分钟只作第三层；锁屏/休眠可能仍连接。GPU WorkSpaces停止不保存未保存的应用状态，应及时保存MP4并下载校验。

停止后月度固定部分等可能继续收费，重新登录可再次启动。先退出客户端、核云端 STOPPED、核视频保存，再清理桌面和残留费用。本模板无 TerminateWorkspaces 权限，不删除桌面。未停止前不得删除主栈或取消备用执行。备用结束后可删除备用栈，最后删除主栈及日志组；不能在备用执行仍运行时删其角色/文档。

## 静态检查结果

- JSON解析、两段Python的 ast.parse 通过；未执行SDK调用。
- AWS官方 cfn-lint 对东京、新加坡两区域校验退出码0，无诊断。
- 资源类型仅 IAM::Role、Lambda::Function、Logs::LogGroup、Scheduler::Schedule、SSM::Document。
- 两个 Stop 角色均限制东京 workspace/* 和精确 aws:ResourceTag/ExperimentId，无桌面创建、启动、修改、删除权限。
- 未做模拟停机或模拟视频；静态通过不能证明账户可部署、真实停止或赠金抵扣。未调用 AWS ValidateTemplate 或创建栈。

## 官方依据

- https://docs.aws.amazon.com/workspaces/latest/api/API_StopWorkspaces.html
- https://docs.aws.amazon.com/workspaces/latest/api/API_DescribeWorkspaces.html
- https://docs.aws.amazon.com/workspaces/latest/api/API_DescribeTags.html
- https://docs.aws.amazon.com/workspaces/latest/api/API_CreateWorkspaces.html
- https://docs.aws.amazon.com/service-authorization/latest/reference/list_workspaces.html
- https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html
- https://docs.aws.amazon.com/scheduler/latest/UserGuide/cross-service-confused-deputy-prevention.html
- https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-sleep.html
- https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-executeScript.html
- https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-setup-iam.html
- https://docs.aws.amazon.com/workspaces/latest/adminguide/running-mode.html
- https://aws.amazon.com/workspaces-family/workspaces/faqs/
