#!/usr/bin/env python3
"""Bump patch version in manifest.json."""
from __future__ import annotations
import json, re, sys
from pathlib import Path
MANIFEST = Path(__file__).resolve().parents[1] / "custom_components/kinvia/manifest.json"
def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    version = data.get("version", "1.0.0")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
    if not match:
        print(f"Invalid version format: {version}", file=sys.stderr); return 1
    major, minor, patch = map(int, match.groups())
    new_version = f"{major}.{minor}.{patch + 1}"
    data["version"] = new_version
    MANIFEST.write_text(json.dumps(data, indent=2) + "
", encoding="utf-8")
    print(new_version); return 0
if __name__ == "__main__": raise SystemExit(main())
