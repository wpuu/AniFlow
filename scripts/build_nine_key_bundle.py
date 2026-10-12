"""Package *only public, allowlisted* AniFlow files into a Node-free Windows test bundle.

The artifact contains the EXISTING 9-Key app, not a new platform. The prebuilt
frontend is tied to a SHA-256 manifest so Windows setup need not run npm.
No .env, credentials, browser state, node_modules or runtime data are copied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "pyproject.toml",
    "首次安装AniFlow.cmd",
    "启动AniFlow.cmd",
    "一键重启当前AniFlow.cmd",
    "scripts/restart_aniflow_windows.ps1",
    "scripts/setup_aniflow_windows.ps1",
    "scripts/start_aniflow_windows.ps1",
    "apps/grok-frontend/dist/index.html",
    "content/shotlists/MYCL-001-cat-lapping.json",
    "content/factpacks/MYCL-001-cat-lapping.json",
)
INSTRUCTIONS = """AniFlow 雪所长｜9-Key 视频测试包（非已生成的视频）

1. 解压整个文件夹。需要 Windows、Python 3.11+ 和首次安装时可访问的 Python 包下载源。
2. 双击“首次安装AniFlow.cmd”。前端已由 GitHub CI 预构建，不需 Node/npm。
3. 安装成功后以后统一双击“一键重启当前AniFlow.cmd”，它只会关闭已确认的旧 AniFlow 服务，校验当前包版本再打开浏览器，不清空 Key/历史。
   “启动AniFlow.cmd”仍保留兼容。
4. 选择 Agnes Video 2.5 Flash，点击“载入雪所长首镜头 · 5秒”。
5. 在自己的可信浏览器填写合法 Key。先点击一个 Key 的“生成视频”，确认计费后才考虑9-Key批量。
6. 收到完成结果后尽快打开视频链接并保存 MP4；任务可能存在服务器上，网页刷新不等于取消任务。
7. 遇到提交不确定：先点“继续查原任务”，不要改用其他浏览器重发。

请勿在聊天、GitHub Issue、PR、CI 中提供密钥。不要运行旧 v7.0.4 安装器。
本包仅通过无 Key 的自动化验证，不代表已得到 Agnes 真视频。
"""


def build_bundle(root: Path, dest: Path, source_commit: str) -> dict[str, object]:
    if dest.exists():
        raise FileExistsError(f"Bundle output already exists: {dest}")
    if len(source_commit) != 40 or any(c not in "0123456789abcdef" for c in source_commit.lower()):
        raise ValueError("Expected exactly one 40-character Git commit SHA")
    src_files = sorted((root / "src" / "aniflow").rglob("*.py"))
    if not src_files:
        raise FileNotFoundError("AniFlow Python package source is absent")
    candidates = [root / path for path in REQUIRED] + src_files
    for item in candidates:
        if not item.is_file() or item.is_symlink():
            raise FileNotFoundError(f"Missing or unsupported source file: {item}")

    dest.mkdir(parents=True)
    for item in candidates:
        relative = item.relative_to(root)
        # Strict input allowlist: no environment secrets or private runtime files.
        if any(part.startswith(".") for part in relative.parts) or "node_modules" in relative.parts:
            raise ValueError(f"Unsafe bundle source: {relative}")
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, target)

    built_html = dest / "apps" / "grok-frontend" / "dist" / "index.html"
    digest = hashlib.sha256(built_html.read_bytes()).hexdigest()
    manifest: dict[str, object] = {
        "bundle": "AniFlow-existing-nine-key-windows",
        "source_commit": source_commit,
        "frontend_sha256": digest,
        "contains_credentials": False,
        "requires_node_npm": False,
        "requires_python_3_11_plus": True,
    }
    (dest / "prebuilt_frontend.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (dest / "9Key使用说明.txt").write_text(INSTRUCTIONS, encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    options = parser.parse_args()
    manifest = build_bundle(ROOT, options.output_dir.resolve(), options.source_commit)
    print("NO_SECRETS_BUNDLE_CREATED")
    print(f"SOURCE_COMMIT={manifest['source_commit']}")
    print(f"FRONTEND_SHA256={manifest['frontend_sha256']}")


if __name__ == "__main__":
    main()
