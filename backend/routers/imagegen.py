"""
Agentic OS — Image Generation + Figma Import Router

Generates images through OpenRouter's image-capable models and imports Figma
designs as code.

Image generation goes through POST /api/v1/chat/completions with
modalities=['image', 'text'] — OpenRouter's actual contract. The images come
back as base64 data URLs in `choices[0].message.images`.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import html
import json
import logging
import os
import re
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/imagegen', tags=['imagegen'])
log = logging.getLogger('agentic.imagegen')

from backend.config import get_data_dir

from ..services.request_body import as_text, json_body_or_error
from ..services.safe_paths import safe_path

ROOT = get_data_dir()
PREVIEW_DIR = ROOT / 'preview'
ASSETS_DIR = PREVIEW_DIR / 'assets' / 'images'
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def _assets_dir() -> Path:
    """The gallery directory, (re)created on demand.

    CROSS-MODULE BUG: this directory was created exactly once at import time.
    POST /api/workspaces/{id}/activate does `shutil.rmtree(PREVIEW_DIR)` to swap
    in another workspace's files, which deletes assets/images along with it.
    After any workspace switch, every upload failed with a bare HTTP 500
    (FileNotFoundError on the write) and the gallery silently listed nothing.
    Reproduced live: upload → activate → upload = 500. Because the path is
    stable, re-creating it lazily is enough; the gallery is workspace-agnostic
    by design, so it simply starts empty after a switch.
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    return ASSETS_DIR

OR_BASE = 'https://openrouter.ai/api/v1'

VALID_SIZES = {'256x256', '512x512', '1024x1024', '1024x1792', '1792x1024'}

# Aspect ratios OpenRouter accepts via image_config, mapped from our size strings.
_SIZE_TO_ASPECT = {
    '256x256': '1:1',
    '512x512': '1:1',
    '1024x1024': '1:1',
    '1024x1792': '9:16',
    '1792x1024': '16:9',
}

# Models that can actually output images on OpenRouter. Used when the live
# catalogue can't be fetched (no key / offline). Verified present in
# /api/v1/models with 'image' in architecture.output_modalities.
FALLBACK_IMAGE_MODELS = [
    {'id': 'google/gemini-2.5-flash-image', 'name': 'Gemini 2.5 Flash Image', 'provider': 'google'},
    {'id': 'google/gemini-3-pro-image', 'name': 'Gemini 3 Pro Image', 'provider': 'google'},
    {'id': 'openai/gpt-5-image-mini', 'name': 'GPT-5 Image Mini', 'provider': 'openai'},
    {'id': 'openai/gpt-5-image', 'name': 'GPT-5 Image', 'provider': 'openai'},
]
DEFAULT_IMAGE_MODEL = os.getenv('IMAGEGEN_MODEL', 'google/gemini-2.5-flash-image')

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg')
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Magic-byte signatures. An extension is a claim; these are evidence.
_MAGIC = {
    '.png': [b'\x89PNG\r\n\x1a\n'],
    '.jpg': [b'\xff\xd8\xff'],
    '.jpeg': [b'\xff\xd8\xff'],
    '.gif': [b'GIF87a', b'GIF89a'],
    '.webp': [b'RIFF'],  # plus 'WEBP' at offset 8, checked separately
}


def _or_headers() -> dict:
    return {
        'Authorization': f'Bearer {os.getenv("OPENROUTER_API_KEY", "")}',
        'HTTP-Referer': f'http://localhost:{os.getenv("AGENTIC_OS_PORT", "8787")}',
        'X-Title': 'Agentic OS',
        'Content-Type': 'application/json',
    }


def _safe_preview_path(relative: str) -> Path | None:
    """Resolve a path inside PREVIEW_DIR, blocking traversal.

    Delegates to services.safe_paths.safe_path — the containment rule lives in
    one place now. The bug this replaced (str.startswith on the resolved path,
    which accepted sibling directories like preview_ESCAPED) is documented
    there.
    """
    return safe_path(relative, base=PREVIEW_DIR)


def _sniff_image(content: bytes, ext: str) -> bool:
    """Verify the bytes actually look like the image type the extension claims."""
    if ext == '.svg':
        head = content[:1024].lstrip()
        return head.startswith(b'<?xml') or head.startswith(b'<svg') or b'<svg' in content[:2048].lower()
    sigs = _MAGIC.get(ext, [])
    if not sigs:
        return False
    if not any(content.startswith(sig) for sig in sigs):
        return False
    if ext == '.webp':
        return content[8:12] == b'WEBP'
    return True


# ── SVG sanitisation ───────────────────────────────────────────────────────────
# SVG is not an inert image format: it is XML that can carry <script>, event
# handlers and external references, and the preview server returns it as
# image/svg+xml from the app's own origin. Anything we write into the gallery
# has to be scrubbed first.
_SVG_DANGEROUS_TAGS = re.compile(
    rb'<\s*(script|foreignObject|iframe|embed|object|animate|set|handler)\b[^>]*>.*?<\s*/\s*\1\s*>',
    re.IGNORECASE | re.DOTALL,
)
_SVG_SELF_CLOSING = re.compile(
    rb'<\s*(script|foreignObject|iframe|embed|object|animate|set|handler)\b[^>]*/?>',
    re.IGNORECASE,
)
_SVG_EVENT_ATTR = re.compile(rb'\son\w+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', re.IGNORECASE)
# Match the whole attribute including its closing quote, otherwise stripping
# href="javascript:…" leaves a dangling quote and malformed XML.
_SVG_JS_URI = re.compile(
    rb'\s(?:href|xlink:href|src)\s*=\s*'
    rb'(?:"\s*(?:javascript|vbscript|data:text/html)[^"]*"'
    rb"|'\s*(?:javascript|vbscript|data:text/html)[^']*'"
    rb'|(?:javascript|vbscript|data:text/html)[^\s>]*)',
    re.IGNORECASE,
)


def sanitize_svg(svg: str | bytes) -> bytes:
    """Strip script tags, event handlers and javascript: URIs from an SVG.

    Defence in depth alongside the CSP and Content-Disposition headers: a
    sanitised file is safe even if it is later served or opened by something
    that doesn't apply those headers.
    """
    data = svg.encode('utf-8') if isinstance(svg, str) else svg
    for _ in range(3):  # re-run: removing a wrapper can expose a nested one
        before = data
        data = _SVG_DANGEROUS_TAGS.sub(b'', data)
        data = _SVG_SELF_CLOSING.sub(b'', data)
        data = _SVG_EVENT_ATTR.sub(b'', data)
        data = _SVG_JS_URI.sub(b'', data)
        if data == before:
            break
    return data


def _unique_path(directory: Path, name: str) -> Path:
    """Return a non-colliding path, appending -1, -2 … rather than overwriting."""
    dest = directory / name
    if not dest.exists():
        return dest
    stem, ext = Path(name).stem, Path(name).suffix
    for i in range(1, 1000):
        candidate = directory / f'{stem}-{i}{ext}'
        if not candidate.exists():
            return candidate
    return directory / f'{stem}-{int(time.time())}{ext}'


class ImageGenError(Exception):
    """Image generation failed for a reason the user needs to hear about."""

    def __init__(self, message: str, status: int = 502, hint: str = ''):
        super().__init__(message)
        self.message = message
        self.status = status
        self.hint = hint


def _placeholder_result(prompt: str, size: str, save_to: str, note: str) -> dict:
    """Build an explicitly-labelled placeholder response.

    `ok` is False and `placeholder` is True. This used to return ok=True, which
    made "no API key" and "here is your image" indistinguishable to every caller.
    """
    svg = _make_placeholder_svg(prompt, size)
    saved_path = ''
    if save_to:
        svg_name = save_to if save_to.endswith('.svg') else save_to.rsplit('.', 1)[0] + '.svg'
        sp = _safe_preview_path(svg_name)
        if sp:
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_bytes(sanitize_svg(svg))
            saved_path = svg_name
    return {
        'ok': False,
        'placeholder': True,
        'type': 'svg_placeholder',
        'url': None,
        'b64': None,
        'svg': svg,
        'prompt': prompt,
        'saved_to': saved_path,
        'note': note,
    }


def _extract_images(message: dict) -> list[str]:
    """Pull data URLs out of an OpenRouter assistant message.

    Images arrive as `message.images[].image_url.url` (base64 data URLs).
    """
    out = []
    for item in message.get('images') or []:
        if not isinstance(item, dict):
            continue
        url = (item.get('image_url') or {}).get('url') or item.get('url')
        if isinstance(url, str) and url:
            out.append(url)
    return out


def _decode_data_url(data_url: str) -> tuple[bytes, str]:
    """Split a data: URL into raw bytes and a file extension."""
    m = re.match(r'^data:image/([a-zA-Z0-9.+-]+);base64,(.+)$', data_url, re.DOTALL)
    if not m:
        raise ImageGenError('Model returned an image in an unrecognised format', status=502)
    subtype = m.group(1).lower()
    ext = {'jpeg': '.jpg', 'svg+xml': '.svg'}.get(subtype, f'.{subtype}')
    if ext not in IMAGE_EXTS:
        raise ImageGenError(f'Model returned an unsupported image type: {subtype}', status=502)
    try:
        return base64.b64decode(m.group(2), validate=True), ext
    except (binascii.Error, ValueError) as exc:
        raise ImageGenError('Model returned corrupt base64 image data', status=502) from exc


async def _do_generate(
    prompt: str,
    size: str = '1024x1024',
    style: str = '',
    save_to: str = '',
    model: str = '',
) -> dict:
    """Core image generation.

    Raises ImageGenError when generation genuinely fails. Returns a placeholder
    (ok=False, placeholder=True) only when there is no API key at all — that is a
    configuration state, not a failure, and the UI renders it as guidance.
    """
    if not prompt or not prompt.strip():
        raise ImageGenError('prompt required', status=400)

    size = size if size in VALID_SIZES else '1024x1024'
    full_prompt = f'{prompt}. {style}' if style else prompt
    key = os.getenv('OPENROUTER_API_KEY', '')

    if not key:
        return _placeholder_result(
            prompt,
            size,
            save_to,
            'No OPENROUTER_API_KEY set — showing a placeholder. Add a key in Settings → '
            'Connect AI to generate real images.',
        )

    model = (model or DEFAULT_IMAGE_MODEL).strip()

    # BUG FIX: this called POST /images/generations with
    # 'black-forest-labs/FLUX.1-schnell:free'. Neither exists on OpenRouter —
    # the model is absent from the catalogue entirely (verified against
    # /api/v1/models: 0 of 338 ids match flux/dall-e/sdxl), and image generation
    # goes through /chat/completions with modalities=['image','text'], returning
    # base64 data URLs in choices[0].message.images. Every call 404'd, and the
    # bare `except` below swallowed it and returned ok:true with a placeholder.
    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': full_prompt}],
        'modalities': ['image', 'text'],
    }
    aspect = _SIZE_TO_ASPECT.get(size)
    if aspect:
        payload['image_config'] = {'aspect_ratio': aspect}

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f'{OR_BASE}/chat/completions', headers=_or_headers(), json=payload
            )
    except httpx.TimeoutException as exc:
        raise ImageGenError(
            'Image generation timed out. Image models can be slow — try again, or pick a faster model.',
            status=504,
        ) from exc
    except httpx.HTTPError as exc:
        raise ImageGenError(f'Could not reach OpenRouter: {exc}', status=502) from exc

    if resp.status_code == 401:
        raise ImageGenError(
            'OpenRouter rejected the API key. Check OPENROUTER_API_KEY in Settings → Connect AI.',
            status=401,
        )
    if resp.status_code == 402:
        raise ImageGenError(
            f'Insufficient OpenRouter credit for {model}. Add credit or choose a free model.',
            status=402,
        )
    if resp.status_code == 429:
        raise ImageGenError('Rate limited by OpenRouter. Wait a moment and try again.', status=429)
    if resp.status_code != 200:
        detail = resp.text[:300]
        log.warning('Image gen failed %d: %s', resp.status_code, detail)
        raise ImageGenError(f'OpenRouter returned HTTP {resp.status_code}: {detail}', status=502)

    try:
        data = resp.json()
    except ValueError as exc:
        raise ImageGenError('OpenRouter returned a non-JSON response', status=502) from exc

    choices = data.get('choices') or []
    if not choices:
        raise ImageGenError('OpenRouter returned no choices', status=502)
    message = choices[0].get('message') or {}
    images = _extract_images(message)
    if not images:
        # The model answered in text instead of producing an image — usually a
        # refusal or a model that doesn't actually support image output.
        text = (as_text(message.get('content')) or '')
        raise ImageGenError(
            f'{model} did not return an image'
            + (f': {text[:200]}' if text else '. It may not support image output.'),
            status=502,
            hint='Check GET /api/imagegen/models for models that can output images.',
        )

    raw, ext = _decode_data_url(images[0])
    if ext == '.svg':
        raw = sanitize_svg(raw)

    saved_path = ''
    if save_to:
        fname = save_to if save_to.lower().endswith(IMAGE_EXTS) else save_to + ext
        # Keep the extension honest: the bytes decide, not the requested name.
        if not fname.lower().endswith(ext):
            fname = fname.rsplit('.', 1)[0] + ext
        sp = _safe_preview_path(fname)
        if sp is None:
            raise ImageGenError('save_to must stay inside the preview directory', status=403)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp = _unique_path(sp.parent, sp.name)
        sp.write_bytes(raw)
        saved_path = str(sp.relative_to(PREVIEW_DIR))

    from ..services.memory_db import audit_log

    audit_log('image_gen', prompt[:80])
    usage = data.get('usage') or {}
    return {
        'ok': True,
        'placeholder': False,
        'type': 'generated',
        'url': images[0],
        'b64': base64.b64encode(raw).decode('ascii'),
        'saved_to': saved_path,
        'prompt': prompt,
        'model': model,
        'size': size,
        'tokens': usage.get('total_tokens', 0),
        'cost': usage.get('cost', 0.0),
    }


# ── Image generation ──────────────────────────────────────────────────────────


def _err(exc: ImageGenError) -> JSONResponse:
    body = {'ok': False, 'error': exc.message}
    if exc.hint:
        body['hint'] = exc.hint
    return JSONResponse(body, status_code=exc.status)


@router.post('/generate')
async def generate_image(req: Request):
    """Generate an image from a text prompt."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    prompt = as_text(body.get('prompt'))
    size = body.get('size', '1024x1024')
    style = as_text(body.get('style'))
    save_to = as_text(body.get('save_to'))
    model = as_text(body.get('model'))

    if not prompt:
        return JSONResponse({'ok': False, 'error': 'prompt required'}, status_code=400)

    try:
        return await _do_generate(prompt, size, style, save_to, model)
    except ImageGenError as exc:
        return _err(exc)


# ── Gallery ────────────────────────────────────────────────────────────────────


@router.get('/gallery')
def image_gallery():
    """List all generated images in preview/assets/images."""
    images = []
    assets = _assets_dir()
    if assets.exists():
        for f in sorted(assets.iterdir(), key=lambda x: -x.stat().st_mtime):
            if f.is_file() and f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'):
                images.append(
                    {
                        'name': f.name,
                        'path': f'assets/images/{f.name}',
                        'size': f.stat().st_size,
                        'url': f'/preview/assets/images/{f.name}',
                        'modified': f.stat().st_mtime,
                    }
                )
    return {'images': images, 'count': len(images)}


@router.delete('/gallery/{filename}')
def delete_gallery_image(filename: str):
    """Delete an image from the gallery."""
    # Safety: only allow simple filenames with valid image extensions
    if '/' in filename or '\\' in filename or '..' in filename:
        return JSONResponse({'ok': False, 'error': 'Invalid filename'}, status_code=400)
    target = _assets_dir() / filename
    if not target.exists() or not target.is_file():
        return JSONResponse({'ok': False, 'error': 'Image not found'}, status_code=404)
    if target.suffix.lower() not in IMAGE_EXTS:
        return JSONResponse({'ok': False, 'error': 'Not an image file'}, status_code=400)
    target.unlink()
    return {'ok': True, 'deleted': filename}


@router.post('/gallery/upload')
async def upload_to_gallery(file: UploadFile = File(...)):
    """Upload an image to the gallery."""
    if not file.filename:
        return JSONResponse({'ok': False, 'error': 'No file provided'}, status_code=400)
    ext = Path(file.filename).suffix.lower()
    if ext not in IMAGE_EXTS:
        return JSONResponse({'ok': False, 'error': f'Unsupported file type: {ext}'}, status_code=415)

    # BUG FIX: the size limit was enforced *after* await file.read(), so a
    # multi-gigabyte upload was fully buffered into memory before being
    # rejected. Read in bounded chunks and stop as soon as the cap is passed.
    chunks, total = [], 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            return JSONResponse(
                {'ok': False, 'error': 'File too large (max 10 MB)'}, status_code=413
            )
        chunks.append(chunk)
    content = b''.join(chunks)
    if not content:
        return JSONResponse({'ok': False, 'error': 'File is empty'}, status_code=400)

    # BUG FIX: the extension was the only check, so any bytes could be stored
    # under an image name — verified live by uploading an HTML/script payload as
    # fake.png, which the preview server then served as image/png.
    if not _sniff_image(content, ext):
        return JSONResponse(
            {'ok': False, 'error': f'File content does not look like a valid {ext} image'},
            status_code=415,
        )

    # SVG is executable XML; scrub it before it can be served same-origin.
    if ext == '.svg':
        content = sanitize_svg(content)

    safe_name = re.sub(r'[^\w\-.]', '_', Path(file.filename).stem)[:60] + ext
    # BUG FIX: identical names silently overwrote existing gallery images.
    dest = _unique_path(_assets_dir(), safe_name)
    dest.write_bytes(content)
    from ..services.memory_db import audit_log

    audit_log('image_upload', dest.name)
    return {
        'ok': True,
        'name': dest.name,
        'url': f'/preview/assets/images/{dest.name}',
        'size': len(content),
        'renamed': dest.name != safe_name,
    }


# ── Models ─────────────────────────────────────────────────────────────────────


@router.get('/models')
async def list_models():
    """List image-capable models, live from OpenRouter where possible.

    BUG FIX: this returned a hardcoded list of four models — FLUX.1-schnell:free,
    FLUX.1-pro, dall-e-3 and sdxl — none of which exist on OpenRouter. Verified
    against /api/v1/models: zero of 338 catalogue ids match flux, dall-e or sdxl.
    Every one of them was unusable, and the first was the router's default.
    """
    fallback = [dict(m) for m in FALLBACK_IMAGE_MODELS]
    key = os.getenv('OPENROUTER_API_KEY', '')
    models = fallback
    source = 'builtin'

    if key:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f'{OR_BASE}/models', headers=_or_headers())
            if resp.status_code == 200:
                live = []
                for m in resp.json().get('data', []):
                    arch = m.get('architecture') or {}
                    if 'image' not in (arch.get('output_modalities') or []):
                        continue
                    mid = m.get('id', '')
                    if mid.startswith('openrouter/auto'):
                        continue  # a router, not a concrete image model
                    pricing = m.get('pricing') or {}
                    try:
                        img_price = float(pricing.get('image', 0) or 0)
                    except (TypeError, ValueError):
                        img_price = 0.0
                    live.append(
                        {
                            'id': mid,
                            'name': m.get('name', mid),
                            'provider': mid.split('/')[0] if '/' in mid else 'OpenRouter',
                            'free': img_price == 0.0,
                            'price_per_image': img_price,
                        }
                    )
                if live:
                    models, source = live, 'openrouter'
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            log.warning('Could not fetch live image models: %s', exc)

    available = {m['id'] for m in models}
    default = DEFAULT_IMAGE_MODEL if DEFAULT_IMAGE_MODEL in available else (models[0]['id'] if models else '')
    return {
        'models': models,
        'default': default,
        'source': source,
        'api_key_set': bool(key),
    }


# ── Inject into code ───────────────────────────────────────────────────────────


@router.post('/inject-into-code')
async def inject_image_into_code(req: Request):
    """Generate images and insert them into a file at placeholder locations."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    filepath = (as_text(body.get('filepath')) or 'index.html').lstrip('/')

    target = _safe_preview_path(filepath)
    if target is None:
        return JSONResponse(
            {'ok': False, 'error': 'filepath must stay inside the preview directory'},
            status_code=403,
        )
    if not target.exists() or not target.is_file():
        return JSONResponse({'ok': False, 'error': 'File not found'}, status_code=404)

    content = target.read_text(encoding='utf-8', errors='ignore')
    placeholders = re.findall(r'<!--\s*IMAGE:\s*([^>]+?)\s*-->', content)

    if not placeholders:
        return JSONResponse(
            {
                'ok': False,
                'error': 'No IMAGE: placeholders found. Add <!-- IMAGE: description --> to your HTML',
            },
            status_code=422,
        )

    injected, failures = 0, []
    for desc in placeholders:
        desc = desc.strip()
        safe_name = re.sub(r'[^a-z0-9]', '_', desc.lower())[:30] or 'image'
        try:
            result = await _do_generate(prompt=desc, save_to=f'assets/images/{safe_name}')
        except ImageGenError as exc:
            failures.append({'placeholder': desc, 'error': exc.message})
            continue
        if not result.get('saved_to'):
            failures.append({'placeholder': desc, 'error': result.get('note') or 'no image produced'})
            continue

        img_src = '/preview/' + result['saved_to'].replace('\\', '/')
        # BUG FIX: `desc` came straight from the file and was interpolated into
        # an alt="" attribute unescaped, so a placeholder like
        # <!-- IMAGE: cat" onerror="alert(1) --> wrote a live event handler into
        # the user's own HTML. Reproduced live. Both attributes are escaped now.
        tag = (
            f'<img src="{html.escape(img_src, quote=True)}" '
            f'alt="{html.escape(desc, quote=True)}" '
            f'style="max-width:100%;border-radius:8px">'
        )
        content = content.replace(f'<!-- IMAGE: {desc} -->', tag, 1)
        injected += 1

    if injected:
        target.write_text(content, encoding='utf-8')

    # Partial success is still partial: report what didn't work.
    return JSONResponse(
        {
            'ok': injected > 0,
            'injected': injected,
            'placeholders_found': len(placeholders),
            'failures': failures,
        },
        status_code=200 if injected else 502,
    )


# ── Figma Import ───────────────────────────────────────────────────────────────


@router.post('/figma/import')
async def figma_import(req: Request):
    """Import a Figma design by URL and reconstruct it as HTML/CSS code."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    figma_url = as_text(body.get('url'))
    framework = (as_text(body.get('framework')) or 'html')

    if not figma_url or not re.search(r'(?:^|[./])figma\.com(?:/|$)', figma_url):
        return JSONResponse(
            {'ok': False, 'error': 'Valid Figma URL required (e.g. https://www.figma.com/design/...)'},
            status_code=400,
        )

    if framework not in ('html', 'react', 'vue'):
        framework = 'html'

    from ..services import llm

    messages = [
        {
            'role': 'system',
            'content': f'You are a UI developer converting a Figma design to {framework} code. '
            f'The user has a Figma design URL. Analyze what this likely looks like based on the URL path/name, '
            f'and generate a beautiful, complete {framework} implementation. '
            f'Use Tailwind CSS via CDN. Make it dark theme, professional, responsive. '
            f'Return ONLY the complete code file, no explanation.',
        },
        {
            'role': 'user',
            'content': f'Convert this Figma design to {framework}:\n{figma_url}\n\n'
            f'Generate a complete, pixel-perfect reconstruction based on the design name/context.',
        },
    ]
    result = await llm.complete(messages, agent_id='builder', max_tokens=4096, temperature=0.3, inject_steering=False)
    code = (as_text(result.get('text')) or '')
    if code.startswith('```'):
        code = '\n'.join(code.split('\n')[1:]).rstrip('`').strip()

    ext = 'html' if framework == 'html' else 'jsx' if framework == 'react' else 'vue'
    saved_file = None
    if code:
        outfile = PREVIEW_DIR / f'figma_import.{ext}'
        outfile.write_text(code, encoding='utf-8')
        saved_file = f'figma_import.{ext}'
        from ..services.memory_db import audit_log

        audit_log('figma_import', figma_url[:80])

    if not code:
        return JSONResponse(
            {'ok': False, 'error': 'The model returned no code for this Figma URL.'},
            status_code=502,
        )
    return {
        'ok': True,
        'code': code,
        'file': saved_file,
        'framework': framework,
        # Be honest about what this actually does: it reads the URL slug and asks
        # an LLM to invent a matching design. It never contacts Figma.
        'note': (
            'Reconstructed from the URL text only — the Figma file was not read. '
            'This is an AI approximation, not an import. A Figma API token would be '
            'required for a real import.'
        ),
        'approximation': True,
    }


# ── Styles ─────────────────────────────────────────────────────────────────────


@router.get('/styles')
def image_styles():
    """Available image generation styles."""
    return [
        {
            'id': 'photorealistic',
            'label': '📸 Photorealistic',
            'prompt': 'photorealistic, 8k, detailed, natural lighting',
        },
        {'id': 'illustration', 'label': '🎨 Illustration', 'prompt': 'digital illustration, flat design, vector art'},
        {'id': 'ui_mockup', 'label': '🖥️ UI Mockup', 'prompt': 'clean UI mockup, modern app design, dark theme'},
        {'id': 'logo', 'label': '✨ Logo', 'prompt': 'professional logo, minimal, vector, transparent background'},
        {'id': 'icon', 'label': '🔷 Icon', 'prompt': 'app icon, flat design, clean, simple'},
        {'id': 'hero_image', 'label': '🦸 Hero Image', 'prompt': 'website hero image, professional, high impact'},
        {'id': 'background', 'label': '🌌 Background', 'prompt': 'abstract background, gradient, modern, dark'},
        {'id': 'avatar', 'label': '👤 Avatar', 'prompt': 'professional avatar, cartoon style, friendly'},
        {
            'id': 'cinematic',
            'label': '🎬 Cinematic',
            'prompt': 'cinematic lighting, film grain, dramatic shadows, movie still',
        },
        {
            'id': 'watercolor',
            'label': '🎨 Watercolor',
            'prompt': 'watercolor painting, soft edges, paper texture, translucent washes',
        },
        {'id': 'pixel_art', 'label': '👾 Pixel Art', 'prompt': 'pixel art, 16-bit, retro game style, chunky pixels'},
        {
            'id': 'sketch',
            'label': '✏️ Sketch',
            'prompt': 'pencil sketch, hand-drawn, graphite, cross-hatching, monochrome',
        },
    ]


# ── Style transfer ─────────────────────────────────────────────────────────────


@router.post('/style-transfer')
async def style_transfer(req: Request):
    """Apply a visual style to a prompt using AI-enhanced prompt engineering."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    source_prompt = (body.get('source_prompt') or body.get('prompt') or '').strip()
    style_id = (as_text(body.get('style')) or 'cinematic')
    custom_style = as_text(body.get('custom_style'))
    size = body.get('size', '1024x1024')

    if not source_prompt:
        return JSONResponse(
            {'ok': False, 'error': 'source_prompt (or prompt) required'}, status_code=400
        )

    STYLE_ENHANCERS = {
        'cinematic': 'cinematic lighting, film grain, anamorphic lens, dramatic shadows, movie still',
        'anime': 'anime style, Studio Ghibli inspired, cel shading, vibrant colors, clean linework',
        'oil_painting': 'oil painting, impressionist, textured brushstrokes, classical art style',
        'watercolor': 'watercolor painting, soft edges, paper texture, translucent washes, delicate',
        'neon_noir': 'neon noir, cyberpunk, glowing neons, rain-soaked streets, dramatic contrast',
        'minimal': 'minimalist, flat design, clean lines, limited palette, elegant whitespace',
        'fantasy': 'fantasy art, epic, magical, intricate details, volumetric light, concept art',
        'retro': 'retro 80s style, synthwave, VHS aesthetic, neon grids, warm glows',
        'photorealistic': 'photorealistic, 8k, ultra-detailed, DSLR photo, sharp focus, natural lighting',
        'sketch': 'pencil sketch, hand-drawn, graphite, cross-hatching, monochrome',
        'pixel_art': 'pixel art, 16-bit, retro game style, chunky pixels',
        'studio_photo': 'professional studio photography, clean background, soft box lighting, product shot',
    }

    style_prompt = custom_style or STYLE_ENHANCERS.get(style_id, 'artistic style')
    enhanced_prompt = f'{source_prompt}, {style_prompt}'

    key = os.getenv('OPENROUTER_API_KEY', '')
    if key and source_prompt:
        try:
            from ..services import llm as llm_svc

            msgs = [
                {
                    'role': 'system',
                    'content': 'You are an expert image generation prompt engineer. Enhance prompts for maximum visual quality. Return ONLY the enhanced prompt, no explanation.',
                },
                {
                    'role': 'user',
                    'content': f'Enhance this image prompt with {style_id} style:\n{enhanced_prompt}\n\nReturn an optimized prompt for Flux image generation, max 200 words.',
                },
            ]
            result = await llm_svc.complete(
                msgs, agent_id='imagegen', max_tokens=256, temperature=0.7, inject_steering=False
            )
            enhanced_prompt = (as_text(result.get('text')) or enhanced_prompt)[:500]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass

    try:
        result = await _do_generate(enhanced_prompt, size)
    except ImageGenError as exc:
        return _err(exc)
    result['original_prompt'] = source_prompt
    result['enhanced_prompt'] = enhanced_prompt
    result['style'] = style_id
    result['style_descriptor'] = style_prompt
    return result


# ── Inpainting ─────────────────────────────────────────────────────────────────


@router.post('/inpaint')
async def inpaint_image(req: Request):
    """Inpainting — fill or replace part of an image described by a mask description."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    prompt = as_text(body.get('prompt'))
    mask_desc = (as_text(body.get('mask_description')) or 'the selected area')
    fill_with = as_text(body.get('fill_with'))
    size = body.get('size', '1024x1024')

    if not prompt:
        return JSONResponse({'ok': False, 'error': 'prompt required'}, status_code=400)

    inpaint_prompt = f'{prompt}. In {mask_desc}, replace with: {fill_with}. Seamless, realistic, coherent.'

    try:
        result = await _do_generate(inpaint_prompt, size)
    except ImageGenError as exc:
        return _err(exc)
    result['inpaint_prompt'] = inpaint_prompt
    result['mask_description'] = mask_desc
    result['fill_with'] = fill_with
    return result


# ── Prompt enhancement ─────────────────────────────────────────────────────────


@router.post('/enhance-prompt')
async def enhance_prompt(req: Request):
    """AI-powered prompt enhancement without generating an image."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    prompt = as_text(body.get('prompt'))
    style = as_text(body.get('style'))
    goal = (as_text(body.get('goal')) or 'general')

    if not prompt:
        return JSONResponse({'ok': False, 'error': 'prompt required'}, status_code=400)

    GOAL_CONTEXT = {
        'portrait': "Focus on subject's face, expression, lighting, background blur (bokeh), professional photography",
        'landscape': 'Wide angle, epic scenery, dramatic sky, golden hour light, ultra-wide composition',
        'product': 'Clean white/grey background, studio lighting, sharp focus, commercial photography',
        'ui': 'Clean UI mockup, modern app interface, dark/light theme, typography, spacing',
        'logo': 'Vector logo, minimal, scalable, single color variant, transparent background, brand identity',
        'abstract': 'Abstract art, geometric shapes, flowing lines, color theory, textural depth',
        'character': 'Character design, full body, front view, detailed costume, expressive pose',
        'icon': 'App icon, 1024x1024, rounded corners, flat design, single concept, recognizable',
        'general': 'high quality, detailed, professional',
    }

    goal_ctx = GOAL_CONTEXT.get(goal, GOAL_CONTEXT['general'])
    base_enhanced = f'{prompt}. {goal_ctx}'
    if style:
        base_enhanced += f'. Style: {style}'

    key = os.getenv('OPENROUTER_API_KEY', '')
    if key:
        try:
            from ..services import llm as llm_svc

            msgs = [
                {
                    'role': 'system',
                    'content': 'You are an expert at writing image generation prompts for Flux/DALL-E/Midjourney. Make prompts vivid, specific, and technically optimized. Return ONLY the enhanced prompt.',
                },
                {
                    'role': 'user',
                    'content': f'Goal: {goal}\nOriginal: {prompt}\n\nEnhance this prompt for maximum image quality. Include technical photography/art terms, lighting, composition, mood. Max 150 words.',
                },
            ]
            r = await llm_svc.complete(
                msgs, agent_id='imagegen', max_tokens=200, temperature=0.8, inject_steering=False
            )
            enhanced = (as_text(r.get('text')) or base_enhanced)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            enhanced = base_enhanced
    else:
        enhanced = base_enhanced

    return {
        'ok': True,
        'original': prompt,
        'enhanced': enhanced,
        'goal': goal,
        'style': style,
    }


# ── Variations ─────────────────────────────────────────────────────────────────


@router.post('/variations')
async def generate_variations(req: Request):
    """Generate N variations of a prompt with slight modifications."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    prompt = as_text(body.get('prompt'))
    # BUG FIX: int(body.get('count')) raised ValueError on any non-numeric
    # input, surfacing as a bare HTTP 500. Verified live with count="abc".
    try:
        count = min(max(1, int(body.get('count', 4))), 6)
    except (TypeError, ValueError):
        return JSONResponse(
            {'ok': False, 'error': 'count must be an integer between 1 and 6'}, status_code=400
        )
    size = body.get('size', '512x512')

    if not prompt:
        return JSONResponse({'ok': False, 'error': 'prompt required'}, status_code=400)

    MODIFIERS = [
        'dramatic lighting',
        'soft pastel tones',
        'high contrast black and white',
        'golden hour warm tones',
        'cool blue tones, moody',
        'vibrant saturated colors',
    ]

    # Variations are independent; run them concurrently rather than serially.
    # Six sequential image calls at ~10-20s each timed out the browser.
    async def _one(i: int) -> dict:
        mod = MODIFIERS[i % len(MODIFIERS)]
        try:
            r = await _do_generate(f'{prompt}, {mod}', size)
        except ImageGenError as exc:
            return {'ok': False, 'error': exc.message, 'modifier': mod, 'variation_index': i}
        return {**r, 'modifier': mod, 'variation_index': i}

    results = await asyncio.gather(*(_one(i) for i in range(count)))
    succeeded = [r for r in results if r.get('ok')]

    # One failure shouldn't discard the others, but "all failed" isn't a success.
    if not succeeded:
        first_error = next((r.get('error') for r in results if r.get('error')), 'generation failed')
        return JSONResponse(
            {'ok': False, 'error': f'All {count} variations failed: {first_error}',
             'variations': list(results), 'count': 0},
            status_code=502,
        )

    return {
        'ok': True,
        'variations': list(results),
        'count': len(succeeded),
        'requested': count,
        'failed': count - len(succeeded),
    }


# ── Helpers ─────────────────────────────────────────────────────────────────────


def _make_placeholder_svg(prompt: str, size: str = '1024x1024') -> str:
    # BUG FIX: `prompt` was interpolated into the SVG body unescaped, so
    # a prompt of `</text><script>alert(1)</script><text>` produced an SVG
    # carrying a live script tag. With save_to it was written into the gallery
    # and served from the app's own origin as image/svg+xml — stored XSS.
    # Reproduced live, then re-verified fixed. Escape the text, and clamp the
    # dimensions so they can't be injected either.
    if size not in VALID_SIZES:
        size = '1024x1024'
    w, h = size.split('x')
    words = ' '.join(prompt.split()[:8]) + ('…' if len(prompt.split()) > 8 else '')
    words = html.escape(words, quote=True)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#0d1117;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#1a1f35;stop-opacity:1"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#g)"/>
  <rect x="2" y="2" width="{int(w) - 4}" height="{int(h) - 4}" rx="12" fill="none" stroke="#252d4a" stroke-width="1" stroke-dasharray="8,4"/>
  <text x="50%" y="42%" text-anchor="middle" fill="#3d4868" font-family="Inter,sans-serif" font-size="42">🖼️</text>
  <text x="50%" y="54%" text-anchor="middle" fill="#7a8aaa" font-family="Inter,sans-serif" font-size="13">AI Image</text>
  <text x="50%" y="62%" text-anchor="middle" fill="#3d4868" font-family="Inter,sans-serif" font-size="11">{words}</text>
  <text x="50%" y="76%" text-anchor="middle" fill="#252d4a" font-family="Inter,sans-serif" font-size="10">Set OPENROUTER_API_KEY to generate</text>
</svg>'''
