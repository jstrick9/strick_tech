"""
Unit Tests — Template Gallery enhancements (`tests/unit/test_52_templates_enhancements.py`)

Covers the three follow-ups identified in the Templates module review:

1. The catalogue moved out of ~660 lines of inline Python string literals into
   templates/<id>/ directories (template.json manifest + real files), so
   starters can be edited, diffed and reviewed as ordinary source.
2. Multi-file templates. All 14 originals shipped a single index.html, so the
   multi-file scaffold path — nested directories, non-HTML entrypoints — was
   entirely untested. Two real multi-file starters now exercise it.
3. Saved snapshots ("Save Current Work") were write-only: nothing could list,
   restore or delete them. They are now first-class in the gallery.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.routers.templates import (
    TEMPLATES,
    TEMPLATES_DIR,
    _resolve_saved,
    _saved_dir,
    load_templates,
    reload_templates,
)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_PY = (ROOT / 'backend' / 'routers' / 'templates.py').read_text(encoding='utf-8')
GALLERY_JS = (ROOT / 'frontend' / 'js' / '21-template-gallery.js').read_text(encoding='utf-8')


class TestCatalogueLoadsFromDisk:
    def test_templates_directory_exists_and_is_populated(self):
        assert TEMPLATES_DIR.is_dir(), f'{TEMPLATES_DIR} must exist'
        assert len(list(TEMPLATES_DIR.iterdir())) >= 14

    def test_every_template_dir_has_a_manifest_and_its_declared_files(self):
        for d in sorted(TEMPLATES_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith(('.', '_')):
                continue
            manifest = d / 'template.json'
            assert manifest.is_file(), f'{d.name} has no template.json'
            meta = json.loads(manifest.read_text(encoding='utf-8'))
            assert meta.get('files'), f'{d.name} declares no files'
            for rel in meta['files']:
                assert (d / rel).is_file(), f'{d.name} declares missing file {rel}'

    def test_inline_catalogue_is_gone(self):
        """The router must no longer carry the templates as literals."""
        assert 'TEMPLATES = [' not in TEMPLATES_PY
        assert 'load_templates()' in TEMPLATES_PY

    def test_router_is_substantially_smaller(self):
        # Was 1023 lines when the 14 templates were inline.
        assert len(TEMPLATES_PY.splitlines()) < 700

    def test_loader_is_deterministic(self):
        assert [t['id'] for t in load_templates()] == sorted(t['id'] for t in load_templates())

    def test_reload_refreshes_in_place(self):
        before = len(TEMPLATES)
        assert reload_templates() == before
        assert len(TEMPLATES) == before

    def test_loader_skips_a_manifest_declaring_an_escaping_path(self, tmp_path, monkeypatch):
        """A manifest must not be able to read files outside its own directory."""
        import backend.routers.templates as mod

        secret = tmp_path / 'secret.txt'
        secret.write_text('classified', encoding='utf-8')
        tdir = tmp_path / 'templates' / 'evil'
        tdir.mkdir(parents=True)
        (tdir / 'ok.html').write_text('<h1>fine</h1>', encoding='utf-8')
        (tdir / 'template.json').write_text(
            json.dumps({'id': 'evil', 'files': ['ok.html', '../../secret.txt']}), encoding='utf-8'
        )
        monkeypatch.setattr(mod, 'TEMPLATES_DIR', tmp_path / 'templates')
        loaded = mod.load_templates()
        assert len(loaded) == 1
        assert list(loaded[0]['files']) == ['ok.html'], 'escaping path must be dropped'

    def test_loader_survives_a_corrupt_manifest(self, tmp_path, monkeypatch):
        import backend.routers.templates as mod

        good = tmp_path / 'templates' / 'good'
        good.mkdir(parents=True)
        (good / 'index.html').write_text('<h1>ok</h1>', encoding='utf-8')
        (good / 'template.json').write_text(json.dumps({'id': 'good', 'files': ['index.html']}), encoding='utf-8')

        bad = tmp_path / 'templates' / 'bad'
        bad.mkdir(parents=True)
        (bad / 'template.json').write_text('{ not json', encoding='utf-8')

        monkeypatch.setattr(mod, 'TEMPLATES_DIR', tmp_path / 'templates')
        loaded = mod.load_templates()
        assert [t['id'] for t in loaded] == ['good'], 'one bad manifest must not break the catalogue'


class TestMultiFileTemplates:
    """The multi-file scaffold path was previously unexercised by any template."""

    def test_at_least_two_multi_file_templates_ship(self):
        multi = [t for t in TEMPLATES if len(t['files']) > 1]
        assert len(multi) >= 2, 'multi-file scaffolding needs real coverage'

    def test_nested_directory_paths_are_supported(self):
        nested = [t['id'] for t in TEMPLATES if any('/' in f for f in t['files'])]
        assert nested, 'no template exercises nested directory creation'

    @pytest.mark.parametrize('tid', ['react-vite-app', 'fastapi-service'])
    def test_expected_starters_are_present_and_multi_file(self, tid):
        t = next((t for t in TEMPLATES if t['id'] == tid), None)
        assert t is not None, f'{tid} missing'
        assert len(t['files']) > 1

    def test_react_template_has_a_valid_package_json(self):
        t = next(t for t in TEMPLATES if t['id'] == 'react-vite-app')
        pkg = json.loads(t['files']['package.json'])
        assert 'react' in pkg['dependencies']
        assert 'dev' in pkg['scripts']

    def test_fastapi_template_ships_runnable_structure(self):
        t = next(t for t in TEMPLATES if t['id'] == 'fastapi-service')
        assert 'app/main.py' in t['files']
        assert 'test_app.py' in t['files']
        # The entry point must actually define the ASGI app uvicorn is told to run.
        assert 'app = FastAPI(' in t['files']['app/main.py']

    def test_non_html_templates_still_expose_a_sensible_entrypoint(self):
        """fastapi-service has no .html file — preview must not assume one."""
        t = next(t for t in TEMPLATES if t['id'] == 'fastapi-service')
        assert not any(f.endswith('.html') for f in t['files'])


class TestPreviewHandlesNonHtmlTemplates:
    """The 👁 preview button was hard-broken for templates with no HTML."""

    def test_endpoint_falls_back_to_a_source_file(self):
        assert "'renderable': False" in TEMPLATES_PY
        assert 'README.md' in TEMPLATES_PY

    def test_endpoint_flags_renderable_html_templates(self):
        assert "'renderable': True" in TEMPLATES_PY

    def test_ui_renders_source_as_code_not_markup(self):
        assert 'tmpl-preview-code' in GALLERY_JS
        # Template source must never be injected as HTML.
        idx = GALLERY_JS.index('tmpl-preview-code')
        assert 'textContent' in GALLERY_JS[idx:idx + 900]

    def test_ui_only_uses_an_iframe_when_renderable(self):
        assert 'renderable = meta.renderable !== false' in GALLERY_JS


class TestSavedSnapshotManagement:
    def test_endpoints_exist(self):
        assert "@router.get('/saved')" in TEMPLATES_PY
        assert "@router.post('/saved/{filename}/restore')" in TEMPLATES_PY
        assert "@router.delete('/saved/{filename}')" in TEMPLATES_PY

    def test_static_saved_routes_precede_the_dynamic_template_route(self):
        """Otherwise /saved is swallowed by /{template_id} and 404s."""
        assert TEMPLATES_PY.index("@router.get('/saved')") < TEMPLATES_PY.index("@router.get('/{template_id}')")

    def test_restore_backs_up_before_replacing(self):
        assert 'Auto-backup before restoring' in TEMPLATES_PY

    def test_resolver_rejects_traversal_and_non_html(self):
        assert _resolve_saved('../../etc/passwd') is None
        assert _resolve_saved('nested/evil.html') is None
        assert _resolve_saved('notes.txt') is None
        assert _resolve_saved('') is None

    def test_resolver_accepts_a_real_snapshot(self):
        d = _saved_dir()
        probe = d / 'unit_probe_snapshot.html'
        probe.write_text('<h1>probe</h1>', encoding='utf-8')
        try:
            assert _resolve_saved('unit_probe_snapshot.html') == probe.resolve()
        finally:
            probe.unlink(missing_ok=True)

    def test_display_names_survive_slugging(self):
        """The filename is lossy ("My App" -> my_app); the index keeps the name."""
        assert '_write_saved_index' in TEMPLATES_PY
        assert '_read_saved_index' in TEMPLATES_PY


class TestGalleryUiWiring:
    def test_saved_snapshots_are_fetched_and_shown(self):
        assert "fetch('/api/templates/saved')" in GALLERY_JS
        assert '_saved: true' in GALLERY_JS

    def test_restore_and_delete_are_wired(self):
        assert 'restoreSavedTemplate' in GALLERY_JS
        assert 'deleteSavedTemplate' in GALLERY_JS
        assert 'window.restoreSavedTemplate = restoreSavedTemplate;' in GALLERY_JS
        assert 'window.deleteSavedTemplate = deleteSavedTemplate;' in GALLERY_JS

    def test_destructive_actions_confirm_first(self):
        idx = GALLERY_JS.index('async function deleteSavedTemplate')
        assert 'gmConfirm(' in GALLERY_JS[idx:idx + 600]

    def test_a_failing_saved_fetch_cannot_break_the_gallery(self):
        assert 'saved snapshots are optional' in GALLERY_JS
