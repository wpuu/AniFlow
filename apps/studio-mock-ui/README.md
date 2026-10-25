# AniFlow Studio Mock UI (P0-035)

这是基于 Grok 原版界面制作的**独立工程集成副本**。原始 ZIP 与 `apps/studio-candidate-grok/` 完全保留不变；当前生产用的 AniFlow 8765 不会被替换。

**只连本机模拟服务，没有 AWS / ComfyUI / Agnes 真实 API。**

本地验证（仓库根目录）：

```
cd apps/studio-mock-ui
npm ci
npm run build
cd ../..
python scripts/run_studio_mock.py
```

然后使用 `http://127.0.0.1:8767/`，选择**电脑本地 PNG/JPG**首帧，输入提示词，点击生成。后台 SQLite 自动记录任务，约6秒完成一个原仓库**蓝色模拟视频**，保存于 `data/runtime/studio/videos/`，并在前台可播放/下载。断线刷新后读取原始任务编号，重复创建有幂等键保护；不需要真实 GPU。HTTP 状态不使用 Grok 原版随机模拟计时器。

`src/data.ts` 只暴露 MOCK 模型；不显示虚假的 AWS 在线状态与计价。原始文本+Logo资产在仓库根目录的 Grok ZIP 中，Mock服务可从 ZIP 原样读取 Logo，不上传外部服务。不删除当前系统任何视频或密钥。浏览器仅保存“从列表隐藏”的 ID，不保存图像Base64与任务资料。

这里实现的是**Mock工程通路**，尚未连接真实 H3/ComfyUI、AWS EC2、SSM、自动关机，也不代表真实5秒图生视频成功。任何 AWS 的实际创建、启动、消费都需要重新做预算/实例/许可与显存核验并经用户允许。
