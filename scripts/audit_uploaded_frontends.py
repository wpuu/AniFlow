"""Read-only, ZIP-safe comparison of the two generated AniFlow frontends.

Does not execute archive code, install npm packages, or touch AWS/Agnes.
Prints bounded evidence for human review from the actual uploaded ZIP bytes.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
import sys
from collections import Counter
from pathlib import Path
from zipfile import ZipFile, BadZipFile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = {
    "Claude": "aniflow-ai-video-dashboard-claude.zip",
    "Grok": "aniflow-ai-video-dashboard-grok.zip",
}
SOURCE_SUFFIXES = (".tsx", ".ts", ".jsx", ".js", ".css", ".html", ".vue", ".svelte", ".json", ".md")
SKIP_PARTS = {"node_modules", ".git", ".next", "dist", "build", "__MACOSX", ".venv", "coverage"}
FEATURES = {
    "image_to_video": r"\b(i2v|image.to.video|图生视频|首帧|first.frame)\b",
    "text_to_video": r"\b(t2v|text.to.video|文生视频)\b",
    "first_last_frames": r"(last.frame|尾帧|首尾帧|end.frame)",
    "reference_images": r"(reference.images?|参考图|referenc(e|ing).*(image|frame))",
    "aws_ec2": r"(g6e|EC2|instance.id|AWS|启停实例|云端算力)",
    "gpu_status": r"(gpu.*(vram|utilization|temperature|memory)|显存|GPU利用率)",
    "comfyui": r"(ComfyUI|/prompt\b|/history/|/view\b|/upload/image)",
    "provider_model": r"(provider|供应商|模型服务|MiniMax|Agnes|ZeroGPU|Hugging.?Face)",
    "task_queue": r"(queue|排队|队列|pending|任务状态)",
    "task_recovery": r"(recover|恢复任务|resume|断线|断点|retry|重试)",
    "local_save": r"(showSaveFilePicker|showDirectoryPicker|save.path|保存路径|local.path|本地保存)",
    "download_mp4": r"(download|下载视频|mp4|video/mp4)",
    "projects_shots": r"(shot.list|storyboard|分镜|镜头|episode|项目管理)",
    "cost_budget": r"(credit|cost|pricing|billing|预算|成本|费用)",
    "auto_shutdown": r"(auto.?stop|auto.?shutdown|idle.timeout|空闲关机|自动关闭)",
    "batch_generation": r"(batch|批量|一键生成|multi.task)",
    "history_search": r"(history|历史记录|搜索|筛选|filter)",
    "settings_storage": r"(localStorage|indexedDB|zustand|redux|persist)",
    "real_network_call": r"(fetch\s*\(|axios\.|WebSocket\s*\(|EventSource\s*\(|/api/)",
    "mock_data": r"(mock|fake|simulation|simulate|demo|示例数据|演示模式)",
    "approval_safety": r"(确认|approval|confirm\(|quota|金额上限|危险操作)",
    "editor_shortcuts": r"(onKeyDown|快捷键|shortcut|hotkey)",
    "accessibility": r"(aria-label|role=|tabIndex)",
    "responsive": r"(sm:|md:|lg:|@media|grid-cols)",
    "tests": r"(test\(|describe\(|it\(|playwright|vitest|jest|cypress)",
    "n8n": r"(n8n|webhook|YouTube|TikTok)",
}

def safe_bytes(zf: ZipFile, name: str, max_bytes: int = 800_000) -> bytes | None:
    info = zf.getinfo(name)
    if info.file_size > max_bytes or info.is_dir():
        return None
    return zf.read(info)

def is_source(name: str) -> bool:
    n = name.replace("\\", "/")
    return n.lower().endswith(SOURCE_SUFFIXES) and not any(p in SKIP_PARTS for p in n.split("/"))

def audit(label: str, filename: str) -> dict:
    zippath = ROOT / filename
    zip_sha = hashlib.sha256(zippath.read_bytes()).hexdigest()
    with ZipFile(zippath) as zf:
        infos = zf.infolist()
        bad_names = [i.filename for i in infos if i.filename.startswith("/") or
                     ".." in i.filename.replace("\\", "/").split("/") or
                     posixpath.normpath(i.filename).startswith("../")]
        symlinks = [i.filename for i in infos if (i.external_attr >> 16) & 0o170000 == 0o120000]
        filenames = [i.filename for i in infos if not i.is_dir()]
        sourcefiles = [f for f in filenames if is_source(f)]
        exts = Counter(Path(f).suffix.lower() for f in sourcefiles)
        package = {}
        packages = [f for f in sourcefiles if f.endswith("/package.json") or f == "package.json"]
        for p in packages[:8]:
            try:
                item = json.loads(zf.read(p))
                package[p] = {
                    "name": item.get("name"),
                    "scripts": item.get("scripts"),
                    "dependencies": list((item.get("dependencies") or {}).keys()),
                    "devDependencies": list((item.get("devDependencies") or {}).keys()),
                }
            except (ValueError, UnicodeDecodeError, KeyError):
                package[p] = {"parse_error": True}

        matches = {feature: [] for feature in FEATURES}
        dangerous = []
        source_size = 0
        nonempty_lines = 0
        preview = []
        for file in sourcefiles:
            raw = safe_bytes(zf, file)
            if raw is None:
                continue
            source_size += len(raw)
            text = raw.decode("utf-8", errors="replace")
            lines = text.splitlines()
            nonempty_lines += sum(bool(x.strip()) for x in lines)
            for n, line in enumerate(lines, 1):
                for feature, pattern in FEATURES.items():
                    if re.search(pattern, line, flags=re.IGNORECASE):
                        evidence = matches[feature]
                        if len(evidence) < 5:
                            evidence.append({"file": file, "line": n, "excerpt": line.strip()[:175]})
                if re.search(r"(api[_-]?key|secret|token|accesskey|credential|http://0\.0\.0\.0)", line, flags=re.I):
                    if len(dangerous) < 18:
                        dangerous.append({"file": file, "line": n, "detail": "redacted"})
            if re.search(r"(^|/)(src/)?(App|Dashboard|Main|VideoStudio)\.(tsx|jsx|vue)$", file, re.I):
                preview.append({"file": file, "lines": len(lines),
                                "head": "\n".join(("[REDACTED POTENTIAL SECRET]" if re.search(r"(api[_-]?key|secret|token|credential|accesskey)", line, re.I) else line) for line in lines[:90])[:7000]})
        dirnames = sorted({f.rsplit("/", 1)[0] if "/" in f else "." for f in sourcefiles})
        weighted = sorted(
            [{"file": f, "bytes": zf.getinfo(f).file_size} for f in sourcefiles],
            key=lambda x: -x["bytes"],
        )[:14]
        return {
            "source": label,
            "filename": filename,
            "zip_bytes": zippath.stat().st_size,
            "zip_sha256": zip_sha,
            "entries": len(filenames),
            "uncompressed_bytes": sum(i.file_size for i in infos),
            "suspicious_paths": bad_names[:10],
            "symlinks": symlinks[:10],
            "source_count": len(sourcefiles),
            "source_bytes_examined": source_size,
            "nonempty_source_lines": nonempty_lines,
            "extensions": dict(exts),
            "source_directories": dirnames[:45],
            "source_filenames": sourcefiles[:130],
            "large_source_files": weighted,
            "package_json": package,
            "features": matches,
            "secret_or_credential_related_source_lines": dangerous,
            "main_component_source_excerpt": preview[:4],
        }

def main() -> int:
    results = []
    for label, filename in ARCHIVES.items():
        try:
            results.append(audit(label, filename))
        except (OSError, BadZipFile, ValueError, KeyError) as exc:
            print(f"AUDIT_FAILURE {label} {type(exc).__name__}: {str(exc)[:120]}", file=sys.stderr)
            return 1
    print("BEGIN_ANIFLOW_STATIC_ZIP_COMPARISON")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("END_ANIFLOW_STATIC_ZIP_COMPARISON")
    print("PASS_TWO_UPLOADS_INSPECTED_WITHOUT_RUNNING_UNTRUSTED_CODE")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
