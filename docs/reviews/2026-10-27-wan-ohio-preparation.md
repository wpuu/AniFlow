# 俄亥俄州 EC2＋Wan2.2 候选：实际核查及本地准备

2026-10-27，Asia/Shanghai。用户要求继续该候选；主负责人是唯一 AWS 操作者，子代理仅处理公开资料、本地代码及测试。没有创建新的云端资源、下载大权重、执行真实GPU预检或提交视频；原H3归档及两个原ZIP未改，main未合并。

## 账户与机型的实际证据

- 北京时间09:29的接口实读：Ohio `us-east-2` 的G/VT按需额度8vCPU，当前非终止实例0；控制台也显示应用8、默认0、使用0。[接口快照](2026-10-27-wan-ohio-current-eligibility.json)、[页面脱敏原文](2026-10-27-wan-ohio-quota-console.txt)。
- `g7e.2xlarge`准确配置为8vCPU、64GiB主存、单RTX PRO Server 6000、98304MiB名义显存；三个可用区均列出该机型。可用区供应清单不代表实时容量，也没有真实创建成功证据。[AWS规格](https://aws.amazon.com/ec2/instance-types/g7e/)。
- 同次接口账户为PAID/ACTIVE，赠金估算USD46.49；未改变计划。精确Linux按需价格USD3.36312/h，SKU `84MJTJ2X73HAYM9Q`，生效2026-10-01。只核实了这项单机价格，镜像产品代码、磁盘、网络、保护、税及完整费用尚未核完，不能称净自付条件已通过。
- 账单页显示五笔Active、日期2026/10/30、估算USD46.49，并注明约24小时更新、最终数随发票结算。到期精确时刻仍未查明。[赠金页面摘要](2026-10-27-wan-ohio-credit-summary.json)。
- 第一次赠金服务清单已读到EC2/S3/传输/VPC/保护相关服务；逐笔刷新尚未完成时，账单页出现“您已注销”“所有选项卡中的AWS会话均已注销”，SDK也返回`LoginRefreshRequired`。[未完成的镜像及网络复查](2026-10-27-wan-ohio-image-network-incomplete.json)。不能把部分清单或旧估算作为创建授权。

同一Ego专用空间已交给用户本人重新登录，未索取密码/MFA；等待确认后才能恢复操作。只读临时CLI连接已用官方logout退出、缓存0、精确删除本任务4个认证文件，不修改全局AWS配置，不执行浏览器退出。[临时连接退出回执](2026-10-27-wan-ohio-auth-cleanup.json)。

## 本地完成的部分

1. 新Ohio EC2主保护模板为Lambda/Events每分钟执行；Singapore备用为独立SSM Automation固定时刻执行并有界重试，不调用主Lambda。代码与IAM同时限制Ohio区域、唯一实验标签，只有Describe/Stop/Terminate权限；没有创建/启动实例权限。**仅本地测试通过，尚未AWS ValidateTemplate、部署或实测停机。** 实例终止也不代表磁盘/S3等辅助费已清理。
2. 新Wan独立契约与API模板固定Comfy修订及官方模板哈希，四份FP16权重元数据和完整SHA256已核对；普通20步、10/10专家切换、CFG3.5、euler/simple、shift5.0，无LoRA或4步加速支路。图片/动作仍为待所有者确认的占位符，负向提示已单独绑定，尚未下载权重或提交生成。
3. 目标为原生800×1376、121帧、24fps，再仅裁边为774×1376并截取前120帧形成5秒；不放大生成视频、不插帧。官方默认640×640/81帧/16fps与该目标不同。全FP16约64.05GiB文件体量不能全驻留64GiB主存；固定Comfy的`--highvram`GPU优先加载和默认safetensors内存映射有源码依据，但目标显存、主存峰值、耗时及与H3等效画质都仍待真实验证。失败不自动换FP8、降分辨率或降帧率。[模型契约](../model-contracts.md)、[工作流模板](../../infra/ec2/wan-workflow-bundle.template.json)。
4. Real Bridge新增独立`REAL_WAN / wan2.2-i2v-a14b`身份，精确绑定Ohio/g7e及10项审计条件；旧H3区域、机型、124帧源门槛均保留。Wan为独立121帧源及严格5秒后处理。持久任务缺少/错用preset即失败，不能走宽松下载分支；请求键、未知提交恢复及单次POST限制保留。
5. 实际Grok视觉入口`apps/studio-mock-ui`新增Wan标签、Ohio设备及预检，保留原视觉和H3历史。提交前重新核对模型身份，服务切换时在上传/提交前拒绝；播放器显示真实文件、哈希和未知指标，不伪造Seed/CFG/显存。没有改错另一套Agnes或静态候选前端。

主负责人复跑 **131项Python契约/保护/本机合成媒体检查、14项前端契约、Ruff、TypeScript、Vite构建**，全部通过。[本地验证范围](2026-10-27-wan-ohio-local-validation.json)。测试中的上游和GPU信息为替身，媒体是本机合成样例，**不是Wan真实成片，也不是AWS停机证明**。React多组件修改已按相应技能检查，未加入新前端依赖。

本机8768已在独立Wan运行数据目录启动，实际HTTP显示Wan/Ohio/g7e、目标64/96GiB；ready=false、launch_allowed=false、GPU未连接、AWS读写0。它读取本机阻塞快照，不借用其他本机Comfy GPU。[实际本机HTTP](2026-10-27-wan-ohio-local-blocked-http.json)。旧H3运行数据保留，8765未动。

## 尚需完成的输入及下一步

- AWS本人登录并确认完成。恢复后刷新完整赠金服务资格、计划、镜像来源及无付费ProductCodes、网络/SSM权限和全部费用；在这些门槛及主备保护实部署、权限正反例、备用实际等待确认前，不创建GPU。
- 原指定D盘目前只余约22GB，完整新Wan模型及环境包预计需约75GB；已询问能否改存`G:/AniFlow-Wan-Archive-20261027`，G盘当前约106GB空闲。**尚未获准，也未在G盘建目录或下载大模型。** 原D盘H3包不删除、不覆盖。
- 条件通过后才做一次单台准入及固定10分钟真实GPU/驱动/CUDA/私有通路预检；没有DryRun、页面额度或本地测试可替代真实准入。预检通过并实际停止后，再在有效固定保护与预算内准备生成阶段；所有者图片和动作仍待确认，未提前提交。
- Linux端私有S3自动保存、实际模型装载、目标采样、本机MP4完整校验及环境/模型归档仍须实机完成，不能把本轮代码准备写成这些步骤已通过。

[当前执行状态](2026-10-27-wan-ohio-execution-status.json)。本轮真实视频仍为0；不提额、不升级、不联系AWS支持，不因登录等待创建资源。
