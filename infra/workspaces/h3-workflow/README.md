# H3 I2V 工作流静态准备

**仅静态准备，未完成H3实机推理或真实视频。** 本轮云端创建被AWS实际0配额以ResourceLimitExceededException拒绝，已知本轮资源已清理。此目录没有AWS操作、模型权重、视频、GPU实测或批准开机的gate。

- `workflow-bundle.template.json`：供现有Bridge读取的完整16节点模板，固定官方Comfy-Org来源。保留首帧/文本运行时TODO，bindings为114.image、104.prompt；严格后处理preset为h3_native_5s_portrait_v1。
- `video_minimax_h3_i2v.json`：官方0.11.89依赖的JSON包0.1.115原始I2V模板，未修改；不是API提交文件。
- `upstream-lock.json`：ComfyUI v0.42.1固定提交、官方包版本、公开URL和SHA256。清单中的上游源码与4MB wheel没有全部复制进仓库。
- `node-schema-evidence.json`：15种官方节点的固定源码schema摘录、原始文件和行号；不是实机object_info。
- `postprocess-plan.template.json`：源视频实际出现后才可执行的裁边/裁时方案，输入输出文件名仍为TODO。
- `source-licenses.json`、`LICENSE.ComfyUI`：保留来源、上游许可证元数据和GPLv3正文；不将第三方源码摘录冒充项目原创，也不替代H3模型/输出许可证。
- `preparation-status.json`：如实记录本轮未推理状态，不是pass gate。

模板取官方非Turbo false分支：pruned_int8_convrot、四个核心权重、默认attention、20步、res_multistep/simple。新增官方ImageScale(lanczos, center)将运行时上传首帧按比例裁切/缩放到800×1376，再送H3；原始 `assets/character/agnes-felt-test-frame.png` 不改动、不包含在此目录。

H3真实生成124帧/24fps，之后只保留前120帧，视频像素横向裁到774×1376（左12、右14），最终严格9:16、短边774、5秒；不缩放生成视频、不插帧。首帧预处理与最终视频后处理是不同阶段。H.264/AAC重新编码仍有压缩，不能宣称位级无损。

本地已验证JSON可解析、节点/绑定引用完整、官方schema来源、非Turbo20步与尺寸帧数算术。尚未验证实际服务schema、权重加载、显存、耗时、视频质量、真实费用或MP4完整性；不能把静态检查称真实成功。

未来实跑须重新取得真实配额、费用与双停止保护证据，核原四权重哈希及实际CUDA/驱动，通过私有连接读取真实object_info；由Bridge上传本人首帧、绑定任务文本、单次提交并持久化真实prompt_id，再核MP4下载/ffprobe/完整解码/SHA256。不要直接提交任何含TODO的模板，也不要为本目录编造通过的gate。
