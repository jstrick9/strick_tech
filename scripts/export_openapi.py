#!/usr/bin/env python3
"""Export the FastAPI OpenAPI document from the application source."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import app
from backend.version import VERSION

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'contracts' / 'openapi.json'


def main() -> None:
    spec = app.openapi()
    spec.setdefault('info', {})['version'] = VERSION
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(spec, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'Exported {len(spec.get("paths", {}))} paths to {OUTPUT}')


if __name__ == '__main__':
    main()
