# AniFlow AWS东京H3｜Work模式执行交接｜2026-10-25

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
