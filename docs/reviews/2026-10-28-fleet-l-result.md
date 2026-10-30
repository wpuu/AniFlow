# 修正后唯一请求仍被参数组合拒绝：全清理，未进入容量测试

北京时间2026-10-28 **20:29:37**，Owner允许的l唯一非DryRun CreateFleet返回`InvalidParameterCombination`。具体原因为按优先级选择与最高小时价不能同时设置。原请求的CloudTrail事件已按**ClientToken、AWS请求号、错误内容**三项精确核对，responseElements为空；随后实际盘点Fleet/实例/卷/网卡/EIP0。[真实拒绝及零资源证明](2026-10-28-fleet-l-validation-refusal.json)。没有Fleet ID、实例ID、GPU运行或容量判断。

本轮遵守只发一次真实创建请求，收到错误后未重发。另有**两次显式DryRun只读调用**，分别检查原非法组合与修正组合，两者均返回DryRunOperation。这证明DryRun主要检查权限，不能证明完整参数兼容或库存；不能把它当成实际开机成功。[两次只读检查](2026-10-28-fleet-l-readonly-parameter-check.json)。总计1次真实创建方法调用被校验拒绝、2次只读DryRun，不能混算成3次GPU准入或容量拒绝。

## 已完成的预算、保护和修正

[本轮新账户及价格](2026-10-28-fleet-l-eligibility.json)：Ohio配额8、实例0，G6.xlarge/G5.xlarge为0.8048/1.006美元每小时；[当前券范围](2026-10-28-fleet-l-credit-scope.json)为五笔Active、Oct30到期、预计43.45美元，一笔预计20美元券覆盖本轮十项服务。账户原有PAID/ACTIVE未升级，官方Amazon免费镜像无Marketplace产品码；税区仍unknown、EBS/IPv4仍服务级映射，无收费Cost Explorer调用。

[合并预算自动门槛](2026-10-28-fleet-l-budget.json)实际检查本次预检含等额缓冲约0.489857美元，加入前次k辅助费及等额预留约0.154524美元，两次合并约0.644381美元≤0.65。k无GPU、精确请求匹配、全部清理且辅助时长766.85秒小于1小时的事实被自动核对。该预算是预检估算，并非实际费用、最终税或更早历史项目总账。

本轮全新三栈实际CREATE_COMPLETE；主无目标真实调用/IAM正反例与独立新加坡四步骤Success。固定停止20:35:00、兜底终止20:36:00，两栈实际UPDATE_COMPLETE、备用实际等待确认后才建启动模板及发请求。[本轮真实保护证据](2026-10-28-fleet-l-protection.json)。没有真实GPU，所以不能声称完成真实GPU停机试验。

移除上一轮错误的ValidUntil后，本轮触发了另一项服务端组合限制；这是提交参数组合问题，不是GPU库存结论。现在已把选择策略改为**lowest-price、保留每小时1.006美元上限，移除候选Priority**，两款机型/六个候选/目标1/Spot0/固定截止均不变。按已查价格，G6仍比G5便宜，保留原预期顺序。新增回归后**40项本地测试、Ruff和差异检查通过**。修正后的代码未进行新的真实创建请求，不能承诺AWS必定接受或开机成功。

初次执行前39项模块与此前29项清理测试、原优先级版本来源保存在[a9bebe0执行前记录](https://github.com/wpuu/AniFlow/blob/a9bebe0/docs/reviews/2026-10-28-fleet-l-sources.json)；40项及最低价版本属于本次拒绝之后。本地SDK结构检查无法覆盖服务端参数组合约束，不作为真实成功依据。

## 实际收尾和当前阻塞

20:35:29已核实启动模板、三栈及全部IAM角色/Profile、Lambda、规则、日志、备用文档、安全组、私有桶不存在；实例/卷/网卡/EIP0，正式备用实际Cancelled。[清理回执](2026-10-28-fleet-l-cleanup.json)、[Fleet/模板边界](2026-10-28-fleet-l-metadata-cleanup.json)。20:35:45官方CLI退出、缓存0，精确清理本轮认证文件，浏览器登录和全局配置未改，[退出回执](2026-10-28-fleet-l-auth-cleanup.json)。Ego仅Luna/high操作，自有页已关闭、原页和空间2 active保留，无finish/handOff。

当前累计**28次历史容量拒绝不变，另有2次Fleet参数拒绝**；六候选仍没有实际容量结果。GPU创建、真实机上CUDA/SSM预检、模型下载/加载和真实视频均0。无GPU运行费，辅助费/税/抵扣待账单，不能声称总费用0。

本轮到此停止，不再发送真实创建请求。原ZIP、D/G归档、Bridge与画质设置保持，PR #7 Draft，main未合并。下一步若Owner愿意继续，建议批准[有界参数修正、仅一次容量准入的具体方案](2026-10-28-fleet-bounded-validation-proposal.md)，从而明确哪些无资源校验拒绝可修正后继续、哪些情况必须停止；尚未获准、尚未实现或启动该新流程。
