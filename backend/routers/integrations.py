"""
Agentic OS — Integrations Router
Stripe payment scaffolding, Auth.js/Clerk authentication,
and auto-documentation generation (README, API docs, changelog).
"""

from __future__ import annotations

import contextlib
import httpx
import json
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, Request

from ..services import llm, memory_db

router = APIRouter(prefix='/api/integrations', tags=['integrations'])
log = logging.getLogger('agentic.integrations')

ROOT = Path(__file__).resolve().parents[2]  # /home/user/agentic-os
PREVIEW_DIR = ROOT / 'preview'
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


# ── Available integrations catalogue ──────────────────────────────────────────
INTEGRATIONS = [
    {
        'id': 'stripe-payments',
        'name': 'Stripe Payments',
        'category': 'payments',
        'emoji': '💳',
        'description': 'Add payment processing: checkout, subscriptions, webhooks, and customer portal',
        'env_vars': ['STRIPE_PUBLISHABLE_KEY', 'STRIPE_SECRET_KEY', 'STRIPE_WEBHOOK_SECRET'],
        'docs_url': 'https://stripe.com/docs',
        'tags': ['payments', 'stripe', 'checkout', 'subscription'],
    },
    {
        'id': 'auth-nextauth',
        'name': 'NextAuth.js Authentication',
        'category': 'auth',
        'emoji': '🔐',
        'description': 'Email, Google, GitHub OAuth with sessions. Works with any Next.js app',
        'env_vars': ['NEXTAUTH_SECRET', 'NEXTAUTH_URL', 'GOOGLE_CLIENT_ID', 'GITHUB_CLIENT_ID'],
        'docs_url': 'https://next-auth.js.org',
        'tags': ['auth', 'nextauth', 'oauth', 'sessions'],
    },
    {
        'id': 'auth-clerk',
        'name': 'Clerk Authentication',
        'category': 'auth',
        'emoji': '👤',
        'description': 'Complete user management with pre-built UI components. Easiest auth to set up',
        'env_vars': ['NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY', 'CLERK_SECRET_KEY'],
        'docs_url': 'https://clerk.com/docs',
        'tags': ['auth', 'clerk', 'users', 'login'],
    },
    {
        'id': 'supabase-full',
        'name': 'Supabase (DB + Auth + Storage)',
        'category': 'backend',
        'emoji': '☁️',
        'description': 'PostgreSQL database, authentication, file storage, and real-time subscriptions',
        'env_vars': ['NEXT_PUBLIC_SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_ANON_KEY'],
        'docs_url': 'https://supabase.com/docs',
        'tags': ['database', 'auth', 'storage', 'realtime'],
    },
    {
        'id': 'openai-api',
        'name': 'OpenAI API',
        'category': 'ai',
        'emoji': '🤖',
        'description': 'Add AI chat, completions, embeddings, and image generation to your app',
        'env_vars': ['OPENAI_API_KEY'],
        'docs_url': 'https://platform.openai.com/docs',
        'tags': ['ai', 'openai', 'gpt', 'chatgpt'],
    },
    {
        'id': 'resend-email',
        'name': 'Resend Email',
        'category': 'email',
        'emoji': '📧',
        'description': 'Send transactional emails with React Email templates. Simple API, high deliverability',
        'env_vars': ['RESEND_API_KEY'],
        'docs_url': 'https://resend.com/docs',
        'tags': ['email', 'transactional', 'notifications'],
    },
    {
        'id': 'upstash-redis',
        'name': 'Upstash Redis',
        'category': 'database',
        'emoji': '⚡',
        'description': 'Serverless Redis for caching, rate limiting, and session storage',
        'env_vars': ['UPSTASH_REDIS_REST_URL', 'UPSTASH_REDIS_REST_TOKEN'],
        'docs_url': 'https://upstash.com/docs',
        'tags': ['redis', 'cache', 'rate-limiting'],
    },
    {
        'id': 'analytics-posthog',
        'name': 'PostHog Analytics',
        'category': 'analytics',
        'emoji': '📊',
        'description': 'Product analytics: events, funnels, session recording, feature flags',
        'env_vars': ['NEXT_PUBLIC_POSTHOG_KEY', 'NEXT_PUBLIC_POSTHOG_HOST'],
        'docs_url': 'https://posthog.com/docs',
        'tags': ['analytics', 'tracking', 'events'],
    },
]

_INT_BY_ID = {i['id']: i for i in INTEGRATIONS}


# ── Helpers ────────────────────────────────────────────────────────────────────
def _safe_preview_path(filename: str) -> Path | None:
    """Resolve a filename inside PREVIEW_DIR, blocking path traversal."""
    # Strip any leading slashes / dotdot components from filename
    safe_name = Path(filename).name if '/' not in filename else Path(filename).as_posix().lstrip('/')
    dest = (PREVIEW_DIR / safe_name).resolve()
    if str(dest).startswith(str(PREVIEW_DIR.resolve())):
        return dest
    return None


# ── REST endpoints ─────────────────────────────────────────────────────────────


@router.get('')
def list_integrations(category: str = '', q: str = ''):
    """List all integrations, optionally filtered by category or search query."""
    results = list(INTEGRATIONS)
    if category:
        results = [i for i in results if i['category'] == category]
    if q:
        ql = q.lower()
        results = [
            i
            for i in results
            if ql in i['name'].lower() or ql in i['description'].lower() or any(ql in t for t in i['tags'])
        ]
    return results


@router.get('/categories')
def list_categories():
    """Retrieve and return list categories."""
    cats: dict = {}
    for i in INTEGRATIONS:
        c = i['category']
        cats[c] = cats.get(c, 0) + 1
    return [{'id': k, 'count': v} for k, v in sorted(cats.items())]


@router.post('/{integration_id}/scaffold')
async def scaffold_integration(integration_id: str, req: Request):
    """
    Scaffold an integration into the current project.
    Generates the necessary files, env var placeholders, and wiring code.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    framework = (body.get('framework') or 'web').strip()[:64]

    integration = _INT_BY_ID.get(integration_id)
    if not integration:
        return {'ok': False, 'error': f"Integration '{integration_id}' not found"}

    messages = [
        {
            'role': 'system',
            'content': f'You are an expert developer scaffolding {integration["name"]} for a {framework} project. '
            f'Generate COMPLETE, WORKING code. Include all necessary files. '
            f"Use placeholder values for API keys (e.g. 'YOUR_STRIPE_KEY'). "
            f'Make the code production-ready and well-commented. '
            f'Return multiple files using this format:\n'
            f'<FILE path="filename.ext">\ncomplete content\n</FILE>',
        },
        {
            'role': 'user',
            'content': f'Scaffold {integration["name"]} for a {framework} project.\n'
            f'Env vars needed: {", ".join(integration["env_vars"])}\n'
            f'Include: installation instructions in a comment, all necessary files, '
            f'example usage, and a working demo component.',
        },
    ]

    result = await llm.complete(messages, agent_id='builder', max_tokens=4096, temperature=0.3, inject_steering=False)
    code = result.get('text', '').strip()

    # Parse and save files
    saved_files = []
    file_pattern = re.compile(r'<FILE\s+path=["\']([^"\']+)["\']>(.*?)</FILE>', re.DOTALL)

    for m in file_pattern.finditer(code):
        fpath = m.group(1).strip()
        content = m.group(2).strip()
        dest = _safe_preview_path(fpath)
        if dest:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding='utf-8')
            saved_files.append(fpath)

    # If no structured files, save as a single guide file
    if not saved_files:
        guide_name = f'{integration_id}-setup.md'
        guide_path = PREVIEW_DIR / guide_name
        guide_path.write_text(f'# {integration["name"]} Setup\n\n{code}', encoding='utf-8')
        saved_files.append(guide_name)

    env_additions = '\n'.join(f'{v}=YOUR_{v}' for v in integration['env_vars'])

    memory_db.audit_log('integration_scaffold', f'{integration_id}: {len(saved_files)} files')
    return {
        'ok': True,
        'integration': integration['name'],
        'files': saved_files,
        'env_vars': integration['env_vars'],
        'env_example': env_additions,
        'docs_url': integration['docs_url'],
        'next_steps': [
            '1. Add env vars to your .env file',
            '2. Install required packages',
            '3. Import the generated components',
            f'4. See {integration["docs_url"]} for full docs',
        ],
    }


# ── Documentation Generator ────────────────────────────────────────────────────

VALID_DOC_TYPES = {'readme', 'api', 'changelog', 'contributing', 'architecture'}
FILENAME_MAP = {
    'readme': 'README.md',
    'api': 'API.md',
    'changelog': 'CHANGELOG.md',
    'contributing': 'CONTRIBUTING.md',
    'architecture': 'ARCHITECTURE.md',
}


@router.post('/docs/generate')
async def generate_docs(req: Request):
    """
    AI-powered documentation generator.
    Types: readme, api, changelog, contributing, architecture
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    doc_type = (body.get('type') or 'readme').strip().lower()

    if doc_type not in VALID_DOC_TYPES:
        return {'ok': False, 'error': f"Unknown doc type '{doc_type}'. Valid: {sorted(VALID_DOC_TYPES)}"}

    # Gather project context
    files: list = []
    if PREVIEW_DIR.exists():
        for f in sorted(PREVIEW_DIR.rglob('*'))[:30]:
            if f.is_file() and f.suffix in ('.js', '.jsx', '.ts', '.tsx', '.py', '.html', '.css'):
                try:
                    files.append(f.relative_to(PREVIEW_DIR).as_posix())
                except ValueError:
                    pass

    entry_content = ''
    entry = PREVIEW_DIR / 'index.html'
    if entry.exists():
        entry_content = entry.read_text(encoding='utf-8', errors='ignore')[:2000]

    prompts = {
        'readme': f"""Generate a comprehensive README.md for this project.
Project files: {', '.join(files[:15]) or 'No files yet'}
Entry file sample:
{entry_content[:1000]}

Include: project name/description, features, installation, usage, tech stack, contributing, license.
Use emoji section headers. Make it compelling and professional.""",
        'api': f"""Generate API documentation for this project.
Files: {', '.join(files[:15]) or 'No files yet'}
Document all endpoints, request/response formats, authentication, examples.
Format as markdown with code blocks.""",
        'changelog': f"""Generate a CHANGELOG.md for this project following Keep a Changelog format.
Project files: {', '.join(files[:15]) or 'No files yet'}
Include: [Unreleased] section, semantic versioning, categories (Added, Changed, Fixed, Removed).
Fill with plausible entries based on the project structure.""",
        'contributing': f"""Generate a CONTRIBUTING.md guide for this project.
Files: {', '.join(files[:10]) or 'No files yet'}
Include: code of conduct, how to contribute, development setup, PR process, coding standards.""",
        'architecture': f"""Generate an ARCHITECTURE.md document explaining the project structure.
Files: {', '.join(files[:20]) or 'No files yet'}
Include: overview diagram (ASCII), folder structure explanation, key design decisions, data flow.""",
    }

    prompt = prompts[doc_type]
    messages = [
        {
            'role': 'system',
            'content': 'You are a technical writer generating professional documentation. Return only the markdown content, no preamble.',
        },
        {'role': 'user', 'content': prompt},
    ]

    result = await llm.complete(
        messages, agent_id='researcher', max_tokens=3000, temperature=0.4, inject_steering=False
    )
    doc_content = result.get('text', '').strip()

    if not doc_content:
        return {'ok': False, 'error': 'LLM returned empty response', 'type': doc_type}

    filename = FILENAME_MAP[doc_type]
    out_path = PREVIEW_DIR / filename
    out_path.write_text(doc_content, encoding='utf-8')
    memory_db.audit_log('doc_generate', f'{doc_type}: {filename}')

    return {
        'ok': True,
        'type': doc_type,
        'content': doc_content,
        'filename': filename,
    }


@router.get('/docs/types')
def doc_types():
    """Execute or process doc types operation."""
    return [
        {'id': 'readme', 'label': '📖 README', 'desc': 'Project overview, installation, usage'},
        {'id': 'api', 'label': '🔌 API Docs', 'desc': 'Endpoint documentation with examples'},
        {'id': 'changelog', 'label': '📋 Changelog', 'desc': 'Version history (Keep a Changelog format)'},
        {'id': 'contributing', 'label': '🤝 Contributing', 'desc': 'How to contribute guide'},
        {'id': 'architecture', 'label': '🏗️ Architecture', 'desc': 'System design and structure overview'},
    ]


# ── Project Rules (.agenticrules) ─────────────────────────────────────────────
RULES_FILE = ROOT / '.agenticrules'  # /home/user/agentic-os/.agenticrules

_DEFAULT_RULES = """# .agenticrules — Project AI Rules
# These rules guide every AI agent in this workspace.

## Tech Stack
- Framework: Web (HTML/CSS/JS)
- Styling: Tailwind CSS via CDN
- Theme: Dark mode (background: #07080f, text: #f4f6ff)

## Code Style
- Use modern ES6+ JavaScript
- Prefer async/await over callbacks
- Always add error handling
- Use semantic HTML elements
- Mobile-first responsive design

## Agent Behavior
- Keep responses concise and actionable
- Generate complete, working code — no truncation
- Always include comments for complex logic
- Prefer composition over inheritance
"""


@router.get('/rules')
def get_project_rules():
    """Get the current project AI rules (.agenticrules file)."""
    if RULES_FILE.exists():
        try:
            content = RULES_FILE.read_text(errors='ignore')
            return {'ok': True, 'content': content, 'path': str(RULES_FILE), 'is_default': False}
        except Exception as ex:
            return {'ok': False, 'error': str(ex)}
    return {'ok': True, 'content': _DEFAULT_RULES, 'path': str(RULES_FILE), 'is_default': True}


@router.post('/rules')
async def save_project_rules(req: Request):
    """Save project AI rules."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    content = (body.get('content') or '').strip()
    if not content:
        return {'ok': False, 'error': 'content required — cannot save empty rules'}
    try:
        RULES_FILE.write_text(content, encoding='utf-8')
        memory_db.audit_log('rules_save', f'{len(content)} chars')
        return {'ok': True, 'path': str(RULES_FILE), 'length': len(content)}
    except Exception as ex:
        return {'ok': False, 'error': str(ex)}


# ════════════════════════════════════════════════════════════════
#  SPRINT 14 — Deep Stripe & Auth Integration
# ════════════════════════════════════════════════════════════════


@router.post('/stripe/wire')
async def stripe_wire(req: Request):
    """
    Generate real Stripe integration code wired into the preview.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    mode = (body.get('mode') or 'payment').strip()
    if mode not in ('payment', 'subscription', 'connect'):
        mode = 'payment'
    price_id = (body.get('price_id') or '').strip()[:128]
    product_name = (body.get('product_name') or 'Pro Plan').strip()[:128]
    try:
        amount_cents = max(0, int(body.get('amount_cents', 1999)))
    except (TypeError, ValueError):
        amount_cents = 1999
    currency = re.sub(r'[^a-z]', '', (body.get('currency') or 'usd').lower())[:3]
    target_file = (body.get('target_file') or 'checkout.html').strip()
    include_webhook = bool(body.get('include_webhook', True))

    stripe_key = os.getenv('STRIPE_SECRET_KEY', '')
    pub_key = os.getenv('STRIPE_PUBLISHABLE_KEY', '')

    from ..services import llm as llm_svc

    msgs = [
        {
            'role': 'system',
            'content': 'You are a senior full-stack developer. Generate complete, production-ready Stripe integration code. '
            'Include error handling, loading states, and best practices. Use Stripe.js v3.',
        },
        {
            'role': 'user',
            'content': f"Generate a complete Stripe {mode} integration for '{product_name}' "
            f'(amount: ${amount_cents / 100:.2f} {currency.upper()}, '
            f'price_id: {price_id or "YOUR_PRICE_ID"}).\n\n'
            f'Include:\n'
            f'1. Complete HTML + vanilla JS checkout page with Stripe Elements\n'
            f'2. Success and cancel redirect handling\n'
            f'3. Loading spinner and error display\n'
            f'4. {"Webhook handler (Python/FastAPI) for payment_intent.succeeded and checkout.session.completed" if include_webhook else ""}\n'
            f'5. Environment variable placeholders (STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY)\n\n'
            f'publishable_key={"pk_live_YOUR_KEY" if not pub_key else pub_key[:20] + "..."}\n'
            f'Return two sections: ### CHECKOUT_HTML and ### WEBHOOK_PYTHON',
        },
    ]
    result = await llm_svc.complete(msgs, agent_id='builder', max_tokens=3000, temperature=0.2, inject_steering=False)
    code = result.get('text', '')

    # Split into sections
    html_code = ''
    webhook_code = ''
    if '### CHECKOUT_HTML' in code:
        parts = code.split('### CHECKOUT_HTML')
        rest = parts[1] if len(parts) > 1 else code
        if '### WEBHOOK_PYTHON' in rest:
            html_code, webhook_code = rest.split('### WEBHOOK_PYTHON', 1)
        else:
            html_code = rest
    elif '```html' in code:
        m = re.search(r'```html\n(.*?)```', code, re.DOTALL)
        html_code = m.group(1) if m else code

    html_code = html_code.strip()
    webhook_code = webhook_code.strip()

    # Strip markdown fences if present
    if html_code.startswith('```'):
        html_code = '\n'.join(html_code.split('\n')[1:]).rstrip('`').strip()
    if webhook_code.startswith('```'):
        webhook_code = '\n'.join(webhook_code.split('\n')[1:]).rstrip('`').strip()

    saved_files = []
    if html_code:
        dest = _safe_preview_path(target_file)
        if dest:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(html_code, encoding='utf-8')
            saved_files.append(target_file)

    if webhook_code:
        wh_dest = _safe_preview_path('stripe_webhook.py')
        if wh_dest:
            wh_dest.write_text(webhook_code, encoding='utf-8')
            saved_files.append('stripe_webhook.py')

    memory_db.audit_log('stripe_wire', f'mode={mode} files={saved_files}')
    return {
        'ok': True,
        'mode': mode,
        'product_name': product_name,
        'html_code': (html_code[:500] + '...') if len(html_code) > 500 else html_code,
        'webhook_code': webhook_code[:200] if webhook_code else None,
        'saved_files': saved_files,
        'preview_url': f'/preview/{target_file}',
        'has_real_key': bool(stripe_key),
        'note': 'Set STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY in .env for live payments',
    }


@router.get('/stripe/products')
async def stripe_products():
    """List Stripe products/prices (live if key set, else mock data)."""
    key = os.getenv('STRIPE_SECRET_KEY', '')
    if key:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    'https://api.stripe.com/v1/prices?active=true&expand[]=data.product',
                    auth=(key, ''),
                )
                if r.status_code == 200:
                    data = r.json()
                    data['mock'] = False
                    return data
        except Exception as ex:
            log.warning('Stripe products fetch failed: %s', ex)

    return {
        'data': [
            {
                'id': 'price_starter_monthly',
                'nickname': 'Starter Monthly',
                'unit_amount': 999,
                'currency': 'usd',
                'recurring': {'interval': 'month'},
                'product': {'name': 'Starter Plan', 'description': 'Up to 3 projects'},
            },
            {
                'id': 'price_pro_monthly',
                'nickname': 'Pro Monthly',
                'unit_amount': 2999,
                'currency': 'usd',
                'recurring': {'interval': 'month'},
                'product': {'name': 'Pro Plan', 'description': 'Unlimited projects + API'},
            },
            {
                'id': 'price_enterprise',
                'nickname': 'Enterprise',
                'unit_amount': 9900,
                'currency': 'usd',
                'recurring': {'interval': 'month'},
                'product': {'name': 'Enterprise', 'description': 'Custom limits + SLA'},
            },
        ],
        'mock': True,
    }


@router.post('/stripe/checkout-session')
async def create_checkout_session(req: Request):
    """Create a Stripe Checkout session (live if key, else return test URL)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    price_id = (body.get('price_id') or 'price_starter_monthly').strip()[:128]
    mode = (body.get('mode') or 'subscription').strip()
    if mode not in ('payment', 'subscription'):
        mode = 'subscription'
    success = body.get('success_url', f'http://localhost:{os.getenv("AGENTIC_OS_PORT", "8787")}/preview/success.html')
    cancel = body.get('cancel_url', f'http://localhost:{os.getenv("AGENTIC_OS_PORT", "8787")}/preview/cancel.html')

    key = os.getenv('STRIPE_SECRET_KEY', '')
    if key:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    'https://api.stripe.com/v1/checkout/sessions',
                    auth=(key, ''),
                    data={
                        'mode': mode,
                        'line_items[0][price]': price_id,
                        'line_items[0][quantity]': '1',
                        'success_url': success,
                        'cancel_url': cancel,
                    },
                )
                if r.status_code == 200:
                    return {'ok': True, 'session': r.json(), 'mock': False}
                else:
                    return {'ok': False, 'error': f'Stripe error: {r.status_code}', 'detail': r.text[:200]}
        except Exception as ex:
            return {'ok': False, 'error': str(ex)}

    return {
        'ok': True,
        'session': {'id': 'cs_test_DEMO', 'url': 'https://checkout.stripe.com/demo'},
        'mock': True,
    }


@router.post('/auth/wire')
async def auth_wire(req: Request):
    """
    Generate working auth integration code wired into preview.
    Supports NextAuth, Clerk, Supabase Auth, Firebase Auth, Auth0.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    provider = (body.get('provider') or 'nextauth').strip()
    valid_providers = {'nextauth', 'clerk', 'supabase', 'firebase', 'auth0', 'magic'}
    if provider not in valid_providers:
        provider = 'nextauth'

    auth_file = (body.get('target_file') or 'auth.html').strip()
    # Validate oauth_providers list
    raw_oauth = body.get('oauth_providers', ['google', 'github'])
    valid_oauth = {'google', 'github', 'discord', 'twitter', 'facebook', 'apple', 'microsoft'}
    oauth = [o for o in (raw_oauth if isinstance(raw_oauth, list) else []) if o in valid_oauth]
    if not oauth:
        oauth = ['google', 'github']
    include_magic_link = bool(body.get('magic_link', True))

    # Get keys from vault/env
    available_keys: list = []
    con = memory_db.get_conn()
    try:
        rows = con.execute(
            "SELECT key FROM secrets WHERE key LIKE '%AUTH%' OR key LIKE '%CLERK%' OR key LIKE '%SUPABASE%'"
        ).fetchall()
        available_keys = [r['key'] for r in rows]
    except (memory_db.sqlite3.Error, KeyError, TypeError):
        pass
    finally:
        con.close()

    from ..services import llm as llm_svc

    msgs = [
        {
            'role': 'system',
            'content': 'You are a senior full-stack developer. Generate complete, secure auth integration code.',
        },
        {
            'role': 'user',
            'content': f'Generate a complete {provider} authentication integration.\n\n'
            f'OAuth providers to support: {", ".join(oauth)}\n'
            f'{"Include magic link/passwordless email login." if include_magic_link else ""}\n\n'
            f'Generate:\n'
            f'1. A complete HTML login page with all auth options, polished UI (dark theme, Inter font)\n'
            f'2. Session management example\n'
            f'3. Protected route pattern\n'
            f'4. Environment variables needed: list them with YOUR_KEY placeholders\n\n'
            f'Make it production-ready with loading states, error handling, and beautiful design.\n'
            f'Return HTML first (complete page), then Python/JS config snippets.',
        },
    ]
    result = await llm_svc.complete(msgs, agent_id='builder', max_tokens=3000, temperature=0.2, inject_steering=False)
    code = result.get('text', '')

    # Extract HTML
    html_code = ''
    m = re.search(r'<!DOCTYPE html>.*?</html>', code, re.DOTALL | re.IGNORECASE)
    if m:
        html_code = m.group(0)
    elif '```html' in code:
        m2 = re.search(r'```html\n(.*?)```', code, re.DOTALL)
        html_code = m2.group(1) if m2 else code
    else:
        html_code = code

    saved = []
    if html_code:
        dest = _safe_preview_path(auth_file)
        if dest:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(html_code, encoding='utf-8')
            saved.append(auth_file)

    memory_db.audit_log('auth_wire', f'provider={provider} files={saved}')
    return {
        'ok': True,
        'provider': provider,
        'oauth': oauth,
        'code_preview': code[:400],
        'saved_files': saved,
        'preview_url': f'/preview/{auth_file}',
        'available_keys': available_keys,
        'note': f'Set your {provider.upper()}_SECRET and related vars in Settings → API Keys',
    }


@router.get('/auth/providers')
def auth_providers():
    """List available auth providers and their status."""
    providers = [
        {
            'id': 'nextauth',
            'name': 'NextAuth.js',
            'icon': '🔐',
            'difficulty': 'medium',
            'env_vars': ['NEXTAUTH_SECRET', 'NEXTAUTH_URL', 'GOOGLE_CLIENT_ID', 'GITHUB_CLIENT_ID'],
            'docs': 'https://next-auth.js.org',
        },
        {
            'id': 'clerk',
            'name': 'Clerk',
            'icon': '👤',
            'difficulty': 'easy',
            'env_vars': ['NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY', 'CLERK_SECRET_KEY'],
            'docs': 'https://clerk.com/docs',
        },
        {
            'id': 'supabase',
            'name': 'Supabase Auth',
            'icon': '🚀',
            'difficulty': 'easy',
            'env_vars': ['SUPABASE_URL', 'SUPABASE_ANON_KEY'],
            'docs': 'https://supabase.com/docs/guides/auth',
        },
        {
            'id': 'firebase',
            'name': 'Firebase Auth',
            'icon': '🔥',
            'difficulty': 'medium',
            'env_vars': ['FIREBASE_API_KEY', 'FIREBASE_AUTH_DOMAIN', 'FIREBASE_PROJECT_ID'],
            'docs': 'https://firebase.google.com/docs/auth',
        },
        {
            'id': 'auth0',
            'name': 'Auth0',
            'icon': '🛡️',
            'difficulty': 'easy',
            'env_vars': ['AUTH0_DOMAIN', 'AUTH0_CLIENT_ID', 'AUTH0_CLIENT_SECRET'],
            'docs': 'https://auth0.com/docs',
        },
        {
            'id': 'magic',
            'name': 'Magic Link (Passwordless)',
            'icon': '✉️',
            'difficulty': 'easy',
            'env_vars': ['MAGIC_SECRET_KEY'],
            'docs': 'https://magic.link/docs',
        },
    ]
    for p in providers:
        p['configured'] = any(os.getenv(k) for k in p['env_vars'])
    return {'providers': providers}


@router.get('/{integration_id}')
def get_integration(integration_id: str):
    """Get details for a single integration by ID."""
    # Must come AFTER all static paths — but since all static paths have sub-segments
    # (e.g. /categories, /docs/types) they won't conflict with a single segment.
    integration = _INT_BY_ID.get(integration_id)
    if not integration:
        return {'ok': False, 'error': f"Integration '{integration_id}' not found"}
    return {**integration, 'ok': True}
