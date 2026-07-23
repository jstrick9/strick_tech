#!/usr/bin/env python3
"""Check static frontend API paths against the committed OpenAPI contract."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / 'contracts' / 'openapi.json'
API_LITERAL = re.compile(r"['\"](/api/[A-Za-z0-9_./-]+)")
EXTERNAL_API_PATHS = {'/api/pull'}  # Ollama's API, not an Agentic OS route


def _normalize(path: str) -> str:
    return path.rstrip('/') or '/'


def _matches_contract(reference: str, contract: str) -> bool:
    """Match a concrete frontend path against an OpenAPI templated path."""
    ref_parts = _normalize(reference).strip('/').split('/')
    contract_parts = _normalize(contract).strip('/').split('/')
    if len(ref_parts) != len(contract_parts):
        return False
    return all(
        contract_part.startswith('{') and contract_part.endswith('}') or ref_part == contract_part
        for ref_part, contract_part in zip(ref_parts, contract_parts)
    )


def main() -> None:
    spec = json.loads(SPEC_PATH.read_text(encoding='utf-8'))
    paths = {_normalize(path) for path in spec.get('paths', {})}
    references: dict[str, list[str]] = {}
    for source in (ROOT / 'frontend').rglob('*'):
        if source.suffix not in {'.js', '.jsx', '.html'}:
            continue
        text = source.read_text(encoding='utf-8', errors='ignore')
        for match in API_LITERAL.finditer(text):
            path = _normalize(match.group(1))
            if path in EXTERNAL_API_PATHS:
                continue
            references.setdefault(path, []).append(str(source.relative_to(ROOT)))

    unresolved: dict[str, list[str]] = {}
    for path, sources in references.items():
        if path in paths or any(_matches_contract(path, candidate) for candidate in paths):
            continue
        # A literal may be a prefix of a parameterized endpoint, e.g.
        # /api/agents/ followed by an ID assembled at runtime.
        if not any(candidate.startswith(path + '/') for candidate in paths):
            unresolved[path] = sources

    if unresolved:
        for path, sources in sorted(unresolved.items()):
            print(f'UNRESOLVED {path}: {", ".join(sorted(set(sources)))}')
        raise SystemExit(f'{len(unresolved)} frontend API references are absent from OpenAPI')

    print(f'Validated {len(references)} static frontend API references against {len(paths)} OpenAPI paths')


if __name__ == '__main__':
    main()
