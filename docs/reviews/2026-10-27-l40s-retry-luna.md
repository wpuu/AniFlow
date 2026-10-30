# L40S再试与低用量执行记录

2026-10-27，Asia/Shanghai。用户要求Ego使用gpt-6-luna高思考并继续推进，先真实实例再模型。

- 本轮新建子代理时显式传入`model=gpt-6-luna`、`reasoning_effort=high`及独立短上下文；该代理完成同一个Ego空间2恢复与官方临时登录。此前Ego由主会话直接执行，未声称以前已用Luna。未改全局主会话模型设置。[官方子代理配置说明](https://learn.chatgpt.com/docs/agent-configuration/subagents)。
- 主负责人准备并复用既有固定截止脚本，先由单一控制器执行。之后将本轮云端协调独占交给同一个Luna，主负责人停止AWS操作；没有并行AWS写入者。控制器结束后才接续清理。
- 本轮实验aniflow-wan-ohio-20261027-l40s-c，仍为Ohio g6e.2xlarge。两套保护真实验证、固定截止及备用实际等待均完成后，提交唯一一次自动分配请求。AWS返回InsufficientInstanceCapacity，没有实例ID；08:42:58Z按请求键和实验标签查询匹配实例0。未做GPU预检、模型部署或视频提交。
- 固定StopUtc为08:51:29Z，CleanupUtc为08:56:29Z；未延长运行中截止。不存在的预检报告不计为额外模型故障，也不计为成功。
- 16:45最终核查：备用已实际Cancelled；三栈、IAM角色/Profile、Lambda、规则、日志、SSM文档、安全组和S3桶均不存在，实验实例/卷/ENI/EIP均0。官方CLI已logout、缓存0、精确清理4个任务认证文件，全局AWS配置和用户浏览器登录未改。[清理证据](2026-10-27-l40s-retry-cleanup.json)、[退出回执](2026-10-27-l40s-retry-auth-cleanup.json)。辅助服务最终费用和赠金结算仍未取得账单。

另复核发现G盘归档下载已中断，最近状态约15.34GB/68.78GB、0份完整校验；之前报告“后台继续”不准确。此问题已记录，当前仍优先实际GPU准入，不以归档或本地测试代替开机成功。
