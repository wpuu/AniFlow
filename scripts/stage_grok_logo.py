"""Restore the binary logo from the untouched user-uploaded Grok ZIP.

This helper copies only one explicitly named PNG, never extracts arbitrary ZIP paths.
No execution of archive contents, network, or credentials.
"""
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "aniflow-ai-video-dashboard-grok.zip"
ASSET = "public/images/logo.png"
OUT = ROOT / "apps/studio-candidate-grok/public/images/logo.png"

def main() -> None:
    with ZipFile(ZIP) as z:
        raw = z.read(ASSET)
    if not (1000 <= len(raw) <= 2_000_000) or raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Grok logo PNG is invalid or exceeds safe size")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.is_file() and OUT.read_bytes() != raw:
        raise FileExistsError("Logo differs from source ZIP; refusing overwrite")
    OUT.write_bytes(raw)
    print("PASS_ORIGINAL_GROK_LOGO_STAGED_LOCALLY")

if __name__ == "__main__":
    main()
