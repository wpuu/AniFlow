"""Safely inspect/extract source files from the user-uploaded UI ZIP candidates.

Used only in isolated GitHub Actions to compare, never to deploy or connect services.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = {
    "Grok": "aniflow-ai-video-dashboard-grok.zip",
    "Claude": "aniflow-ai-video-dashboard-claude.zip",
}
def members(z: ZipFile):
    for item in z.infolist():
        p = PurePosixPath(item.filename)
        if not item.filename or p.is_absolute() or ".." in p.parts:
            raise ValueError("Unsafe archive member")
        if (item.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError("Symlink disallowed")
        if item.file_size > 2_000_000:
            raise ValueError("Oversized individual archive entry")
        yield item, p

def main():
    a = argparse.ArgumentParser()
    a.add_argument("--export-text", action="store_true")
    a.add_argument("--extract", choices=["Grok", "Claude"])
    a.add_argument("--output", type=Path)
    args = a.parse_args()
    if args.export_text:
        with ZipFile(ROOT / ARCHIVES["Grok"]) as z:
            print("BEGIN_GROK_SOURCE_TRANSFER")
            for info, path in members(z):
                print("ARCHIVE_META " + json.dumps({"path":str(path),"bytes":info.file_size,"is_dir":info.is_dir()},ensure_ascii=False))
                if info.is_dir() or not (str(path).endswith((".tsx",".ts",".jsx",".js",".css",".html",".json",".md"))):
                    continue
                text = z.read(info).decode("utf-8")
                for i in range(0,len(text),7000):
                    print("ZIPTEXT "+json.dumps({"path":str(path),"seq":i//7000,"data":text[i:i+7000]},ensure_ascii=False))
            print("END_GROK_SOURCE_TRANSFER")
    elif args.extract:
        if not args.output:
            raise ValueError("--output is required with --extract")
        dest = args.output.resolve()
        dest.mkdir(parents=True, exist_ok=True)
        with ZipFile(ROOT / ARCHIVES[args.extract]) as z:
            for info, path in members(z):
                file = dest.joinpath(*path.parts)
                if not file.resolve().is_relative_to(dest):
                    raise ValueError("Unsafe member path")
                if info.is_dir():
                    file.mkdir(parents=True,exist_ok=True)
                else:
                    file.parent.mkdir(parents=True,exist_ok=True)
                    file.write_bytes(z.read(info))
        print("PASS_SAFELY_EXTRACTED_"+args.extract.upper())
    else:
        a.error("Choose --export-text or --extract")
if __name__ == "__main__":
    main()
