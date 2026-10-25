"""Read-only Wan image-to-video reference asset technical preflight.

No dependencies, provider API calls, file mutations or credentials. Read only the
two versioned character assets. A valid metadata report NEVER proves visual
identity, ownership, commercial permission, or output quality.

Source: official Wan2.6 image-to-video API documentation (2026-10-11).
Initial image: JPEG/PNG/BMP/WEBP (PNG alpha unsupported); each side 240..8000 px,
max 20 MiB. Output ratio follows the initial image rather than the text prompt.
"""
from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "assets/character/agnes-felt-test-frame.png",
    "assets/character/xue-director-felt-concept.png",
)
MAX_BYTES = 20 * 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
TARGET_ASPECT = 9 / 16


def check_png(path: Path) -> dict:
    result = {
        "path": path.relative_to(ROOT).as_posix(),
        "model": "wan2.6-i2v-flash",
        "provider_api_requests": 0,
        "changes_written": 0,
        "human_visual_approval": False,
        "commercial_rights_verified": False,
    }
    blockers = []
    try:
        size = path.stat().st_size
        with path.open("rb") as file:
            header = file.read(33)
            file.seek(0)
            digest = hashlib.file_digest(file, "sha256").hexdigest()
    except OSError:
        return {**result, "result": "BLOCKED", "blockers": ["Asset not readable"]}

    result["size_bytes"] = size
    result["sha256"] = digest
    if size > MAX_BYTES:
        blockers.append("Larger than Wan2.6 20 MiB maximum")
    if (
        len(header) != 33
        or header[:8] != PNG_MAGIC
        or struct.unpack(">I", header[8:12])[0] != 13
        or header[12:16] != b"IHDR"
        or zlib.crc32(header[12:29]) != struct.unpack(">I", header[29:33])[0]
    ):
        return {**result, "result": "BLOCKED", "blockers": blockers + ["Invalid PNG IHDR"]}

    width, height, depth, kind, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", header[16:29]
    )
    result.update({
        "width": width, "height": height,
        "png_bit_depth": depth, "png_color_type": kind,
        "source_aspect_ratio": round(width / height, 5) if height else None,
        "has_alpha_channel": kind in (4, 6),
    })
    if min(width, height) < 240 or max(width, height) > 8000:
        blockers.append("Wan2.6 input dimensions must be 240..8000 on both sides")
    if kind in (4, 6):
        blockers.append("PNG has alpha; Wan2.6 input PNG alpha is unsupported")
    if depth not in (8, 16) or kind not in (0, 2, 3, 4, 6):
        blockers.append("Unsupported/unexpected PNG depth or color type")
    if compression != 0 or filtering != 0 or interlace not in (0, 1):
        blockers.append("Unexpected PNG compression/filter/interlace encoding")
    if height <= width:
        blockers.append("Reference image is not portrait")
    elif abs(width / height - TARGET_ASPECT) > 0.01:
        blockers.append("Reference image is not close to 9:16; output aspect follows image")

    result["input_basics_pass"] = not any(
        "20 MiB" in b or "input dimensions" in b or "alpha" in b
        or "PNG" in b for b in blockers
    )
    result["portrait_9_16_technical_ready"] = not blockers
    result["blockers"] = blockers
    result["result"] = (
        "TECHNICALLY_COMPATIBLE_VISUAL_REVIEW_PENDING"
        if not blockers else "NEEDS_REFERENCE_PREPARATION"
    )
    return result


def main() -> int:
    reports = [check_png(ROOT / path) for path in FILES]
    print(json.dumps({
        "phase": "P0-019_WAN_REFERENCE_ASSET_AUDIT",
        "trusted_source": "git-versioned assets only",
        "provider_calls": 0,
        "video_generated": False,
        "assets": reports,
        "recommendation": (
            "Visual character approval, image rights and provider test still required; "
            "if geometry/alpha is unsuitable, prepare a reviewed 9:16 opaque source image "
            "before any paid Wan call."
        ),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
