# 保持FP16与原生成规格的L40S备选（待用户同意）

2026-10-27，Asia/Shanghai。g7e.2xlarge三个Ohio可用区及自动选择均已实际返回InsufficientInstanceCapacity，实验GPU0；本方案仅分析，未修改Bridge机型门槛、未创建g6e。

## 已实读与尚未验证

- Ohio `g6e.2xlarge`为8vCPU/64GiB主存，单NVIDIA L40S；产品名义48GB，实际规格接口报告45776MiB，约44.70GiB，不能当48GiB。沿用Ohio G/VT按需8核池；同账户此前实读应用8、使用0，不提额。
- Linux共享按需精确价USD2.24208/h。三个可用区列出该机型，**不代表当前容量**；没有做该机型实际创建，也未证明内存能装下目标工作流。[只读接口证据](2026-10-27-wan-l40s-readonly.json)。
- 四小时计算上界USD8.96832；沿用已列明磁盘/网络/保护/环境转出等保守预留，合计约USD12.78066，保留20美元实验上限和赠金抵扣后自付不超过1美元。估算非账单；创建前重新核验赠金和保护。

## 只改变权重驻留，不降低生成参数

保持同四份FP16权重及哈希、原生800×1376/121帧/24fps、20步/CFG3.5/shift5.0，最终仅裁边774×1376并取120帧形成严格5秒。保持GPU执行T5、专家和VAE；CPU仅暂存权重，不执行模型推理，不改FP8、不改分辨率/帧数/步数。

取消96GiB方案的`--highvram`，使用固定Comfy默认卸载及safetensors mmap，在启动日志中实际确认DynamicVRAM/comfy-aimdo启用；不能根据参数推定成功。**不使用`--lowvram`、`--cpu`、`--cpu-vae`或`--gpu-only`**，避免文本编码或VAE落到CPU。

源码依据：[内存管理](https://github.com/Comfy-Org/ComfyUI/blob/63be2f9b82ad0dac88a7ceaa28a9cf3154125a18/comfy/model_management.py)、[启动初始化](https://github.com/Comfy-Org/ComfyUI/blob/63be2f9b82ad0dac88a7ceaa28a9cf3154125a18/main.py)、[参数定义](https://github.com/Comfy-Org/ComfyUI/blob/63be2f9b82ad0dac88a7ceaa28a9cf3154125a18/comfy/cli_args.py)、[mmap权重读取](https://github.com/Comfy-Org/ComfyUI/blob/63be2f9b82ad0dac88a7ceaa28a9cf3154125a18/comfy/utils.py)。

## 实际风险与止损

两专家各约26.615GiB，合计53.23GiB，无法同驻这张卡；T5约10.586GiB，VAE权重约0.236GiB。按阶段交换权重提供可试路径，但注意力激活、复制、CPU固定页和系统内存仍可能OOM。VAE源码公式对目标尺寸、2字节计算估计约14.35GiB激活，非实际峰值；须先卸载专家。普通解码OOM时Comfy默认可能转GPU分块解码，仍同尺寸/模型但不能保证逐像素一致，需要实测记录。[VAE源码](https://github.com/Comfy-Org/ComfyUI/blob/63be2f9b82ad0dac88a7ceaa28a9cf3154125a18/comfy/sd.py)。

[原厂I2V说明](https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B)仍给出至少80GB的原厂命令要求；不能把Comfy的44.7GiB候选称为官方已验证配置。权重交换会变慢，无法保证在4小时内成片。

如用户同意：为新实验重建双云端保护并核实实际等待，加入每次开机固定截止；只创建一台，先做最长10分钟CUDA/私有通路预检并实际停止，再准备模型装载验证及单次生成。任何阶段失败及时停止清理，不自动改精度或视频规格。生成阶段建议最多2.5小时固定窗口，给保护与4小时总上限留余量。原g7e保护已经清理，不能沿用其“已部署”状态。

**待同意原因：从96GiB g7e改为名义48GB L40S会改变内存、耗时和失败风险；用户要求先分析后决定。** 新机型及Bridge门槛尚未改动。
