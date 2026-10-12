"""Package *only public, allowlisted* AniFlow files into a Node-free Windows test bundle.

The artifact contains the EXISTING 9-Key app, not a new platform. The prebuilt
frontend is tied to a SHA-256 manifest so Windows setup need not run npm.
No .env, credentials, browser state, node_modules or runtime data are copied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "pyproject.toml",
    "version.json",
    "首次安装AniFlow.cmd",
    "启动AniFlow.cmd",
    "一键重启当前AniFlow.cmd",
    "检查更新AniFlow.cmd",
    "scripts/check_aniflow_update_windows.ps1",
    "scripts/restart_aniflow_windows.ps1",
    "scripts/setup_aniflow_windows.ps1",
    "scripts/start_aniflow_windows.ps1",
    "apps/grok-frontend/dist/index.html",
    "content/shotlists/MYCL-001-cat-lapping.json",
    "content/factpacks/MYCL-001-cat-lapping.json",
)
INSTRUCTIONS = """AniFlow 雪所长｜9-Key 视频测试包（非已生成的视频）

1. 解压整个文件夹。需要 Windows、Python 3.11+ 和首次安装时可访问的 Python 包下载源。
2. 双击“首次安装AniFlow.cmd”。前端已由 GitHub CI 预构建，不需 Node/npm。安装及重启都会检查是否有更新，但不会悄悄覆盖旧文件。
3. 更新：双击“检查更新AniFlow.cmd”。若已经在下载文件夹找到官方成功CI的ZIP，则会核验后安装到旁边的新文件夹；若浏览器须登录GitHub，会打开下载页面。\n4. 安装成功后双击新版文件夹的“一键重启当前AniFlow.cmd”，它只结束已确认的旧 AniFlow 服务，核对运行版本再打开浏览器，不清空Key/历史。
   “启动AniFlow.cmd”仍保留兼容。
4. 选择 Agnes Video 2.5 Flash，点击“载入雪所长首镜头 · 5秒”。
5. 在自己可信的浏览器填写Key。Flash当前限时免费，单Key与一键生成全部无需余额确认；付费2.5才提示费用。9条不同Key一键生成将发送9条真实创建请求。
6. 收到完成结果后尽快打开视频链接并保存 MP4；任务可能存在服务器上，网页刷新不等于取消任务。
7. 上游响应超时、无 video_id 的任务仍可能在服务商侧存在，手动重试有重复创建风险。\n8. 下一版不会自动覆盖旧 ZIP；每次到 GitHub PR 最新绿色 CI 下载新的完整Windows包。

请勿在聊天、GitHub Issue、PR、CI 中提供密钥。不要运行旧 v7.0.4 安装器。
本包仅通过无 Key 的自动化验证，不代表已得到 Agnes 真视频。
"""


def build_bundle(root: Path, dest: Path, source_commit: str) -> dict[str, object]:
    if dest.exists():
        raise FileExistsError(f"Bundle output already exists: {dest}")
    if len(source_commit) != 40 or any(c not in "0123456789abcdef" for c in source_commit.lower()):
        raise ValueError("Expected exactly one 40-character Git commit SHA")
    version_path = root / "version.json"
    meta = json.loads(version_path.read_text(encoding="utf-8"))
    app_version = meta.get("app_version")
    release_stage = meta.get("release_stage")
    if not isinstance(app_version, str) or not re.fullmatch(r"0\.[0-9]+\.[0-9]+", app_version):
        raise ValueError("AniFlow version.json needs a pre-release app_version, e.g. 0.32.0")
    if not isinstance(release_stage, str) or not re.fullmatch(r"P0-[0-9]{3}", release_stage):
        raise ValueError("AniFlow release_stage must be P0-NNN")
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    if pyproject.get("project", {}).get("version") != app_version:
        raise ValueError("AniFlow version mismatch between version.json and pyproject.toml")
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
        "app_version": app_version,
        "release_stage": release_stage,
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
    print(f"ANIFlow_VERSION={manifest['app_version']}")
    print(f"RELEASE_STAGE={manifest['release_stage']}")
    print(f"SOURCE_COMMIT={manifest['source_commit']}")
    print(f"FRONTEND_SHA256={manifest['frontend_sha256']}")


if __name__ == "__main__":
    main()
