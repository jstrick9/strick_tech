"""
Regression guard for the bundled-asset cache in backend/services/asset_bundle.py.

The served index HTML is cached against the mtime of `index.html` so a dev edit
is picked up without a restart. That cache must ALSO invalidate when the bundle
is rebuilt — the content-hashed <script> filenames change but index.html does
not — otherwise the running server keeps pointing the page at the previous (now
missing) bundle. This test rebuilds a fake bundle and asserts the served HTML
follows without touching index.html.
"""
from __future__ import annotations

import json
import os

from backend.services import asset_bundle


def _setup_dir(tmp_path):
    fd = tmp_path / "frontend"
    (fd / "dist").mkdir(parents=True)
    (fd / "index.html").write_text(
        '<html><head><script src="/static/js/head-mod.js"></script></head>'
        '<body><script src="/static/js/app.js"></script></body></html>',
        encoding="utf-8",
    )
    _write_manifest(fd, ["app.v1.js"], ["pane-v1.js"])
    return fd


def _write_manifest(fd, body_names, chunk_names):
    dist = fd / "dist"
    (dist / "manifest.json").write_text(
        json.dumps(
            {
                "head": "head.js",
                "body": body_names[0],
                "chunk_manifest": chunk_names[0],
            }
        ),
        encoding="utf-8",
    )
    (dist / "head.js").write_text("", encoding="utf-8")
    for name in body_names + chunk_names:
        (dist / name).write_text("", encoding="utf-8")


def test_rebuilt_bundle_is_served_without_touching_index(tmp_path, monkeypatch):
    fd = _setup_dir(tmp_path)
    monkeypatch.setenv("AGENTIC_JS_BUNDLE", "1")

    asset_bundle._cache.clear()
    html1 = asset_bundle.index_html(fd)
    assert "app.v1.js" in html1

    # Simulate a bundle rebuild: dist manifest + files change, index.html does not.
    import time
    time.sleep(0.02)
    _write_manifest(fd, ["app.v2.js"], ["pane-v2.js"])

    html2 = asset_bundle.index_html(fd)
    assert "app.v2.js" in html2, "cache must invalidate when the bundle is rebuilt"
    assert "app.v2.js" not in html1
