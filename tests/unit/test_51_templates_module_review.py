"""
Unit Tests — Template Gallery module review (`tests/unit/test_51_templates_module_review.py`)

Regression guards for real defects found during the Templates review:

1. DATA LOSS: scaffolding overwrote preview/ unconditionally. Unsaved work open
   in Studio was destroyed with no warning, no confirmation and no way back —
   the template's NEW content was versioned, but the user's REPLACED content
   never was, so it was genuinely unrecoverable.
2. project_name was collected by the UI, sent on every scaffold, and silently
   did nothing for 11 of the 14 templates (only 3 contain one of the four
   hardcoded placeholder strings).
3. Missing templates returned HTTP 200 with {"ok": false}, so callers doing
   `if (r.ok)` treated "not found" as success.
4. POST /api/templates/scaffold-custom shipped working but unreachable — no UI
   control anywhere called it.
"""

from __future__ import annotations

from pathlib import Path

from backend.routers.templates import TEMPLATES, _apply_project_name, _safe_name, _within_preview

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_PY = (ROOT / 'backend' / 'routers' / 'templates.py').read_text(encoding='utf-8')
GALLERY_JS = (ROOT / 'frontend' / 'js' / '21-template-gallery.js').read_text(encoding='utf-8')


class TestCatalogueIntegrity:
    def test_every_template_has_the_required_fields(self):
        for t in TEMPLATES:
            for field in ('id', 'name', 'category', 'description', 'files', 'tags'):
                assert t.get(field), f'{t.get("id", "?")} is missing {field}'

    def test_template_ids_are_unique(self):
        ids = [t['id'] for t in TEMPLATES]
        assert len(ids) == len(set(ids))

    def test_every_template_ships_at_least_one_file(self):
        # Originally asserted an .html entrypoint, which assumed every template
        # is a web page. Backend starters (e.g. fastapi-service) legitimately
        # ship no HTML at all, so the real invariant is that a template must
        # deliver something.
        for t in TEMPLATES:
            assert t['files'], f'{t["id"]} ships no files'

    def test_web_templates_have_an_html_entrypoint(self):
        """Anything that claims to be previewable in a browser needs HTML."""
        for t in TEMPLATES:
            if t['category'] in ('saas', 'portfolio', 'marketing', 'ecommerce'):
                assert any(f.endswith('.html') for f in t['files']), f'{t["id"]} has no .html file'

    def test_no_template_filename_escapes_the_preview_directory(self):
        for t in TEMPLATES:
            for filename in t['files']:
                assert '..' not in filename and not filename.startswith('/'), f'{t["id"]}: unsafe path {filename}'


class TestOverwriteProtection:
    """Scaffolding must never silently destroy work."""

    def test_scaffold_refuses_to_clobber_without_explicit_opt_in(self):
        assert "'needs_confirmation': True" in TEMPLATES_PY
        assert 'if at_risk and not overwrite:' in TEMPLATES_PY

    def test_conflicting_files_are_named_so_the_ui_can_ask(self):
        assert "'conflicts': at_risk" in TEMPLATES_PY

    def test_replaced_content_is_snapshotted_before_being_overwritten(self):
        assert 'Auto-backup before scaffolding' in TEMPLATES_PY
        # The snapshot must be the PREVIOUS content, not the new template body.
        assert 'previous = target.read_text' in TEMPLATES_PY

    def test_response_reports_what_was_replaced(self):
        assert "'replaced': replaced" in TEMPLATES_PY

    def test_ui_confirms_before_overwriting(self):
        assert 'needs_confirmation' in GALLERY_JS
        assert 'gmConfirm(' in GALLERY_JS
        assert 'Scaffold cancelled' in GALLERY_JS

    def test_ui_only_retries_with_explicit_overwrite(self):
        assert 'postScaffold(true)' in GALLERY_JS
        assert 'postScaffold(false)' in GALLERY_JS


class TestPathContainment:
    def test_paths_inside_preview_are_allowed(self, tmp_path):
        from backend.routers import templates as mod

        assert _within_preview(mod.PREV / 'index.html')

    def test_sibling_directory_sharing_a_prefix_is_rejected(self):
        """`preview_backup/` must not count as being inside `preview/`.

        The old guard used str.startswith(), which treats a sibling directory
        whose name merely starts with the same characters as contained.
        """
        from backend.routers import templates as mod

        sibling = mod.PREV.parent / (mod.PREV.name + '_backup') / 'x.html'
        assert not _within_preview(sibling)

    def test_traversal_is_rejected(self):
        from backend.routers import templates as mod

        assert not _within_preview(mod.PREV / '..' / '..' / 'etc' / 'passwd')


class TestProjectNameSubstitution:
    """Naming a project must have a visible effect on every template."""

    def test_placeholder_templates_still_substitute(self):
        out = _apply_project_name('<h1>YourSaaS</h1>', 'Acme')
        assert 'Acme' in out and 'YourSaaS' not in out

    def test_templates_without_a_placeholder_fall_back_to_title_and_h1(self):
        src = '<html><head><title>Todo App</title></head><body><h1>Todo App</h1></body></html>'
        out = _apply_project_name(src, 'Acme Tracker')
        assert '<title>Acme Tracker</title>' in out
        assert '<h1>Acme Tracker</h1>' in out

    def test_every_builtin_template_responds_to_a_project_name(self):
        """Previously 11 of 14 ignored project_name entirely."""
        unaffected = []
        for t in TEMPLATES:
            for filename, content in t['files'].items():
                if not filename.endswith('.html'):
                    continue
                if _apply_project_name(content, 'ZzUniqueName') == content:
                    unaffected.append(t['id'])
        assert not unaffected, f'project_name still has no effect on: {unaffected}'

    def test_empty_name_leaves_content_untouched(self):
        src = '<title>Todo App</title>'
        assert _apply_project_name(src, '') == src

    def test_project_name_cannot_inject_markup(self):
        malicious = _safe_name('<script>alert(1)</script>Evil')
        out = _apply_project_name('<title>x</title>', malicious)
        assert '<script>' not in out


class TestNotFoundStatusCodes:
    """A missing template is a 404, not a 200 with ok:false."""

    def test_detail_preview_and_scaffold_all_404(self):
        assert TEMPLATES_PY.count('status_code=404') >= 3


class TestSaveCurrentWorkIsReachable:
    """scaffold-custom shipped working but no UI control called it."""

    def test_ui_exposes_a_save_control(self):
        assert 'saveWorkAsTemplate' in GALLERY_JS
        assert 'Save Current Work' in GALLERY_JS

    def test_it_calls_the_real_endpoint(self):
        assert "fetch('/api/templates/scaffold-custom'" in GALLERY_JS

    def test_the_function_is_exported_for_the_inline_handler(self):
        assert 'window.saveWorkAsTemplate = saveWorkAsTemplate;' in GALLERY_JS
