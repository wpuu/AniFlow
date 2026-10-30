# Windows H3 原生部署就绪清单

**2026-10-26：仅完成本地只读预检脚本和公开元数据锁定。未访问AWS账户，未安装、下载权重、启动Comfy、注册SSM或生成视频。AWS登录已交还用户。**

## 预检脚本边界

[windows-h3-preflight.ps1](../../infra/workspaces/windows-h3-preflight.ps1) 默认只诊断。可指定 PortableRoot（包含ComfyUI与python_embeded的解压根目录）、AssetDirectory（安装包所在目录）、LogDirectory。仅显式启用 VerifyLargeFileHashes 时才读取大文件进行SHA256校验，避免未准备好时浪费GPU计时。没有下载/解压/安装/驱动升级/SSM注册/生成接口。

脚本检查原生Windows x64、nvidia-smi、单L4、r580以上驱动、名义24GiB显存、64GiB级RAM、SSM本机服务、已暂存文件与本地8188监听地址。显存允许22,000至26,000MiB以容纳显示/虚拟化预留；RAM允许观察值至少63GiB，属于本次64GiB桌面验收容差，**不是模型官方最低配置**。暂存完成后20GiB可用磁盘是本次操作余量，不是官方硬性最低值；暂存前还必须另加约40.07GB权重、2.02GB压缩包与解压空间。

四个安全开关只记录操作人已核验：日本推理/大陆使用许可、双停止保护、私有连接、Hybrid用量费用。HardStopUtc必须填已生效保护的绝对UTC截止时间，脚本不创建或延长截止。开关不是AWS证据。缺项写Blocked，退出码2；退出码0也不等于部署/视频成功。DeploymentReady及RealVideoGenerated始终为false。

实际运行后才在LogDirectory生成带UTC时间的JSON日志；当前没有运行日志。脚本不读SSM激活信息、注册私钥、AWS凭证或完整机器标识。暂存的嵌入Python存在时会做import/CUDA可见性诊断，可能建立小型CUDA上下文，不加载H3模型、不做推理。Comfy或模型文件缺失只报告，不补装。

## 锁定官方ComfyUI

- 官方版本：[v0.42.1](https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.42.1)，2026-10-19发布。
- 提交：`63be2f9b82ad0dac88a7ceaa28a9cf3154125a18`。
- 资产：[ComfyUI_windows_portable_nvidia.7z](https://github.com/Comfy-Org/ComfyUI/releases/download/v0.42.1/ComfyUI_windows_portable_nvidia.7z)，2,018,444,114 bytes。
- GitHub资产SHA256：`496afd18790ec685d99ebba2edf200d7371a29fbdd3a992bb0f4f52f244a6874`。
- 元数据来源：[官方release API](https://api.github.com/repos/Comfy-Org/ComfyUI/releases/tags/v0.42.1)。只读取元数据和少量源码，未下载该资产。

选默认Nvidia包，不选cu126包、ARM包或第三方Portable。不使用浮动latest下载链接，不自动运行更新器。包的实际Python/PyTorch/CUDA版本仍须由目标桌面探测；公开安装文档说明默认Portable采用Python3.13与CUDA13.0。此提交requirements锁定comfy-kitchen 0.2.39、workflow-templates 0.11.89，脚本核对已安装版本，并记录实际torch版本。

脚本还校验main.py、comfyui_version.py、comfy/cli_args.py、requirements.txt的固定提交原始字节SHA256。它只证明这四文件匹配，不能替代整个安装包哈希或证明所有文件未修改。如果出现换行转换差异，先调查，不擅自忽略校验。

## 锁定H3四个必要权重

仓库：[Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3)。固定修订：`e5eb578a89295337b8ff433a035929ce0279e0b6`。下表路径相对ComfyUI/models，哈希来自该修订HF LFS元数据，脚本内已完整录入。

| 路径 | 精确bytes | SHA256 |
|---|---:|---|
| diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors | 20,970,379,616 | e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a |
| text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors | 15,687,142,551 | 35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6 |
| vae/minimax_h3_video_vae_int8_convrot.safetensors | 2,811,065,184 | 52a2c8c73583c86e4f41cdcce3a6ad0ea562987bc0bf3d60a0cef5f5c8e60c0e |
| vae/minimax_h3_audio_vae_fp32.safetensors | 605,254,808 | 8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48 |

下载地址必须固定为 `https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/e5eb578a89295337b8ff433a035929ce0279e0b6/` 加表中路径；不能改为main或其他精度。四文件共40,073,842,159 bytes，约37.32GiB，不是峰值显存/RAM。

保持默认attention及原官方pruned_int8_convrot，不换w6a8、不自行改FP8或Turbo。官方明确Comfy Kitchen attention与int8_convrot不兼容；这不代表整个comfy-kitchen量化库不可用。Qwen nvfp4_awq文本编码器官方明确不要求Blackwell。CUDA13预编译内核要求r580+驱动，WorkSpaces现有驱动低于此值时停止部署并报告，不自动升级托管图形驱动。

## SSM Hybrid准确位置与参数

[AWS当前Windows安装文档](https://docs.aws.amazon.com/systems-manager/latest/userguide/hybrid-multicloud-ssm-agent-install-windows.html)要求管理员PowerShell。东京官方setup CLI位置是 `https://amazon-ssm-ap-northeast-1.s3.ap-northeast-1.amazonaws.com/latest/windows_amd64/ssm-setup-cli.exe`。安装/注册参数为 `-register`、`-activation-code`、`-activation-id`、`-region`，本次region必须ap-northeast-1。不要套用EC2的实例角色安装方法，也不要擅加provider=EC2去探测WorkSpaces宿主元数据。

AWS指定setup CLI使用官方区域链接，新注册时新取，并明确不应另存以后重用；因此这里保留官方动态路径，**不能伪称其已锁定版本/哈希或已离线缓存可用**。将来明确授权安装时，需按官方签名校验流程核验刚取得的CLI，记录本次SHA256/签名/实际Agent版本，不使用skip-signature-validation或自定义manifest-url。

本轮脚本不提供安装器。未来安装动作的激活ID和激活码必须交互式Read-Host -AsSecureString输入；不能写进脚本、JSON、命令历史、transcript、Git、截图或聊天。原生CLI必须接收参数，运行时仍可能短暂出现在进程参数或系统审计中；避免录屏/转储并由管理员直接本机执行，不把它描述成绝对无泄露通道。安装日志与SSM注册私钥不应直接全文归档。

SSM服务Running只证明本机服务状态，仍须认证控制台核正确mi节点Online、东京注册区域以及本机私有隧道真实连接。Hybrid Session Manager和Run Command自2026-09-30按量收费，旧“高级层/免费会话”假设已过期；须核本次赠金覆盖及总自付≤USD1。[AWS Hybrid现行说明](https://docs.aws.amazon.com/systems-manager/latest/userguide/activations.html)

## 执行前仍阻塞或待填

| 项目 | 当前状态 |
|---|---|
| 用户重新登录AWS | 等待用户；不操作交还的浏览器 |
| 重建后L4、显存、64GiB RAM与r580+驱动 | 尚未实机验证 |
| 固定UTC双停止保护、实验标签、服务费窗口 | 待主负责人对重建资源重新验收，旧资源证据不能直接沿用 |
| Comfy下载/解压、四文件SHA256、CUDA13与内核 | 尚未执行 |
| SSM激活、Agent Online、本机私有隧道 | 尚未执行；激活信息仅运行时输入 |
| 官方I2V模板精确导出与API schema | 尚未锁定/验证；不得编造prompt_id、节点ID或输入参数 |
| 真实首帧路径、5秒、9:16、768短边、24fps | 待正式工作流核验；模板默认可能是640x640/0.4MP，不能冒充目标 |
| 生成、GPU峰值、耗时、MP4落盘及ffprobe/SHA256 | 全部尚未验证 |

官方原生I2V教程列出四个核心权重，并有可选Turbo LoRA；部分模板模型扫描仍可能要求LoRA。四文件不代表任意模板可以原样无缺失运行。必须读固定版本实际模板，确认非Turbo路径、默认attention、模型扫描与节点schema；如必须额外LoRA，先报告并获得本次方案确认，不自动下载或启用Turbo。

原生帧数有17k+5网格，不能随意写120帧并保证严格5秒。先核实实际模板时长参数和最终封装结果，再由ffprobe确认真实时长。L4 24GiB/64GiB是可试候选，没有本配置精确768短边5秒Windows基准，不能承诺窗口内成功。

## 核查证据与本地验证

- [官方Portable说明](https://docs.comfy.org/installation/comfyui_portable_windows)
- [固定提交requirements](https://github.com/Comfy-Org/ComfyUI/blob/63be2f9b82ad0dac88a7ceaa28a9cf3154125a18/requirements.txt)
- [固定提交CLI参数](https://github.com/Comfy-Org/ComfyUI/blob/63be2f9b82ad0dac88a7ceaa28a9cf3154125a18/comfy/cli_args.py)
- [H3固定修订元数据](https://huggingface.co/api/models/Comfy-Org/MiniMax-H3/revision/e5eb578a89295337b8ff433a035929ce0279e0b6?blobs=true)
- [H3官方教程](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)
- [H3官方原生I2V教程](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native)
- [官方comfy-kitchen](https://github.com/Comfy-Org/comfy-kitchen)

PowerShell解析器检查通过；未在本机或AWS桌面运行诊断脚本。读取了公开release/HF元数据及少量固定源码，没有下载Portable资产、SSM安装程序或模型权重，归档前未提交Git，归档提交由主负责人执行。
