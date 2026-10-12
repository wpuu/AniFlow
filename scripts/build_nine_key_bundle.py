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
    "scripts/aniflow_shared_runtime.ps1",
    "scripts/aniflow_runtime_probe.py",
    "scripts/start_aniflow_windows.ps1",
    "apps/grok-frontend/dist/index.html",
    "content/shotlists/MYCL-001-cat-lapping.json",
    "content/factpacks/MYCL-001-cat-lapping.json",
)
INSTRUCTIONS = """AniFlow 雪所长｜Windows 9-Key 测试包（不含已生成视频）

1. 只下载 PR #2 最新绿色 CI 的完整 Windows Artifact，解压到独立新文件夹，不与旧版本混合。
2. 从旧版首次过渡到 v0.34.1 时，会在本机 LOCALAPPDATA\\AniFlow\\python-env 建立一个共享 Python 依赖环境（可能需要最后一次下载依赖）。
3. 之后所有 AniFlow 版本共用这份环境。Python 依赖清单没变时，安装和启动都会跳过 pip；只有依赖变化或环境损坏才重新安装。
4. 请从新目录启动或重启。新版从当前目录 src 加载业务代码，核验版本号、Git SHA 和前端哈希；不会从旧版本读取旧业务代码。
5. 不删除旧 .venv、不清空浏览器内的9条Key与历史。提交视频请求期间不要重启；关闭本机服务不会取消Agnes上游已受理的任务。
6. 如果返回 HTTP503 / video_queue_full，这是 Agnes 免费视频上游共享 GPU 队列容量不足；多次安装或并发发送9条Key不能增加上游算力。
7. “检查更新AniFlow.cmd”只负责查找并校验官方成功CI安装包，不上传Key、不擅自提交视频生成任务。
8. 当前工具链通过无个人凭据的模拟测试，不代表免费 Agnes 真实生成已成功。

请勿向聊天、PR、Issue、公开CI粘贴密钥或带有密钥的截图。
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
