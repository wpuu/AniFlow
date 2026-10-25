"""Read selected source contents from the actual uploaded candidate ZIPs, safely.

No extraction to disk, no code execution, no secret values.
"""
import json
import re
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = {
  "Claude": {
    "archive": "aniflow-ai-video-dashboard-claude.zip",
    "paths": ["src/App.tsx", "src/components/CreatePanel.tsx", "src/components/TaskManager.tsx",
              "src/components/TaskCard.tsx", "src/components/ModelStatusBar.tsx",
              "src/data/models.ts", "src/types.ts", "src/components/Header.tsx"],
  },
  "Grok": {
    "archive": "aniflow-ai-video-dashboard-grok.zip",
    "paths": ["src/App.tsx", "src/hooks/useTaskEngine.ts", "src/components/CreatePanel.tsx",
              "src/components/TaskBoard.tsx", "src/components/TaskCard.tsx",
              "src/components/PlayerModal.tsx", "src/data.ts", "src/types.ts", "src/components/Header.tsx"],
  },
}
MASK = re.compile(r"(api[_-]?key|secret|bearer\s|token\s*[:=]|password|accesskey)", re.I)
def main():
  items = {}
  for name, record in FILES.items():
    with ZipFile(ROOT / record["archive"]) as z:
      sources = {}
      for file in record["paths"]:
        text = z.read(file).decode("utf-8")
        lines = text.splitlines()
        safe = [(line if not MASK.search(line) else "[REDACTED POTENTIAL SECRET]")
                for line in lines]
        sources[file] = {"lines": len(lines), "text": "\n".join(safe)[:16_000]}
      items[name] = sources
  print("BEGIN_CLAUDE_GROK_UI_DETAILS")
  print(json.dumps(items, ensure_ascii=False))
  print("END_CLAUDE_GROK_UI_DETAILS")
  print("PASS_DETAILED_SOURCE_INSPECTION_NO_CODE_EXECUTION")
if __name__ == "__main__":
  main()
