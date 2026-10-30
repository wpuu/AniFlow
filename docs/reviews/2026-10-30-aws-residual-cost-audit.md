# AWS 成本异常及实例删除后的残留费用核查

日期：2026-10-30，北京时间。**后续状态更新：Owner已明确批准清单内清理，2026-10-30 14:40:38独立复查通过；详见[实际清理结果](2026-10-30-aws-approved-cleanup-result.md)。** 下文保留批准前的只读审计快照，不把它当作清理后的当前残留清单。未修改账户计划或配额，也不宣称永久零费用。

## 核查结论

1. 两条已查看的成本异常属于历史检测：EC2 Compute 为 2026-09-11 至 09-19，影响 $12.18；EBS 为 09-12，影响 $0.07。EC2 详情指向马尼拉 Local Zone 的 t3.medium 等贡献项，不是本次 Ohio G6。异常影响额是相对预期的偏差，不是额外罚款，也不等于当前应付金额。清除告警不会停止资源计费。
2. 10月账单在北京时间13:24:29所示估计净额和税均为 $0.00，包含约 $51.13 的使用费及相应赠金抵扣，不能写为没有消费。马尼拉用量原价约 $49.43：EC2 Linux t3.medium 677.888小时/$42.98、EBS gp2/$3.06、公网IPv4/$3.39。账单和成本异常均存在滞后，删除前用量仍可能后续入账。
3. 已用任务隔离的官方短期会话核对原部署账户，并扫描全部20个已启用区域。EC2实例、EBS卷、自有快照、公网IP、NAT、VPC端点、容量预留、RI、ENI、Fleet、ASG、负载均衡、RDS及快照等均为0。全局 CloudFront分发、Route53托管区及注册域名、Savings Plans均为0。控制台支持计划为Basic，Marketplace活跃订阅为0。
4. 仍有存储和潜在调用入口，不能直接保证不会继续产生任何费用。Ohio S3剩11个小文件/版本共313,193字节，无删除标记、无未完成分段上传；另两个模板桶为空。Ohio日志185,501字节，Virginia两组既有日志合计1,042字节。全部三组日志合计186,543字节。S3和日志可能产生极小存储用量；是否被免费额度、赠金或账单舍入抵消不作为归零依据。
5. 原有非项目Lambda有一个AuthType=NONE的Function URL。实际策略允许任意主体经该URL调用，因此外部调用可能产生请求、执行和日志费用。未进行测试调用。函数没有预置并发或事件源映射，代码最后修改时间为2026-04-09，不能将它当成本项目新建函数直接删除。
6. 项目保留主、资产、备用三栈：Ohio主保护Lambda和日志、资产S3/角色/安全组，新加坡备用SSM文档及角色。主EventBridge规则已DISABLED；相关SSM自动化均为终态；没有预置并发。栈、IAM、普通空闲Lambda本身不等同按小时实例费，但其日志/对象及未来调用需要分别处理。

## 审计范围与保留的未知项

结构化脱敏证据见 [2026-10-30-aws-residual-cost-audit.json](2026-10-30-aws-residual-cost-audit.json)。原始账户级资源清单、账单观察及私有配置仅留本机，不上传身份、Function URL、签名URL、凭证或账户ARN。

- 补查20区域的Secrets Manager、Glue jobs/sessions/crawlers/triggers、SNS、SQS、独立Spot请求，返回成功的项目均未发现资源；GameLift Streams在原项目地域未发现资源。
- WorkSpaces、Lightsail、台湾SageMaker旧Notebook及部分GameLift端点有区域不可达/操作不支持，不能把错误写为资源0。Lightsail巴西用IPv4补查后为0；香港返回RegionSetupInProgress。Glue旧DevEndpoints的Get操作明确disabled，替代List操作也返回服务错误，属于未完全验证项。
- 没有启用或扫描当前未opt-in的区域，没有为核账调用付费Cost Explorer API、启动Amazon Q调查或运行SSM审计自动化。控制台Cost Explorer仅用于读取已有账单信息。
- 云日志的storedBytes是服务报告字段，不是对未来费用的承诺；账单税及赠金以最终结算为准。

## 已完成的清理前备份

所有11个S3小文件已下载G盘，逐个校验长度和本地SHA256；三份实际CloudFormation模板及项目日志也已保存，共24份实验文件。两组既有Lambda日志另行保存并校验，函数代码摘要另存以便清理后证明原函数未改动。本轮未下载模型、未生成视频。

备份目录和完整私有清单由本机 `work/aws-zero-charge-audit-20261030/residual-backup-receipt-private.json` 与 `legacy-log-backup-receipt-private.json`记录。保留既有D/G盘归档和两个原始ZIP。

## 待 Owner 确认的具体收尾方案

1. 关闭既有测试Lambda的公开Function URL并清理仅用于该URL的两条公开调用授权，保留函数及代码。此步骤会让该公开网址停止访问，必须明确取得Owner同意。
2. 在重新核对同一账户、精确资源身份、规则禁用及自动化已终态后，清空已备份的11个实验小文件并删除项目资产、主保护、备用三栈；核实S3桶、保护Lambda、规则、日志、SSM文档等实际删除完成，不以Delete API接受代替终态。
3. 删除已备份的两组既有Lambda日志，保留函数代码。两个空模板桶及AWS管理的KMS密钥不产生所识别的闲置资源月费，可以保留，不扩大到无关资源删除。
4. 清理后刷新相关资源清单，确认公开入口及项目残留为0、原函数CodeSha256不变；账单刷新后再区分删除前历史用量与新用量。此刻尚未获批及执行，不能写成零费用验收通过。

## 官方说明

- [AWS非预期费用排查](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/checklistforunwantedcharges.html)：删除实例不代表删除所有关联收费资源，须按区域检查。
- [AWS费用与资源核查](https://repost.aws/knowledge-center/resources-unexpected-charges)：账单有约24小时更新滞后，已删除资源此前产生的费用仍会显示。
- [成本异常检测说明](https://docs.aws.amazon.com/cost-management/latest/userguide/manage-ad.html)：依赖Cost Explorer数据，可滞后24小时；异常检测本身不能替代实时库存。
- [Lambda Function URL访问权限](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html)：NONE模式可通过资源策略向公众开放；本轮已检查实际策略，尚未修改。
