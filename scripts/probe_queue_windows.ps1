# AniFlow 旧多 Key 队列探测入口：安全停用（2026-10-11）
#
# 旧版会默认多个账号 × 多轮发送可能产生费用的视频创建请求，
# 并错误地把「有成功、有队列满」判定为账号独立容量。
# 共享队列仅剩少量空位时，也会有相同的混合结果；
# 因此旧脚本不能用来证明九倍产能。
#
# 请改用 GitHub 当前 P0-010 的单条视频验证器：
# scripts/one_agnes_real_shot.py
# 它默认只预览，真实提交必须在可信环境明确确认计费，
# 仅允许一个 Key 和一条固定 5 秒 MYCL-001 镜头。
#
# This legacy multi-Key batch launcher is intentionally disabled.

Write-Host "此旧版多 Key 队列探测已停用，以避免隐式并发生成及错误的产能结论。" -ForegroundColor Yellow
Write-Host "请阅读 README 中的 P0-010 单镜头安全验证说明。" -ForegroundColor Yellow
exit 2
