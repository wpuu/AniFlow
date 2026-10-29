# G6 n确实运行，但保留失败；停止中终止逻辑已纠正

北京时间2026-10-29 08:39:06，单次RunInstances实际分配Ohio2a g6.xlarge；08:39:43实际Running，Ego已打开实例详情。不是Mock或仅本地测试。实例编号已直接交给Owner核验。

本轮未部署ComfyUI或下载模型，真实视频0。主/备用云SDK支持、IAM双标签正反例和无目标执行实际通过，但不能当作真实GPU停机成功。首启08:40:51才启动探针，08:42:17尚在Torch冷导入；旧的装置后5/6分钟截止留给实际首启的时间不足。

08:42:54实际Stopping后，旧retained实现仍在Cleanup截止把Stopping作为终止目标，08:43:48首个Force+SkipOsShutdown Terminate被AWS接受。正式独立Stop/Cleanup都Failed，均未在有界窗口内确认终态。直到08:50:25才重新读取确认Terminated。故保留失败、严格10分钟终态失败、GPU实测报告未完成；不能声称部署或视频成功。Owner要求“别又删了”没有被本轮实现满足，主负责人已明确告知。

尝试保护Stopping的精确实例控制器在实际状态已Shutting-down时拒绝执行；没有绕过状态检查或伪称保留成功。确认不可逆终止且备用Failed后，停用冗余主终止规则；不据此推断多次API调用是延迟原因。CloudTrail已确认Stop和Terminate均实际带Force/SkipOsShutdown且无API错误，控制面接受不等于终态完成。

## 已纠正但尚待下一次实机验证

retained_guard现在仅对Pending/Running执行紧急Terminate；Stopping仅重试Stop，Shutting-down仅观察，Stopped/Terminated保留。Unknown整批拒绝写入。Stopping仍不算Stopped、不算GPU预检通过；新行为不会为“达到终态时间目标”删除停止中的实例。43项本地测试/Ruff通过，云端旧n没有该补丁，不能追溯算通过。

下一次o仍为G6.xlarge、Ohio2a、单台、唯一请求和独立意图；先确认n计算及相关资源已清，再重新部署验证新保护。显式固定装置后10/11分钟截止，为CFN更新、启动和Torch首启留时间；从真实GPU请求计时仍最多10分钟预检，先成功报告后主动Stop并观察Stopped。正常停止保留；不使用旧全删流程。完整模型预算没有被这份预检预算替代。

n实际首次Stopping距请求少于5分钟，辅助资源清理必须小于1小时；n按5分钟计算、1小时磁盘/辅助及等额预留共保守留0.30美元。o按10分钟GPU、6小时磁盘/辅助及等额预留约0.643438美元，合计约0.943438美元、门槛0.95美元，均为未抵扣前估算而非账单。创建前脚本必须实查这些前提，不满足就不能执行。赠金继续按当前42.64估算、足额券覆盖十项服务核验，税率未知，不推断免税。不提额、不升级、不降画质。

原ZIP、D/G归档保留；新Linux bootstrap只是本地准备，尚未执行下载、部署或生成。PR7保持Draft，不合并main。
