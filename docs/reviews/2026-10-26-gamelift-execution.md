# 东京 GameLift H3 执行记录

**进行中；真实 GPU/CUDA 预检和真实 H3 视频尚未完成，真实 MP4 为 0。** 用户已授权打包保存、双重停止、私有 S3、防重复提交、最多十分钟预检，成功后再跑一条原画质五秒 H3。净自付上限 $1，不提额、不升级、不联系客服。

## 已完成并有实际证据

- 官方 `GetAccountPlanState`：`PAID / ACTIVE`，接口剩余赠金 `$47.56`。此前账户计划未知的表述已得到补全，没有执行升级。
- Ego 浏览器重新打开五笔有效赠金的完整服务清单：均包含 GameLift Streams、S3、Lambda、CloudWatch Events 和 Systems Manager；显示到期日 2026/10/30，精确到期时刻仍未知。余额属于账单估算，未把 `$91.14` 已结算余额当作实时余额。
- 东京 `gen6n_pro` 两个测试流组创建请求均明确 `AlwaysOnCapacity=0, MaximumCapacity=0, TargetIdleCapacity=0`；没有申请 GPU 分配。
- 东京定时路径真实删除 `sg-VW3z6UejX`，CloudTrail 事件 `5ad5d557-664c-43b1-b80f-4e77a18f8386`，北京时间 2026/10/26 15:23:29，执行者为本次 Primary GuardRole，未报错。
- 新加坡 SSM 路径真实删除 `sg-uWKNXg7Ka`，CloudTrail 事件 `394ce525-e5d3-4ed7-8ce6-a346c4b739a8`，北京时间 2026/10/26 17:50:13，执行者为本次 Backup GuardRole，未报错。SSM Automation `a80f89a1-82ed-4013-b001-202610260001` 两步均 Success。
- 两流组最终查询均 `ResourceNotFoundException`；不是仅凭删除 HTTP 返回值判断释放。保护栈此时只针对测试流组，新实验仍须重新绑定和启动备用执行，不能拿旧执行充当新保护。
- 东京私有源/结果桶已部署，四项 Public Access Block 均开启；4MiB 实际上传下载 SHA256 往返通过，测试对象已删除。不是公开视频或 H3 成片。
- Linux 本机环境构建完成：官方 ComfyUI 固定提交 `63be2f9b82ad0dac88a7ceaa28a9cf3154125a18`、官方 Python standalone 3.12.15、PyTorch `2.14.1+cu130`、comfy-kitchen `0.2.39`。本机只检查导入，没有 CPU 视频生成。
- 官方原始音频 VAE 605254808 字节已完整校验并保存到私有东京 S3，SHA256 为 `8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48`。其余三个大权重尚在准备，不把清单当成已下载证明。

## 本地实现与验证

新增 S3 条件请求、跨会话不可重取 claim、请求与会话绑定、当前心跳核验、结果字节/哈希验证下载，以及 GameLift 的独立前端核验字段。原有 WorkSpaces/EC2 入口及两个原 ZIP 未被覆盖。

本轮 66 项 Python 契约/恢复测试、8 项前端契约测试、TypeScript 检查和 Vite 构建通过。这些验证没有调用 H3，不能作为真实推理或真实画质证据。

## 当前阻塞与下一步

Windows 直传出现临时 DNS/连接异常；已终止无进度传输并中止未完成分片，改用官方 Hugging Face Xet 下载单个原文件、全文件哈希后上传；使用官方 S3 路径寻址规避桶域名 DNS 问题。没有改系统 DNS。

CloudShell 东京实际提示账户仍在验证、可能需要两天；没有联系客服或删除重试环境，亦不能据此推断 GameLift GPU 一定不可用。辅助模型搬运 Lambda 的 CreateStack 连接关闭，两次后查询均无该栈，未声称已部署它。

完整运行环境约 5.6 万文件，超过 GameLift 三万文件限制，正在封装支持资源包。待四模型及运行包全部完成 → 东京应用 READY → 新目标双保护落实 → 十分钟实际 GPU 预检。GPU、实际显存、耗时、库存、真实服务费及最终抵扣/税均仍待实测，不将未知写成零。

费用口径：零 GPU 容量测试没有 GPU 分配费；S3、自动化等辅助用量可能有少量费用，最终抵扣以账单为准。原 WorkSpaces 历史目录估算与本轮用量分开记录，未宣称整个账户零费用。

来源：[GameLift API](https://docs.aws.amazon.com/gameliftstreams/latest/apireference/API_CreateStreamGroup.html)、[应用格式](https://docs.aws.amazon.com/gameliftstreams/latest/developerguide/applications.html)、[临时会话角色](https://docs.aws.amazon.com/gameliftstreams/latest/developerguide/session-credentials-setup.html)。账户实际证据来自经授权的 Ego 会话和临时 AWS CLI 登录；无凭证写入仓库。
