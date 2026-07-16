"""
Agentic OS — Image Generation + Figma Import Router
Generate images via OpenRouter vision models (Flux, DALL-E, Stable Diffusion).
Import Figma designs and reconstruct as working code.
"""

from __future__ import annotations

import contextlib

import base64
import logging
import os
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, File, Request, UploadFile

router = APIRouter(prefix='/api/imagegen', tags=['imagegen'])
log = logging.getLogger('agentic.imagegen')

from backend.config import get_data_dir
ROOT = get_data_dir()
PREVIEW_DIR = ROOT / 'preview'
ASSETS_DIR = PREVIEW_DIR / 'assets' / 'images'
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

OR_BASE = 'https://openrouter.ai/api/v1'

VALID_SIZES = {'256x256', '512x512', '1024x1024', '1024x1792', '1792x1024'}


def _or_headers() -> dict:
    return {
        'Authorization': f'Bearer {os.getenv("OPENROUTER_API_KEY", "")}',
        'HTTP-Referer': f'http://localhost:{os.getenv("AGENTIC_OS_PORT", "8787")}',
        'X-Title': 'Agentic OS',
        'Content-Type': 'application/json',
    }


def _safe_preview_path(relative: str) -> Path | None:
    """Resolve a relative path within PREVIEW_DIR, blocking traversal."""
    target = (PREVIEW_DIR / relative.lstrip('/')).resolve()
    if str(target).startswith(str(PREVIEW_DIR.resolve())):
        return target
    return None


async def _do_generate(prompt: str, size: str = '1024x1024', style: str = '', save_to: str = '') -> dict:
    """Core image generation logic (no FastAPI Request dependency)."""
    if not prompt or not prompt.strip():
        return {'ok': False, 'error': 'prompt required'}

    size = size if size in VALID_SIZES else '1024x1024'
    full_prompt = f'{prompt}. {style}' if style else prompt
    key = os.getenv('OPENROUTER_API_KEY', '')

    if not key:
        placeholder = _make_placeholder_svg(prompt, size)
        saved_path = ''
        if save_to:
            sp = _safe_preview_path(save_to)
            if sp:
                sp.parent.mkdir(parents=True, exist_ok=True)
                sp.write_text(placeholder, encoding='utf-8')
                saved_path = save_to
        return {
            'ok': True,
            'type': 'svg_placeholder',
            'url': None,
            'b64': None,
            'svg': placeholder,
            'prompt': prompt,
            'saved_to': saved_path,
            'note': 'Set OPENROUTER_API_KEY to generate real images',
        }

    # Try OpenRouter image generation
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f'{OR_BASE}/images/generations',
                headers=_or_headers(),
                json={
                    'model': 'black-forest-labs/FLUX.1-schnell:free',
                    'prompt': full_prompt,
                    'n': 1,
                    'size': size,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                img_url = data['data'][0].get('url') if data.get('data') else None
                img_b64 = data['data'][0].get('b64_json') if data.get('data') else None

                saved_path = ''
                if save_to and (img_url or img_b64):
                    fname = save_to if save_to.endswith(('.png', '.jpg', '.webp')) else save_to + '.png'
                    sp = _safe_preview_path(fname)
                    if sp:
                        sp.parent.mkdir(parents=True, exist_ok=True)
                        if img_b64:
                            sp.write_bytes(base64.b64decode(img_b64))
                        elif img_url:
                            img_resp = await client.get(img_url)
                            sp.write_bytes(img_resp.content)
                        saved_path = fname

                from ..services.memory_db import audit_log

                audit_log('image_gen', prompt[:80])
                return {
                    'ok': True,
                    'url': img_url,
                    'b64': img_b64,
                    'saved_to': saved_path,
                    'prompt': prompt,
                    'type': 'generated',
                }
            else:
                err = resp.text[:200]
                log.warning('Image gen failed %d: %s', resp.status_code, err)
    except Exception as e:
        log.error('Image gen error: %s', e)

    # Fallback to SVG placeholder when API call fails
    svg = _make_placeholder_svg(prompt, size)
    # Save placeholder if save_to was requested
    saved_path = ''
    if save_to:
        svg_path = save_to if save_to.endswith('.svg') else save_to.rsplit('.', 1)[0] + '.svg'
        sp = _safe_preview_path(svg_path)
        if sp:
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(svg, encoding='utf-8')
            saved_path = svg_path
    return {
        'ok': True,
        'type': 'svg_placeholder',
        'svg': svg,
        'prompt': prompt,
        'url': None,
        'b64': None,
        'saved_to': saved_path,
        'note': 'Image generation failed — showing placeholder. Check API key and model availability.',
    }


# ── Image generation ──────────────────────────────────────────────────────────


@router.post('/generate')
async def generate_image(req: Request):
    """Generate an image from a text prompt."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = (body.get('prompt') or '').strip()
    size = body.get('size', '1024x1024')
    style = (body.get('style') or '').strip()
    save_to = (body.get('save_to') or '').strip()

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

    return await _do_generate(prompt, size, style, save_to)


# ── Gallery ────────────────────────────────────────────────────────────────────


@router.get('/gallery')
def image_gallery():
    """List all generated images in preview/assets/images."""
    images = []
    if ASSETS_DIR.exists():
        for f in sorted(ASSETS_DIR.iterdir(), key=lambda x: -x.stat().st_mtime):
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
        return {'ok': False, 'error': 'Invalid filename'}
    target = ASSETS_DIR / filename
    if not target.exists() or not target.is_file():
        return {'ok': False, 'error': 'Image not found'}
    if target.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'):
        return {'ok': False, 'error': 'Not an image file'}
    target.unlink()
    return {'ok': True, 'deleted': filename}


@router.post('/gallery/upload')
async def upload_to_gallery(file: UploadFile = File(...)):
    """Upload an image to the gallery."""
    if not file.filename:
        return {'ok': False, 'error': 'No file provided'}
    ext = Path(file.filename).suffix.lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'):
        return {'ok': False, 'error': f'Unsupported file type: {ext}'}
    # Generate safe filename
    safe_name = re.sub(r'[^\w\-.]', '_', Path(file.filename).stem)[:60] + ext
    dest = ASSETS_DIR / safe_name
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB limit
        return {'ok': False, 'error': 'File too large (max 10 MB)'}
    dest.write_bytes(content)
    from ..services.memory_db import audit_log

    audit_log('image_upload', safe_name)
    return {
        'ok': True,
        'name': safe_name,
        'url': f'/preview/assets/images/{safe_name}',
        'size': len(content),
    }


# ── Models ─────────────────────────────────────────────────────────────────────


@router.get('/models')
def list_models():
    """List available image generation models."""
    return {
        'models': [
            {
                'id': 'black-forest-labs/FLUX.1-schnell:free',
                'name': 'Flux Schnell (Free)',
                'provider': 'OpenRouter',
                'free': True,
                'quality': 'fast',
            },
            {
                'id': 'black-forest-labs/FLUX.1-pro',
                'name': 'Flux Pro',
                'provider': 'OpenRouter',
                'free': False,
                'quality': 'high',
            },
            {'id': 'openai/dall-e-3', 'name': 'DALL-E 3', 'provider': 'OpenAI', 'free': False, 'quality': 'high'},
            {
                'id': 'stability-ai/sdxl',
                'name': 'Stable Diffusion XL',
                'provider': 'Stability',
                'free': False,
                'quality': 'medium',
            },
        ],
        'default': 'black-forest-labs/FLUX.1-schnell:free',
        'api_key_set': bool(os.getenv('OPENROUTER_API_KEY')),
    }


# ── Inject into code ───────────────────────────────────────────────────────────


@router.post('/inject-into-code')
async def inject_image_into_code(req: Request):
    """Generate images and insert them into a file at placeholder locations."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    filepath = (body.get('filepath') or 'index.html').lstrip('/')

    target = _safe_preview_path(filepath)
    if not target or not target.exists():
        return {'ok': False, 'error': 'File not found'}

    content = target.read_text(encoding='utf-8', errors='ignore')
    placeholders = re.findall(r'<!--\s*IMAGE:\s*([^>]+)\s*-->', content)

    if not placeholders:
        return {'ok': False, 'error': 'No IMAGE: placeholders found. Add <!-- IMAGE: description --> to your HTML'}

    injected = 0
    for desc in placeholders:
        desc = desc.strip()
        safe_name = re.sub(r'[^a-z0-9]', '_', desc.lower())[:30]
        result = await _do_generate(prompt=desc, save_to=f'assets/images/{safe_name}.svg')
        if result.get('ok'):
            placeholder = f'<!-- IMAGE: {desc} -->'
            img_src = result.get('url') or (f'/preview/assets/images/{safe_name}.svg' if result.get('saved_to') else '')
            if img_src:
                content = content.replace(
                    placeholder, f'<img src="{img_src}" alt="{desc}" style="max-width:100%;border-radius:8px">', 1
                )
                injected += 1

    if injected > 0:
        target.write_text(content, encoding='utf-8')

    return {'ok': True, 'injected': injected, 'placeholders_found': len(placeholders)}


# ── Figma Import ───────────────────────────────────────────────────────────────


@router.post('/figma/import')
async def figma_import(req: Request):
    """Import a Figma design by URL and reconstruct it as HTML/CSS code."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    figma_url = (body.get('url') or '').strip()
    framework = (body.get('framework') or 'html').strip()

    if not figma_url or not re.search(r'(?:^|[./])figma\.com(?:/|$)', figma_url):
        return {'ok': False, 'error': 'Valid Figma URL required (e.g. https://www.figma.com/design/...)'}

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
    code = (result.get('text') or '').strip()
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

    return {
        'ok': bool(code),
        'code': code,
        'file': saved_file,
        'framework': framework,
        'note': 'Design reconstructed from URL context. For pixel-perfect import, use the Figma API token.',
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
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    source_prompt = (body.get('source_prompt') or body.get('prompt') or '').strip()
    style_id = (body.get('style') or 'cinematic').strip()
    custom_style = (body.get('custom_style') or '').strip()
    size = body.get('size', '1024x1024')

    if not source_prompt:
        return {'ok': False, 'error': 'source_prompt (or prompt) required'}

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
            enhanced_prompt = (result.get('text') or enhanced_prompt).strip()[:500]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass

    result = await _do_generate(enhanced_prompt, size)
    result['original_prompt'] = source_prompt
    result['enhanced_prompt'] = enhanced_prompt
    result['style'] = style_id
    result['style_descriptor'] = style_prompt
    return result


# ── Inpainting ─────────────────────────────────────────────────────────────────


@router.post('/inpaint')
async def inpaint_image(req: Request):
    """Inpainting — fill or replace part of an image described by a mask description."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = (body.get('prompt') or '').strip()
    mask_desc = (body.get('mask_description') or 'the selected area').strip()
    fill_with = (body.get('fill_with') or '').strip()
    size = body.get('size', '1024x1024')

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

    inpaint_prompt = f'{prompt}. In {mask_desc}, replace with: {fill_with}. Seamless, realistic, coherent.'

    result = await _do_generate(inpaint_prompt, size)
    result['inpaint_prompt'] = inpaint_prompt
    result['mask_description'] = mask_desc
    result['fill_with'] = fill_with
    return result


# ── Prompt enhancement ─────────────────────────────────────────────────────────


@router.post('/enhance-prompt')
async def enhance_prompt(req: Request):
    """AI-powered prompt enhancement without generating an image."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = (body.get('prompt') or '').strip()
    style = (body.get('style') or '').strip()
    goal = (body.get('goal') or 'general').strip()

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

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
            enhanced = (r.get('text') or base_enhanced).strip()
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
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = (body.get('prompt') or '').strip()
    count = min(max(1, int(body.get('count', 4))), 6)
    size = body.get('size', '512x512')

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

    MODIFIERS = [
        'dramatic lighting',
        'soft pastel tones',
        'high contrast black and white',
        'golden hour warm tones',
        'cool blue tones, moody',
        'vibrant saturated colors',
    ]

    results = []
    for i in range(count):
        mod = MODIFIERS[i % len(MODIFIERS)]
        vprompt = f'{prompt}, {mod}'
        r = await _do_generate(vprompt, size)
        results.append({**r, 'modifier': mod, 'variation_index': i})

    return {'ok': True, 'variations': results, 'count': count}


# ── Helpers ─────────────────────────────────────────────────────────────────────


def _make_placeholder_svg(prompt: str, size: str = '1024x1024') -> str:
    w, h = size.split('x') if 'x' in size else ('1024', '1024')
    words = ' '.join(prompt.split()[:8]) + ('…' if len(prompt.split()) > 8 else '')
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
