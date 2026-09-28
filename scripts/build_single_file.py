"""Generate the single-file Windows launcher from QueueTest.ps1.

The owner could not keep a .bat and a .ps1 together: the launcher reported
"QueueTest.ps1 not found in this folder". Two files is one file too many, so
the shipped artifact is a polyglot: cmd.exe runs the header and stops at
`exit /b`, never parsing the PowerShell (or the Chinese) below it, while the
header itself re-reads the file as UTF-8 and executes the part after the
marker. One download, double-click, done.

QueueTest.ps1 stays the source of truth. Run this after editing it:

    python scripts/build_single_file.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "QueueTest.ps1"
TARGET = HERE / "队列测试.bat"

# Split so the literal never appears twice in the header; the loader uses
# LastIndexOf, which must land on the real section start.
MARKER = "#PSBEGIN" + "#"

# The parameter block cannot survive Invoke-Expression, so it becomes plain
# assignments and the Watch switch becomes an interactive prompt.
DEFAULTS = """$Rounds   = 3
$Interval = 20
$Seconds  = 8
$Watch    = $false
$ApiBase  = "https://apihub.agnes-ai.com/v1"
$ApiRoot  = "https://apihub.agnes-ai.com"
"""

MODE_PROMPT = """# ---------------------------------------------------------------- 选模式
Write-Host "选哪种跑法？" -ForegroundColor White
Write-Host "  1 = 快速测 3 轮，先看看情况" -ForegroundColor DarkGray
Write-Host "  2 = 挂机模式，每 20 秒一轮，一直蹲到出结论（推荐）" -ForegroundColor DarkGray
Write-Host ""
$mode = Read-Host "输入 1 或 2（直接回车 = 2）"
if ("$mode".Trim() -eq "1") { $Watch = $false } else { $Watch = $true }
Write-Host ""

"""

KEY_SECTION = "# ---------------------------------------------------------------- 收集 Key"

HEADER = (
    "@echo off\r\n"
    "chcp 65001 >nul\r\n"
    "title AniFlow Queue Test\r\n"
    "powershell -NoProfile -ExecutionPolicy Bypass -Command "
    "\"$ScriptDir='%~dp0';$t=[IO.File]::ReadAllText('%~f0',[Text.Encoding]::UTF8);"
    "$m='#PSBEGIN'+'#';iex $t.Substring($t.LastIndexOf($m)+$m.Length)\"\r\n"
    "echo.\r\n"
    "pause\r\n"
    "exit /b\r\n"
    f"{MARKER}\r\n"
)


def build() -> str:
    ps = SOURCE.read_text(encoding="utf-8-sig")

    ps, n = re.subn(r"param\(\n(?:.*\n)*?\)\n", DEFAULTS, ps, count=1)
    if n != 1:
        sys.exit("could not find the top-level param block")
    if "[switch]$Watch" in ps:
        sys.exit("top-level param block survived the rewrite")
    if "param([string[]]$Keys" not in ps:
        sys.exit("the Invoke-Round param block was removed by mistake")

    # The .bat's own `pause` keeps the window open, and it does so even when
    # PowerShell fails outright, which the in-script wait could never do.
    ps = ps.replace("    Wait-Key; exit 1", "    exit 1")
    ps = ps.replace(
        'Write-Host "把上面这些内容截图发我就行。" -ForegroundColor White\nWait-Key',
        'Write-Host "把上面这些内容截图发我就行。" -ForegroundColor White',
    )
    ps = ps.replace("Wait-Key\n", "")
    if "Wait-Key" in ps.replace("function Wait-Key", ""):
        sys.exit("a Wait-Key call survived; the window would wait twice")

    if KEY_SECTION not in ps:
        sys.exit("could not find the key-collection section")
    ps = ps.replace(KEY_SECTION, MODE_PROMPT + KEY_SECTION, 1)

    return ps


def main() -> None:
    ps = build()
    # No BOM: cmd.exe does not understand one, and the loader decodes UTF-8
    # explicitly, so the Chinese survives either way.
    TARGET.write_bytes(HEADER.encode("utf-8") + ps.replace("\n", "\r\n").encode("utf-8"))
    print(f"wrote {TARGET.name} ({TARGET.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
