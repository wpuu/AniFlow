# 东京 GameLift H3 执行记录

**当前 GPU 配额 0，未启动 GPU、未进行真实 CUDA/H3 预检、未生成真实视频。** 用户要求配额不足时停止云端创建；本轮已停止 GPU 阶段，并完成经用户授权的 D 盘归档及本轮云端资源清理。没有提额、升级计划、联系客服、换模型或降低画质。

## 配额已核对，不能沿用历史 1

- [历史控制台原文](2026-10-26-gamelift-quota-historical-one.txt)确实显示“应用的账户级别配额值 1 / 默认 0 / 利用率 0”，并非把默认值当成应用值。历史记录保留，不覆盖原数据。
- [新控制台原文](2026-10-26-gamelift-quota-console-zero.txt)显示同一东京配额代码 `L-9F99CEA2` 的应用值、默认值、利用率均为 0。浏览器账号与临时 CLI 身份已在本地比较，一致；未公开账号标识。
- [API 对账](2026-10-26-gamelift-live-quota-zero.json)：东京 `GetServiceQuota` 的 `Value=0, GlobalQuota=false, QuotaAppliedAtLevel=ACCOUNT`。俄勒冈、俄亥俄查询同一东京配额也为 0；弗吉尼亚该配额不存在，未将查询错误解释为可用额度。
- 因此当前不是错账户、误读默认值、错选 EC2 G/VT 或 WorkSpaces 配额，也不是全局配额口径。历史 1 到当前 0 的原因没有证据可确认，不能声称 AWS 已批准 GPU 或擅自归因于 Free Plan。
- 此交叉核验做得过晚，应在大文件准备前同时核对 API。发现 0 后没有申请任何正容量，没有调用 StartStreamSession；十分钟 GPU 预检没有开始。

## 已实际完成的准备

- 账户官方接口 `PAID / ACTIVE`，最新读取的剩余赠金快照 `$47.25`；没有执行升级。五笔有效赠金的完整服务清单均包含 GameLift Streams、S3、Lambda、CloudWatch Events、Systems Manager 和 AWS Data Transfer。显示到期日为 2026/10/30，精确时刻仍未确认；账单估算不是实时可支配余额。
- [完整封装清单](2026-10-26-gamelift-package.json)：9 个源文件、47,406,154,264 字节。四个 H3 原始权重共 40,073,842,159 字节，逐个全文件 SHA256 核对；没有改量化版本或原非 Turbo 20 步工作流。
- 环境包 `runtime.tar` 为 7,332,311,040 字节，SHA256 `4c2faf120bfd08b590554eb755e2467c4d3e29ca5c9a1c656d0fd2405a7b90e1`。官方 ComfyUI 固定提交 `63be2f9b82ad0dac88a7ceaa28a9cf3154125a18`、Python standalone 3.12.15、PyTorch 2.14.1+cu130、comfy-kitchen 0.2.39；只验证本机导入，没有 GPU 或 CPU 视频推理。
- S3 应用根目录本身为未压缩文件夹，启动脚本自行验证并展开支持环境包、链接原始模型，避免 5.6 万环境文件超过应用源文件三万上限。东京应用 `a-VcfYE4Fel` 曾实际达到 READY，复制位置只有东京；READY 不等于 CUDA 或 H3 已通过。
- 东京私有桶已验证四项 Public Access Block、BucketOwnerEnforced、AES256、强制 TLS。4MiB 真实上传/下载/哈希往返成功；[真实条件 claim](2026-10-26-gamelift-private-s3-probe.json)首次成功、重复被拒绝，探针对象已删除。这些不是 H3 视频测试。

## 双停止和计算清理实证

- 旧零容量测试：东京定时路径删除 `sg-VW3z6UejX`，CloudTrail `5ad5d557-664c-43b1-b80f-4e77a18f8386`；新加坡 SSM 删除 `sg-uWKNXg7Ka`，事件 `394ce525-e5d3-4ed7-8ce6-a346c4b739a8`，SSM 两步 Success，最终均 NotFound。
- 当前运行准备组 `sg-W1YCvpPIm` 始终配置 `AlwaysOn=0, Maximum=0, TargetIdle=0`，分配容量为 0。新保护绑定该组和应用，东京规则启用、函数返回 armed，新加坡执行已实际进入固定时间等待。
- [最终 CloudTrail](2026-10-26-gamelift-final-guard-events.json)：北京时间 19:36:29 主保护删除该组，事件 `b14d338a-247d-4f5d-8bb2-91a50cc9caa9`；19:37:27 删除应用副本，事件 `b12e6cb3-89a9-40d9-aaa4-9bc276c33c09`，均为本轮 Primary GuardRole、无错误。
- [计算清理结果](2026-10-26-gamelift-compute-cleanup.json)：组和应用均 ResourceNotFoundException；新加坡备用执行 `7b058ed8-a30c-4b2e-a7f4-6e94dd5a0296` 两步 Success。没有仅凭删除 HTTP 返回值判断清理完成。
- 计算资源消失、备用完成后，先删除东京主保护、新加坡备用、模型搬运三套临时栈；本地全量归档两次校验后，再删除私有存储及剩余存储栈。[最终逐项复查](2026-10-26-gamelift-final-cleanup.json)于 2026-10-26 20:45:58 北京时间确认：本轮流组、应用、S3 桶及四个资源栈均不存在。仅清理本轮命名资源，未操作账户其他资源。

## 本地归档与代码

用户已明确选择“转存本机 D 盘并清理云端”，现已完成。目录 `D:/AniFlow-H3-Archive-20261026` 保存全部 9 个源文件，共 47,406,154,264 字节；[归档清单](2026-10-26-gamelift-local-archive.json)中逐个字节数及完整 SHA256 均通过。删除云端前又独立重新计算全部 9 个文件的完整哈希，[删除回执](2026-10-26-gamelift-storage-delete.json)记录二次核验和 15 个本轮源对象删除，最终桶与存储栈不存在。目录另有清单和中文归档说明，合计 11 个文件；当前没有本机真实 MP4。

[临时登录清理](2026-10-26-gamelift-auth-cleanup.json)：官方 CLI logout 成功，本次登录缓存文件为 0，四个本次临时认证辅助文件已逐项删除；没有修改用户全局 AWS 配置。后续恢复需要重新登录，归档本身不依赖该临时会话。

新增私有 S3 请求、跨会话不可重取 claim、请求与会话绑定、当前心跳核验、结果哈希下载，并接入 GameLift 独立前端核验字段。未知 GPU 显存、H3 耗时和最终费用均保持未知。原 Grok 视觉保留，两个原始 ZIP 的 SHA256 再核一致，PR7 保持 Draft，不合并 main。真实 GameLift/ComfyUI 连接及视频链路仍未实测。

本机 Bridge 已显示当前 GameLift 失败审计快照：目标 gen6n_pro、配额检查 False、禁止开机、GPU 未连接、AWS 查询 0。失败快照永远不能授权生成；也不会借用其他本机 ComfyUI 的 GPU 冒充 AWS 设备。新增安全回归后，本轮 72 项 Python 契约测试、8 项前端契约、TypeScript 检查、Vite 构建及相关 Ruff 检查通过；这些没有执行 H3 推理。

## 费用与限制

GPU 分配为 0，因此本轮没有 GPU 分配费。模型搬运、存储、请求和自动化等辅助用量另计，已核相关服务适用赠金；最终费用、赠金抵扣和税仍待账单入账，不能把余额变化直接当成本实验实测费用，也未宣称整个账户费用为零。

后续只有在实际 GPU 配额可用，并重新核查费用、许可和两个正在生效的保护后，才能进行真实预检。本归档完整性和本地代码测试均不能替代真实五秒 H3 成片。
