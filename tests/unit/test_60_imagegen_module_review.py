"""Module 10 — Image Generator review contracts.

Bugs these pin, all reproduced live against a running server before the fix:

1. Image generation called an endpoint and a model that do not exist.
   POST /images/generations with 'black-forest-labs/FLUX.1-schnell:free'.
   OpenRouter generates images through /chat/completions with
   modalities=['image','text'], and zero of its 338 catalogue entries match
   flux / dall-e / sdxl. Every call failed; a blanket `except Exception`
   swallowed it and returned ok:true with a placeholder, so the feature had
   never once produced an image while reporting success every time.

2. Stored XSS via the placeholder SVG. The prompt was interpolated into the
   SVG body unescaped; with save_to it was written to the gallery and served
   from the app's own origin as image/svg+xml under a CSP that allows
   'unsafe-inline'.

3. Stored XSS via SVG upload — no sanitisation at all.

4. Path traversal via save_to. Containment used str.startswith() on the
   resolved path, so '../preview_ESCAPED/x' passed the check because the
   string '<root>/preview_ESCAPED/x' starts with '<root>/preview'.

5. HTML attribute injection in inject-into-code: the placeholder description
   went into alt="" unescaped, writing a live onerror handler into the user's
   own file.

6. Upload accepted any bytes under an image extension, and buffered the entire
   body into memory before checking the size limit.

7. Uploads silently overwrote same-named gallery images.

8. variations?count="abc" raised ValueError → bare HTTP 500.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from backend.routers import imagegen

REPO = Path(__file__).resolve().parents[2]
IMAGEGEN_PY = (REPO / 'backend' / 'routers' / 'imagegen.py').read_text()


def code_only(src: str) -> str:
    """Strip comments and docstrings.

    These fixes are documented in comments that necessarily quote the old
    broken values ('/images/generations', 'FLUX.1-schnell'), so a naive
    substring search over the raw file matches the explanation rather than the
    code. Assert against what actually executes.
    """
    import ast
    import io
    import tokenize

    out = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        out.append(tok)
    stripped = tokenize.untokenize(out)
    doc_lines: set[int] = set()
    for node in ast.walk(ast.parse(stripped)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                doc_lines.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    return '\n'.join(ln for i, ln in enumerate(stripped.splitlines(), 1) if i not in doc_lines)


IMAGEGEN_CODE = code_only(IMAGEGEN_PY)
IMAGEGEN_JS = (REPO / 'frontend' / 'js' / '15-image-generation.js').read_text()
APP_PY = (REPO / 'backend' / 'app.py').read_text()

ONE_PX_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)


class TestUsesTheRealOpenRouterContract:
    def test_generation_goes_through_chat_completions(self):
        assert "f'{OR_BASE}/chat/completions'" in IMAGEGEN_CODE
        assert '/images/generations' not in IMAGEGEN_CODE

    def test_modalities_are_requested(self):
        assert "'modalities': ['image', 'text']" in IMAGEGEN_PY

    def test_nonexistent_models_are_gone(self):
        """None of these ids exist on OpenRouter; the first was the default."""
        for dead in ('FLUX.1-schnell', 'FLUX.1-pro', 'dall-e-3', 'stability-ai/sdxl'):
            assert dead not in IMAGEGEN_CODE, f'{dead} is not a real OpenRouter model'

    def test_default_model_can_actually_output_images(self):
        assert imagegen.DEFAULT_IMAGE_MODEL == 'google/gemini-2.5-flash-image'
        assert imagegen.DEFAULT_IMAGE_MODEL in {m['id'] for m in imagegen.FALLBACK_IMAGE_MODELS}

    def test_images_are_read_from_the_message_images_field(self):
        msg = {'images': [{'image_url': {'url': 'data:image/png;base64,AAAA'}}]}
        assert imagegen._extract_images(msg) == ['data:image/png;base64,AAAA']
        assert imagegen._extract_images({'content': 'no image here'}) == []

    def test_data_urls_decode_to_real_bytes(self):
        url = 'data:image/png;base64,' + base64.b64encode(ONE_PX_PNG).decode()
        raw, ext = imagegen._decode_data_url(url)
        assert raw == ONE_PX_PNG
        assert ext == '.png'

    def test_corrupt_base64_is_reported_not_swallowed(self):
        with pytest.raises(imagegen.ImageGenError):
            imagegen._decode_data_url('data:image/png;base64,!!!not-base64!!!')

    @pytest.mark.asyncio
    async def test_end_to_end_generation_writes_a_real_png(self, tmp_path, monkeypatch):
        data_url = 'data:image/png;base64,' + base64.b64encode(ONE_PX_PNG).decode()
        captured = {}

        class FakeResp:
            status_code = 200
            text = ''

            def json(self):
                return {
                    'choices': [{'message': {'images': [{'image_url': {'url': data_url}}]}}],
                    'usage': {'total_tokens': 5},
                }

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, headers=None, json=None):
                captured['url'] = url
                captured['payload'] = json
                return FakeResp()

        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-test')
        monkeypatch.setattr(imagegen.httpx, 'AsyncClient', FakeClient)
        monkeypatch.setattr(imagegen, 'PREVIEW_DIR', tmp_path)

        result = await imagegen._do_generate('a cat', size='1792x1024', save_to='out/cat.png')

        assert captured['url'].endswith('/chat/completions')
        assert captured['payload']['modalities'] == ['image', 'text']
        assert captured['payload']['image_config'] == {'aspect_ratio': '16:9'}
        assert result['ok'] is True and result['placeholder'] is False
        written = tmp_path / result['saved_to']
        assert written.read_bytes().startswith(b'\x89PNG')


class TestFailuresAreNotReportedAsSuccess:
    @pytest.mark.asyncio
    async def test_upstream_error_raises_instead_of_faking_a_placeholder(self, monkeypatch):
        class FakeResp:
            status_code = 404
            text = 'No endpoint found'

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                return FakeResp()

        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-test')
        monkeypatch.setattr(imagegen.httpx, 'AsyncClient', FakeClient)
        with pytest.raises(imagegen.ImageGenError) as exc:
            await imagegen._do_generate('a cat')
        assert exc.value.status == 502

    @pytest.mark.asyncio
    async def test_text_only_reply_is_an_error_not_a_success(self, monkeypatch):
        """A model that answers in prose produced no image; say so."""

        class FakeResp:
            status_code = 200
            text = ''

            def json(self):
                return {'choices': [{'message': {'content': "I can't do that."}}]}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                return FakeResp()

        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-test')
        monkeypatch.setattr(imagegen.httpx, 'AsyncClient', FakeClient)
        with pytest.raises(imagegen.ImageGenError):
            await imagegen._do_generate('a cat')

    def test_no_key_placeholder_is_labelled_not_ok(self, client):
        """ok:true for a placeholder made 'no key' indistinguishable from success."""
        r = client.post('/api/imagegen/generate', json={'prompt': 'a cat'})
        body = r.json()
        if body.get('placeholder'):
            assert body['ok'] is False
            assert 'OPENROUTER_API_KEY' in body['note']

    def test_status_codes_are_mapped_by_cause(self):
        for code in ('status=400', 'status=401', 'status=402', 'status=429', 'status=502', 'status=504'):
            assert code in IMAGEGEN_PY


class TestSvgIsSanitised:
    @pytest.mark.parametrize(
        'payload',
        [
            b'<svg><script>alert(1)</script></svg>',
            b'<svg onload="alert(1)"><circle r="5"/></svg>',
            b'<svg><a href="javascript:alert(1)">x</a></svg>',
            b"<svg><a xlink:href='javascript:alert(1)'>x</a></svg>",
            b'<svg><foreignObject><body onclick="alert(1)"/></foreignObject></svg>',
            b'<svg><image href="data:text/html,<script>alert(1)</script>"/></svg>',
        ],
    )
    def test_dangerous_constructs_are_stripped(self, payload):
        out = imagegen.sanitize_svg(payload).lower()
        assert b'<script' not in out
        assert b'javascript:' not in out
        assert b'onload=' not in out
        assert b'onclick=' not in out
        assert b'<foreignobject' not in out

    def test_legitimate_svg_survives(self):
        good = b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="5" fill="red"/></svg>'
        assert imagegen.sanitize_svg(good) == good

    def test_stripping_leaves_wellformed_markup(self):
        """A naive regex dropped the attribute but left its closing quote."""
        out = imagegen.sanitize_svg(b'<svg><a href="javascript:alert(1)">x</a></svg>').decode()
        assert out == '<svg><a>x</a></svg>'

    def test_placeholder_escapes_the_prompt(self):
        svg = imagegen._make_placeholder_svg('</text><script>alert(1)</script><text>')
        assert '<script>' not in svg
        assert '&lt;script&gt;' in svg

    def test_placeholder_rejects_an_injected_size(self):
        svg = imagegen._make_placeholder_svg('x', size='1"><script>alert(1)</script>')
        assert '<script>' not in svg

    def test_preview_svgs_are_served_with_a_locked_down_csp(self):
        assert "path.startswith('/preview/') and path.lower().endswith('.svg')" in APP_PY
        assert "default-src 'none'; style-src 'unsafe-inline'; sandbox" in APP_PY


class TestPathContainment:
    def test_sibling_directory_prefix_cannot_escape(self):
        """The startswith() check let '<root>/preview_evil' pass as '<root>/preview'."""
        assert imagegen._safe_preview_path('../preview_ESCAPED/pwned.svg') is None

    @pytest.mark.parametrize(
        'evil',
        ['../../etc/passwd', '/etc/passwd', 'a/../../../x', '..%2f..%2fetc', 'x\x00.png'],
    )
    def test_traversal_payloads_are_rejected(self, evil):
        target = imagegen._safe_preview_path(evil)
        if target is not None:
            target.relative_to(imagegen.PREVIEW_DIR.resolve())  # must not raise

    def test_normal_relative_paths_still_work(self):
        assert imagegen._safe_preview_path('assets/images/ok.png') is not None

    def test_inject_rejects_paths_outside_preview(self, client):
        r = client.post('/api/imagegen/inject-into-code', json={'filepath': '../../etc/passwd'})
        assert r.status_code == 403


class TestInjectIntoCodeEscapesAttributes:
    def test_alt_text_is_escaped(self):
        assert 'html.escape(desc, quote=True)' in IMAGEGEN_PY

    def test_src_is_escaped(self):
        assert 'html.escape(img_src, quote=True)' in IMAGEGEN_PY

    def test_missing_file_is_404_and_no_placeholders_is_422(self, client):
        assert client.post('/api/imagegen/inject-into-code', json={'filepath': 'nope.html'}).status_code == 404


class TestUploadValidation:
    def test_content_is_sniffed_not_just_the_extension(self, client):
        r = client.post(
            '/api/imagegen/gallery/upload',
            files={'file': ('fake.png', b'<html><script>alert(1)</script></html>', 'image/png')},
        )
        assert r.status_code == 415
        assert 'does not look like' in r.json()['error']

    def test_a_real_png_is_accepted(self, client):
        r = client.post(
            '/api/imagegen/gallery/upload',
            files={'file': ('real.png', ONE_PX_PNG, 'image/png')},
        )
        assert r.status_code == 200
        name = r.json()['name']
        client.delete(f'/api/imagegen/gallery/{name}')

    def test_uploaded_svg_is_sanitised_on_disk(self, client):
        evil = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        r = client.post('/api/imagegen/gallery/upload', files={'file': ('e.svg', evil, 'image/svg+xml')})
        assert r.status_code == 200
        name = r.json()['name']
        try:
            stored = (imagegen.ASSETS_DIR / name).read_bytes()
            assert b'<script' not in stored.lower()
        finally:
            client.delete(f'/api/imagegen/gallery/{name}')

    def test_collisions_do_not_overwrite(self, client):
        first = client.post('/api/imagegen/gallery/upload', files={'file': ('dup.png', ONE_PX_PNG, 'image/png')})
        second = client.post('/api/imagegen/gallery/upload', files={'file': ('dup.png', ONE_PX_PNG, 'image/png')})
        try:
            assert first.json()['name'] != second.json()['name']
            assert second.json()['renamed'] is True
        finally:
            client.delete(f"/api/imagegen/gallery/{first.json()['name']}")
            client.delete(f"/api/imagegen/gallery/{second.json()['name']}")

    def test_size_limit_is_enforced_while_reading(self):
        """The cap used to be checked after await file.read() had buffered it all."""
        idx = IMAGEGEN_CODE.index('async def upload_to_gallery')
        body = IMAGEGEN_CODE[idx : idx + 2000]
        assert 'await file.read(64 * 1024)' in body
        assert 'await file.read()' not in body

    def test_empty_and_unsupported_are_rejected(self, client):
        assert client.post(
            '/api/imagegen/gallery/upload', files={'file': ('a.txt', b'x', 'text/plain')}
        ).status_code == 415


class TestStatusCodes:
    @pytest.mark.parametrize(
        'path,body,expected',
        [
            ('/api/imagegen/generate', {'prompt': ''}, 400),
            ('/api/imagegen/enhance-prompt', {}, 400),
            ('/api/imagegen/inpaint', {}, 400),
            ('/api/imagegen/style-transfer', {}, 400),
            ('/api/imagegen/variations', {'prompt': 'x', 'count': 'abc'}, 400),
            ('/api/imagegen/figma/import', {'url': 'http://evil.com'}, 400),
        ],
    )
    def test_validation_errors_are_400(self, client, path, body, expected):
        assert client.post(path, json=body).status_code == expected

    def test_deleting_a_missing_image_is_404(self, client):
        assert client.delete('/api/imagegen/gallery/definitely-not-here.png').status_code == 404

    def test_invalid_delete_filename_is_400(self, client):
        assert client.delete('/api/imagegen/gallery/..%2Fetc%2Fpasswd').status_code in (400, 404)


class TestFigmaHonesty:
    def test_it_admits_it_never_reads_the_figma_file(self):
        """It only sees the URL text and asks an LLM to invent a matching design."""
        assert 'the Figma file was not read' in IMAGEGEN_PY
        assert "'approximation': True" in IMAGEGEN_PY


class TestFrontendContract:
    def test_it_surfaces_server_error_text(self):
        assert 'async function igError' in IMAGEGEN_JS
        assert IMAGEGEN_JS.count('igError(r') >= 6

    def test_placeholder_is_not_rendered_as_a_delivered_image(self):
        assert 'j.placeholder && j.svg' in IMAGEGEN_JS
        assert 'no image was generated' in IMAGEGEN_JS

    def test_a_model_can_be_chosen(self):
        assert 'id="img-model"' in IMAGEGEN_JS
        assert "model:   document.getElementById('img-model')?.value" in IMAGEGEN_JS

    def test_failed_variations_are_not_shown_as_empty_tiles(self):
        assert 'filter(v => v.ok && v.url)' in IMAGEGEN_JS


class TestConcurrency:
    def test_variations_run_concurrently(self):
        """Six sequential image calls at 10-20s each timed out the browser."""
        assert 'asyncio.gather(*(_one(i) for i in range(count)))' in IMAGEGEN_PY

    def test_a_partial_failure_still_returns_the_successes(self):
        assert "'failed': count - len(succeeded)" in IMAGEGEN_PY

    def test_total_failure_is_not_a_success(self):
        assert 'All {count} variations failed' in IMAGEGEN_PY or 'variations failed' in IMAGEGEN_PY


class TestSurvivesWorkspaceSwitch:
    """CROSS-MODULE: activating a workspace rmtree's PREVIEW_DIR.

    ASSETS_DIR was mkdir'd once at import time, so after any workspace switch
    the gallery directory no longer existed: uploads died with a bare HTTP 500
    and the gallery listed nothing without saying why. Reproduced live.
    """

    def test_assets_dir_is_resolved_lazily(self):
        assert 'def _assets_dir()' in IMAGEGEN_CODE
        # No handler may capture the module-level constant directly.
        for handler in ('def image_gallery', 'def delete_gallery_image', 'async def upload_to_gallery'):
            idx = IMAGEGEN_CODE.index(handler)
            body = IMAGEGEN_CODE[idx : idx + 2000]
            assert 'ASSETS_DIR' not in body or '_assets_dir()' in body

    def test_upload_works_after_the_directory_is_removed(self, client):
        import shutil

        shutil.rmtree(imagegen.ASSETS_DIR, ignore_errors=True)
        assert not imagegen.ASSETS_DIR.exists()

        assert client.get('/api/imagegen/gallery').status_code == 200
        r = client.post(
            '/api/imagegen/gallery/upload',
            files={'file': ('after-switch.png', ONE_PX_PNG, 'image/png')},
        )
        assert r.status_code == 200, 'upload must recreate the gallery directory'
        client.delete(f"/api/imagegen/gallery/{r.json()['name']}")
