"""
Agentic OS — Plugin & Marketplace Router
Install community skills, agent personas, and tool packs from:
  - A curated registry (built-in)
  - Any GitHub URL (raw JSON)
  - Direct JSON paste
Plugins are verified, sandboxed, and stored locally.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/plugins', tags=['plugins'])
log = logging.getLogger('agentic.plugins')

from backend.config import get_data_dir

from ..services.request_body import as_text

ROOT = get_data_dir()
PLUGIN_DIR = ROOT / 'plugins'
PLUGIN_DIR.mkdir(exist_ok=True)
REGISTRY_URL = 'https://raw.githubusercontent.com/jstrick9/strick_tech/main/plugins/registry.json'

# ── Built-in registry (always available offline) ──────────────────────────────
BUILTIN_REGISTRY = [
    {
        'id': 'social-media-pack',
        'name': 'Social Media Pack',
        'version': '1.0.0',
        'author': 'Agentic OS',
        'category': 'marketing',
        'description': '6 skills: Twitter thread, LinkedIn post, Instagram caption, YouTube title, Reddit post, Product Hunt launch',
        'emoji': '📱',
        'tags': ['social', 'marketing', 'content'],
        'type': 'skill_pack',
        'skills': [
            {
                'id': 'twitter_thread',
                'name': 'Twitter Thread',
                'emoji': '🐦',
                'category': 'social',
                'agent': 'creative',
                'description': 'Write a viral Twitter thread on any topic',
                'inputs': [
                    {'id': 'topic', 'label': 'Topic', 'type': 'text', 'required': True},
                    {
                        'id': 'length',
                        'label': 'Length',
                        'type': 'select',
                        'required': False,
                        'options': ['5 tweets', '8 tweets', '12 tweets'],
                    },
                ],
                'prompt_template': 'Write a viral {length} Twitter/X thread about: {topic}\n\nFormat: numbered tweets (1/ 2/ etc), hook first tweet, value-packed middle, strong CTA last. Each tweet max 280 chars. Use line breaks, not walls of text.',
            },
            {
                'id': 'linkedin_post',
                'name': 'LinkedIn Post',
                'emoji': '💼',
                'category': 'social',
                'agent': 'creative',
                'description': 'Professional LinkedIn post that gets engagement',
                'inputs': [{'id': 'topic', 'label': 'Topic or story', 'type': 'textarea', 'required': True}],
                'prompt_template': 'Write a high-engagement LinkedIn post about: {topic}\n\nStructure: bold hook, short punchy paragraphs, real insight or story, clear takeaway, CTA. No corporate fluff. Sound human.',
            },
            {
                'id': 'instagram_caption',
                'name': 'Instagram Caption',
                'emoji': '📸',
                'category': 'social',
                'agent': 'creative',
                'description': 'Instagram caption with hashtags',
                'inputs': [
                    {'id': 'image_desc', 'label': 'Describe the image/content', 'type': 'textarea', 'required': True},
                    {
                        'id': 'tone',
                        'label': 'Tone',
                        'type': 'select',
                        'required': False,
                        'options': ['inspiring', 'funny', 'educational', 'promotional'],
                    },
                ],
                'prompt_template': 'Write an {tone} Instagram caption for: {image_desc}\n\nInclude: compelling first line (no cutoff), 2-3 sentence body, emoji usage, 15-20 relevant hashtags separated at end.',
            },
            {
                'id': 'youtube_title',
                'name': 'YouTube Optimizer',
                'emoji': '▶️',
                'category': 'social',
                'agent': 'researcher',
                'description': 'YouTube title, description, and tags',
                'inputs': [{'id': 'video_topic', 'label': 'Video topic', 'type': 'text', 'required': True}],
                'prompt_template': 'Optimize a YouTube video for: {video_topic}\n\nProvide: 5 title options (curiosity-gap, how-to, listicle, question, bold claim), full description (first 125 chars critical), 20 tags ranked by relevance, thumbnail text suggestion.',
            },
            {
                'id': 'reddit_post',
                'name': 'Reddit Post',
                'emoji': '🤖',
                'category': 'social',
                'agent': 'creative',
                'description': 'Reddit post that fits the community',
                'inputs': [
                    {'id': 'topic', 'label': 'Topic', 'type': 'text', 'required': True},
                    {'id': 'subreddit', 'label': 'Target subreddit', 'type': 'text', 'required': False},
                ],
                'prompt_template': 'Write a Reddit post for r/{subreddit} about: {topic}\n\nBe authentic, add value, no self-promotion tone. Include a good title, detailed body with formatting, and end with a genuine question to spark discussion.',
            },
            {
                'id': 'product_hunt',
                'name': 'Product Hunt Launch',
                'emoji': '🚀',
                'category': 'social',
                'agent': 'creative',
                'description': 'Product Hunt launch copy that gets upvotes',
                'inputs': [
                    {'id': 'product', 'label': 'Product name & what it does', 'type': 'textarea', 'required': True}
                ],
                'prompt_template': 'Write Product Hunt launch copy for: {product}\n\nProvide: tagline (60 chars max), description (260 chars), first comment (maker intro, story, ask for feedback), 5 topics/tags to select.',
            },
        ],
    },
    {
        'id': 'dev-toolkit',
        'name': 'Developer Toolkit',
        'version': '1.0.0',
        'author': 'Agentic OS',
        'category': 'development',
        'description': '5 skills: README writer, Dockerfile generator, GitHub Actions CI, Database schema designer, API mock generator',
        'emoji': '🛠️',
        'tags': ['dev', 'code', 'devops'],
        'type': 'skill_pack',
        'skills': [
            {
                'id': 'readme_writer',
                'name': 'README Writer',
                'emoji': '📖',
                'category': 'development',
                'agent': 'builder',
                'description': 'Generate a professional README.md',
                'inputs': [
                    {'id': 'project', 'label': 'Project name & description', 'type': 'textarea', 'required': True},
                    {'id': 'stack', 'label': 'Tech stack', 'type': 'text', 'required': False},
                ],
                'prompt_template': 'Write a professional README.md for: {project}\nStack: {stack}\n\nInclude: badges, description, features, installation, usage with code examples, API reference (if applicable), contributing guide, license. Use proper Markdown.',
            },
            {
                'id': 'dockerfile',
                'name': 'Dockerfile Generator',
                'emoji': '🐳',
                'category': 'development',
                'agent': 'builder',
                'description': 'Production-ready Dockerfile + compose',
                'inputs': [
                    {'id': 'app_desc', 'label': 'App description', 'type': 'textarea', 'required': True},
                    {'id': 'language', 'label': 'Language/Framework', 'type': 'text', 'required': True},
                ],
                'prompt_template': 'Generate a production-ready Dockerfile for: {app_desc}\nLanguage: {language}\n\nInclude: multi-stage build, non-root user, health check, .dockerignore, docker-compose.yml with volumes, env vars, restart policy.',
            },
            {
                'id': 'github_actions',
                'name': 'GitHub Actions CI',
                'emoji': '⚙️',
                'category': 'development',
                'agent': 'builder',
                'description': 'Complete CI/CD pipeline YAML',
                'inputs': [
                    {'id': 'project_type', 'label': 'Project type', 'type': 'text', 'required': True},
                    {
                        'id': 'deploy_target',
                        'label': 'Deploy target',
                        'type': 'select',
                        'required': False,
                        'options': ['Vercel', 'Railway', 'Fly.io', 'AWS', 'none'],
                    },
                ],
                'prompt_template': 'Create a GitHub Actions CI/CD pipeline for: {project_type}\nDeploy to: {deploy_target}\n\nInclude: lint, test, build stages, caching, secrets handling, branch protection triggers, deploy step with rollback on failure.',
            },
            {
                'id': 'db_schema',
                'name': 'Database Schema Designer',
                'emoji': '🗄️',
                'category': 'development',
                'agent': 'builder',
                'description': 'SQL schema from natural language',
                'inputs': [
                    {'id': 'description', 'label': 'Describe your data model', 'type': 'textarea', 'required': True},
                    {
                        'id': 'db_type',
                        'label': 'Database',
                        'type': 'select',
                        'required': False,
                        'options': ['PostgreSQL', 'MySQL', 'SQLite', 'MongoDB'],
                    },
                ],
                'prompt_template': 'Design a {db_type} database schema for: {description}\n\nProvide: CREATE TABLE statements, indexes, foreign keys, sample seed data (INSERT), ERD diagram (ASCII), migration script.',
            },
            {
                'id': 'api_mock',
                'name': 'API Mock Generator',
                'emoji': '🔌',
                'category': 'development',
                'agent': 'builder',
                'description': 'Mock REST API with realistic fake data',
                'inputs': [{'id': 'api_desc', 'label': 'Describe the API', 'type': 'textarea', 'required': True}],
                'prompt_template': 'Generate a complete mock REST API for: {api_desc}\n\nProvide: JSON Schema for all models, realistic mock data (10+ records), Express.js mock server code, Postman collection JSON, curl examples for every endpoint.',
            },
        ],
    },
    {
        'id': 'founder-os',
        'name': 'Solo Founder OS',
        'version': '1.0.0',
        'author': 'Agentic OS',
        'category': 'business',
        'description': '6 skills for solo founders: business plan, pricing strategy, investor email, cold outreach, user interview script, retention analysis',
        'emoji': '👨‍💼',
        'tags': ['founder', 'business', 'saas'],
        'type': 'skill_pack',
        'skills': [
            {
                'id': 'business_plan',
                'name': 'Business Plan',
                'emoji': '📋',
                'category': 'business',
                'agent': 'researcher',
                'description': 'One-page business plan',
                'inputs': [{'id': 'idea', 'label': 'Business idea', 'type': 'textarea', 'required': True}],
                'prompt_template': 'Write a concise one-page business plan for: {idea}\n\nSections: Problem, Solution, Market Size (TAM/SAM/SOM), Business Model, Go-to-Market, Competitive Advantage, Team (placeholder), Financials (Year 1 projections), Ask.',
            },
            {
                'id': 'pricing_strategy',
                'name': 'Pricing Strategy',
                'emoji': '💰',
                'category': 'business',
                'agent': 'researcher',
                'description': 'SaaS pricing tiers and strategy',
                'inputs': [
                    {'id': 'product', 'label': 'Product description', 'type': 'textarea', 'required': True},
                    {'id': 'competitors', 'label': 'Key competitors', 'type': 'text', 'required': False},
                ],
                'prompt_template': 'Design a SaaS pricing strategy for: {product}\nCompetitors: {competitors}\n\nProvide: 3 pricing tiers (names, prices, features), psychological anchoring strategy, annual discount recommendation, freemium vs free-trial analysis, churn-reduction pricing tactics.',
            },
            {
                'id': 'investor_email',
                'name': 'Investor Cold Email',
                'emoji': '📧',
                'category': 'business',
                'agent': 'creative',
                'description': 'Cold email to VCs/angels that gets replies',
                'inputs': [
                    {'id': 'startup', 'label': 'Startup description & traction', 'type': 'textarea', 'required': True},
                    {'id': 'ask', 'label': 'Funding ask', 'type': 'text', 'required': False},
                ],
                'prompt_template': 'Write a cold investor email for: {startup}\nAsk: {ask}\n\nFormat: subject line (3 options), 5-sentence email body (problem, solution, traction, ask, CTA), P.S. line. No fluff, lead with traction.',
            },
            {
                'id': 'cold_outreach',
                'name': 'Cold Outreach Sequence',
                'emoji': '🎯',
                'category': 'business',
                'agent': 'creative',
                'description': '5-touch outreach sequence for B2B sales',
                'inputs': [
                    {'id': 'product', 'label': "What you're selling", 'type': 'text', 'required': True},
                    {'id': 'icp', 'label': 'Ideal customer profile', 'type': 'text', 'required': True},
                ],
                'prompt_template': 'Write a 5-touch cold outreach sequence selling {product} to {icp}.\n\nFor each touch: channel (email/LinkedIn/call), day number, subject/message, goal. Value-first approach, personalization hooks, clear CTAs. Include objection handling for top 3 objections.',
            },
            {
                'id': 'user_interview',
                'name': 'User Interview Script',
                'emoji': '🎤',
                'category': 'business',
                'agent': 'researcher',
                'description': 'Jobs-to-be-done user interview script',
                'inputs': [{'id': 'product', 'label': 'Product/problem area', 'type': 'text', 'required': True}],
                'prompt_template': 'Create a Jobs-to-be-Done user interview script for: {product}\n\nInclude: 5-minute intro, 15 core questions (timeline, context, emotional triggers, current solutions, willingness to pay), probing follow-ups, closing. Avoid leading questions.',
            },
            {
                'id': 'retention_analysis',
                'name': 'Retention Analysis',
                'emoji': '📊',
                'category': 'business',
                'agent': 'researcher',
                'description': 'Churn analysis and retention improvement plan',
                'inputs': [
                    {'id': 'product', 'label': 'Product & current churn symptoms', 'type': 'textarea', 'required': True}
                ],
                'prompt_template': 'Analyze retention for: {product}\n\nProvide: top 5 churn reasons (hypothesis), retention metrics to track (cohort, NRR, NPS), 10 tactical improvements ranked by effort/impact, 30-60-90 day retention roadmap, email sequences for at-risk users.',
            },
        ],
    },
    {
        'id': 'research-assistant',
        'name': 'Research Assistant',
        'version': '1.0.0',
        'author': 'Agentic OS',
        'category': 'research',
        'description': '5 skills: literature review, trend analysis, technical explainer, fact-check, bibliography generator',
        'emoji': '🔬',
        'tags': ['research', 'analysis', 'academic'],
        'type': 'skill_pack',
        'skills': [
            {
                'id': 'lit_review',
                'name': 'Literature Review',
                'emoji': '📚',
                'category': 'research',
                'agent': 'researcher',
                'description': 'Structured literature review on any topic',
                'inputs': [
                    {'id': 'topic', 'label': 'Research topic', 'type': 'text', 'required': True},
                    {
                        'id': 'depth',
                        'label': 'Depth',
                        'type': 'select',
                        'required': False,
                        'options': ['overview', 'detailed', 'comprehensive'],
                    },
                ],
                'prompt_template': 'Write a {depth} literature review on: {topic}\n\nStructure: introduction, key themes with citations (use [Author, Year] format), contradictions in the literature, research gaps, methodology comparison, conclusion. Academic tone.',
            },
            {
                'id': 'trend_analysis',
                'name': 'Trend Analysis',
                'emoji': '📈',
                'category': 'research',
                'agent': 'researcher',
                'description': 'Identify and analyse emerging trends',
                'inputs': [
                    {'id': 'industry', 'label': 'Industry or topic', 'type': 'text', 'required': True},
                    {
                        'id': 'horizon',
                        'label': 'Time horizon',
                        'type': 'select',
                        'required': False,
                        'options': ['6 months', '1 year', '3 years', '5 years'],
                    },
                ],
                'prompt_template': 'Analyse trends in {industry} over a {horizon} horizon.\n\nInclude: 5 macro trends with evidence, early signals & weak signals, technology drivers, regulatory factors, consumer behaviour shifts, opportunities & threats matrix, confidence levels.',
            },
            {
                'id': 'tech_explainer',
                'name': 'Technical Explainer',
                'emoji': '💡',
                'category': 'research',
                'agent': 'brain',
                'description': 'Explain any technical concept at multiple levels',
                'inputs': [
                    {'id': 'concept', 'label': 'Technical concept', 'type': 'text', 'required': True},
                    {
                        'id': 'audience',
                        'label': 'Target audience',
                        'type': 'select',
                        'required': False,
                        'options': ['5-year-old', 'beginner', 'intermediate', 'expert'],
                    },
                ],
                'prompt_template': "Explain '{concept}' to a {audience}.\n\nUse: analogy, core explanation, worked example, common misconceptions, why it matters, further reading (3 resources). Adjust complexity to {audience} level.",
            },
            {
                'id': 'fact_check',
                'name': 'Fact Checker',
                'emoji': '✅',
                'category': 'research',
                'agent': 'researcher',
                'description': 'Verify claims and identify misinformation',
                'inputs': [
                    {'id': 'claim', 'label': 'Claim or statement to verify', 'type': 'textarea', 'required': True}
                ],
                'prompt_template': "Fact-check this claim: '{claim}'\n\nProvide: verdict (True/False/Misleading/Unverifiable), evidence for and against, context that matters, original source if known, confidence level (0-100%), nuance that's often missed.",
            },
            {
                'id': 'bibliography',
                'name': 'Bibliography Generator',
                'emoji': '📑',
                'category': 'research',
                'agent': 'builder',
                'description': 'Generate formatted citations from a list of sources',
                'inputs': [
                    {
                        'id': 'sources',
                        'label': 'Paste source titles, URLs, or descriptions',
                        'type': 'textarea',
                        'required': True,
                    },
                    {
                        'id': 'style',
                        'label': 'Citation style',
                        'type': 'select',
                        'required': False,
                        'options': ['APA 7th', 'MLA 9th', 'Chicago', 'Harvard', 'IEEE'],
                    },
                ],
                'prompt_template': "Generate {style} citations for these sources:\n{sources}\n\nFormat each citation correctly per {style} guidelines. If info is incomplete, note what's missing. Include an annotated bibliography entry (2 sentences) for each.",
            },
        ],
    },
]


# Ids in the SHIPPED registry, captured before custom plugins are appended.
# Must be taken here: _load_custom_registry() and _install_plugin_data() both
# append to BUILTIN_REGISTRY, so a membership test taken any later would label
# every custom plugin "builtin" -- which is precisely the distinction the
# provenance record exists to make.
_BUILTIN_IDS: frozenset[str] = frozenset(p['id'] for p in BUILTIN_REGISTRY if p.get('id'))


# ── Load custom plugins on startup ───────────────────────────────────────────
def _load_custom_registry():
    """Load custom plugins persisted from URL/JSON installs."""
    custom_reg_file = PLUGIN_DIR / 'custom_registry.json'
    if custom_reg_file.exists():
        try:
            custom = json.loads(custom_reg_file.read_text())
            existing_ids = {p['id'] for p in BUILTIN_REGISTRY}
            for p in custom:
                if p.get('id') and p['id'] not in existing_ids:
                    BUILTIN_REGISTRY.append(p)
        except Exception as e:
            log.warning('Failed to load custom registry: %s', e)


_load_custom_registry()


# ── Installed plugins store ────────────────────────────────────────────────────
def _is_builtin(plugin_id: str) -> bool:
    return plugin_id in _BUILTIN_IDS


def _content_hash(plugin: dict) -> str:
    """Stable hash of a pack's functional content (ignores presentation)."""
    payload = json.dumps(
        {
            'id': plugin.get('id'),
            'skills': [
                {
                    'id': sk.get('id'),
                    'prompt_template': sk.get('prompt_template'),
                }
                for sk in (plugin.get('skills') or [])
                if isinstance(sk, dict)
            ],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _load_installed() -> dict:
    f = PLUGIN_DIR / 'installed.json'
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    return {}


def _save_installed(data: dict) -> bool:
    try:
        (PLUGIN_DIR / 'installed.json').write_text(json.dumps(data, indent=2))
        return True
    except Exception as e:
        log.error('Failed to save installed.json: %s', e)
        return False


# ── Endpoints ──────────────────────────────────────────────────────────────────
# ── SSRF guard for /install/url ────────────────────────────────────────────────
# Verified live before this fix: the server fetched
#   http://localhost:8787/api/health          -> reached its own API
#   http://169.254.169.254/latest/meta-data/  -> reached cloud metadata (HTTP 401,
#                                                i.e. the connection SUCCEEDED)
# "Install a plugin from a URL" is a server-side fetch of a user-supplied
# address, which is the textbook SSRF primitive. On a hosted deployment the
# metadata endpoint hands out cloud credentials, and the error message returned
# the response body straight back to the caller, making it a read primitive
# rather than just a blind one.
# The SSRF guard this module introduced now lives in services/safe_fetch.py.
# Module 20 found the identical primitive unguarded in two MORE places (the
# http.get MCP tool and the outbound-webhook connector) precisely because this
# copy was local to a router and could not be reused. One implementation, one
# place, with a repo-wide test that fails when a new outbound call skips it.
from ..services.safe_fetch import url_is_safe as _shared_url_is_safe


def _url_is_safe(url: str) -> tuple[bool, str]:
    """Kept as a thin alias: existing tests and call sites reference this name."""
    return _shared_url_is_safe(url)


@router.get('/registry')
def list_registry():
    """Return the curated plugin registry."""
    installed = _load_installed()
    return [
        {**p, 'installed': p['id'] in installed, 'skills': None, 'skill_count': len(p.get('skills', []))}
        for p in BUILTIN_REGISTRY
    ]


@router.get('/installed')
def list_installed():
    """Retrieve and return list installed."""
    installed = _load_installed()
    return list(installed.values())


@router.post('/install/url')
async def install_from_url(req: Request):
    """Install a plugin from a raw JSON URL (GitHub, etc.)."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    url = as_text(body.get('url'))
    if not url:
        return JSONResponse({'ok': False, 'error': 'url required'}, status_code=400)

    # Convert GitHub blob URL to raw
    url = re.sub(r'github\.com/([^/]+/[^/]+)/blob/', r'raw.githubusercontent.com/\1/', url)

    ok, reason = _url_is_safe(url)
    if not ok:
        log.warning('Refused plugin fetch from %s: %s', url, reason)
        return JSONResponse({'ok': False, 'error': reason, 'blocked': True}, status_code=400)

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            resp = await client.get(url, headers={'User-Agent': 'AgenticOS/6.0'})
            # Redirects are NOT followed: a public URL that 302s to
            # 169.254.169.254 would otherwise walk straight past the check above.
            if resp.is_redirect:
                return JSONResponse(
                    {'ok': False, 'error': 'Refusing to follow redirects when fetching a plugin.'},
                    status_code=400,
                )
            resp.raise_for_status()
            if len(resp.content) > 2_000_000:
                return JSONResponse(
                    {'ok': False, 'error': 'Plugin file too large (limit 2 MB).'}, status_code=413
                )
            data = resp.json()
    except Exception as e:
        # The upstream response body is deliberately NOT echoed back: doing so
        # turned a blind SSRF into a read primitive.
        log.warning('Plugin fetch failed for %s: %s', url, e)
        return JSONResponse(
            {'ok': False, 'error': 'Could not fetch or parse a plugin from that URL.'},
            status_code=400,
        )

    if isinstance(data, dict):
        data['_origin'] = 'url'
        data['_origin_url'] = url[:400]
    return await _install_plugin_data(data)


@router.post('/install/json')
async def install_from_json(req: Request):
    """Install a plugin from pasted JSON."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    data = body.get('plugin_json') or body
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return {'ok': False, 'error': 'Invalid JSON'}
    return await _install_plugin_data(data)


async def _install_plugin_data(data: dict) -> dict:
    """Validate and install plugin from dict."""
    if not isinstance(data, dict):
        return JSONResponse({'ok': False, 'error': 'Plugin must be a JSON object'}, status_code=400)
    if not isinstance(data.get('skills'), list):
        return JSONResponse(
            {'ok': False, 'error': "Plugin must have a 'skills' array"}, status_code=400
        )

    # Static safety review. skills.run_skill() renders templates with
    # `template.format(**inputs)`, and Python's format mini-language evaluates
    # attribute access -- so a plugin-supplied template is executable to a
    # degree. Verified live against an installed skill:
    #     template : "Value: {topic.__class__.__mro__}"
    #     rendered : "Value: (<class 'str'>, <class 'object'>)"
    # Refused outright: a template has no legitimate reason to reach through an
    # attribute. Injection-shaped text is only WARNED about -- see
    # services/plugin_safety.py for why the two are treated differently.
    from ..services.plugin_safety import review_pack

    review = review_pack(data)
    if not review['safe']:
        log.warning('Refused unsafe plugin %s: %s', data.get('id'), review['errors'])
        return JSONResponse(
            {
                'ok': False,
                'error': 'Plugin rejected by the safety check.',
                'problems': review['errors'],
                'warnings': review['warnings'],
                'unsafe': True,
            },
            status_code=400,
        )
    if review['warnings']:
        log.warning('Plugin %s installed with warnings: %s', data.get('id'), review['warnings'])

    plugin_id = data.get('id') or hashlib.sha256(str(data).encode()).hexdigest()[:12]
    data['id'] = plugin_id

    # Persist custom plugin to custom registry file
    custom_reg_file = PLUGIN_DIR / 'custom_registry.json'
    try:
        custom_reg = json.loads(custom_reg_file.read_text()) if custom_reg_file.exists() else []
        if not any(p.get('id') == plugin_id for p in custom_reg):
            custom_reg.append(data)
            custom_reg_file.write_text(json.dumps(custom_reg, indent=2))
    except Exception as e:
        log.warning('Failed to persist custom plugin: %s', e)

    data.setdefault('_origin', 'json')
    data['_warnings'] = review['warnings']

    if not any(p.get('id') == plugin_id for p in BUILTIN_REGISTRY):
        BUILTIN_REGISTRY.append(data)
    return await install_plugin(plugin_id, None)


@router.post('/install/{plugin_id}')
async def install_plugin(plugin_id: str, req: Request):
    """Install a plugin from the registry."""
    plugin = next((p for p in BUILTIN_REGISTRY if p['id'] == plugin_id), None)
    if not plugin:
        return JSONResponse(
            {'ok': False, 'error': f"Plugin '{plugin_id}' not found in registry"}, status_code=404
        )

    installed = _load_installed()
    if plugin_id in installed:
        return JSONResponse(
            {'ok': False, 'error': 'Already installed', 'installed': True}, status_code=409
        )

    # BUG FIX: review_pack() ran at the BOTTOM of this function, after
    # save_skills() had already written the pack to disk -- so it was a report,
    # not a gate. The registry is curated today, which is why nothing had
    # escaped through it, but "the input happens to be trustworthy" is not a
    # safety property; it is the same reasoning that left /import open. Review
    # first and refuse, consistent with every other install door.
    from ..services.plugin_safety import review_pack

    review = review_pack(plugin)
    if not review['safe']:
        return JSONResponse(
            {
                'ok': False,
                'error': 'Plugin rejected by the safety check.',
                'problems': review['errors'],
                'warnings': review['warnings'],
                'unsafe': True,
            },
            status_code=400,
        )

    # Install skills into the skills system
    from .skills import load_skills, save_skills

    skills = load_skills()
    existing_ids = {s['id'] for s in skills}
    added = 0
    _REQUIRED_SKILL_FIELDS = {'id', 'name', 'prompt_template'}
    for skill in plugin.get('skills', []):
        if not isinstance(skill, dict):
            continue
        if not _REQUIRED_SKILL_FIELDS.issubset(skill.keys()):
            log.warning('Skipping malformed skill (missing required fields): %s', skill.get('id', '?'))
            continue
        if skill['id'] not in existing_ids:
            skills.append(skill)
            added += 1

    save_skills(skills)
    # Bracket access here assumed every field the BUILTIN_REGISTRY entries
    # happen to define. A custom plugin installed via /install/json or
    # /install/url legitimately omits them, and the endpoint crashed with
    # KeyError: 'version' -> HTTP 500. Reproduced live with a minimal
    # {id, name, skills} plugin, which is exactly what the documented
    # "paste your JSON" flow produces. Defaults applied instead.
    installed[plugin_id] = {
        'id': plugin['id'],
        'name': plugin.get('name') or plugin_id,
        'version': plugin.get('version') or '1.0.0',
        'author': plugin.get('author') or 'Community',
        'category': plugin.get('category') or 'community',
        'emoji': plugin.get('emoji') or '🧩',
        'skill_count': len(plugin.get('skills', [])),
        'installed_at': time.strftime('%Y-%m-%d'),
        # Provenance. Custom plugins arrive from an arbitrary URL or a paste and
        # were previously indistinguishable from curated content once installed:
        # nothing recorded where a pack came from, so a user could not audit
        # what they had trusted. `content_hash` also makes tampering detectable
        # -- if a pack's contents change, the recorded hash no longer matches.
        'origin': plugin.get('_origin') or ('builtin' if _is_builtin(plugin_id) else 'custom'),
        'origin_url': plugin.get('_origin_url', ''),
        'content_hash': _content_hash(plugin),
        'warnings': (plugin.get('_warnings') or [])[:20],
    }
    _save_installed(installed)

    from ..services.memory_db import audit_log

    audit_log('plugin_install', f'{plugin_id}: {added} skills added')

    _name = plugin.get('name') or plugin_id
    return {
        'ok': True,
        'plugin': _name,
        'skills_added': added,
        'warnings': review['warnings'],
        'message': f'✅ Installed {_name} — {added} skills added to Skills Hub',
    }


@router.delete('/uninstall/{plugin_id}')
@router.post('/uninstall/{plugin_id}')  # POST alias for compatibility
def uninstall_plugin(plugin_id: str):
    """Uninstall a plugin (removes its skills)."""
    plugin = next((p for p in BUILTIN_REGISTRY if p['id'] == plugin_id), None)
    if not plugin:
        return JSONResponse({'ok': False, 'error': 'Not found'}, status_code=404)

    from .skills import load_skills, save_skills

    installed = _load_installed()

    # Skills can be owned by MORE THAN ONE pack. Removing every id this pack
    # declares therefore breaks packs the user still has installed. Reproduced
    # live: dev-toolkit and devops-toolkit both ship `dockerfile`; uninstalling
    # dev-toolkit deleted it while devops-toolkit remained listed as installed
    # and silently lost a skill. linkedin_post (social-media-pack /
    # content-creator) has the same overlap.
    #
    # Only remove a skill when no OTHER still-installed pack claims it.
    retained_by_others: set[str] = set()
    for other_id in installed:
        if other_id == plugin_id:
            continue
        other = _find_pack_skills(other_id)
        retained_by_others |= {sk.get('id') for sk in other if isinstance(sk, dict)}

    pack_skill_ids = {sk['id'] for sk in plugin.get('skills', []) if isinstance(sk, dict) and sk.get('id')}
    to_remove = pack_skill_ids - retained_by_others
    kept_shared = sorted(pack_skill_ids & retained_by_others)

    # A skill the user has since edited is preserved rather than deleted. The
    # editor saves under a `_custom` id so the original is usually untouched,
    # but a skill carrying explicit user modification must never be removed by
    # an unrelated uninstall.
    survivors, removed = [], 0
    for sk in load_skills():
        sid = sk.get('id')
        if sid in to_remove and not sk.get('user_modified'):
            removed += 1
            continue
        survivors.append(sk)
    save_skills(survivors)

    installed.pop(plugin_id, None)
    _save_installed(installed)

    from ..services.memory_db import audit_log

    audit_log('plugin_uninstall', f'{plugin_id}: {removed} skills removed')
    return {
        'ok': True,
        'removed_skills': removed,
        'kept_shared_skills': kept_shared,
        'message': (
            f'Removed {removed} skill(s)'
            + (f'; kept {len(kept_shared)} still used by other plugins' if kept_shared else '')
        ),
    }


def _find_pack_skills(pack_id: str) -> list[dict]:
    """Skills declared by `pack_id` in EITHER backend.

    Ownership has to span both registries: the plugins backend and the
    marketplace both install into the same skills.json, so a plugins-side
    uninstall must respect a marketplace pack's claim and vice versa.
    """
    for pack in BUILTIN_REGISTRY:
        if pack.get('id') == pack_id:
            return pack.get('skills') or []
    try:
        from .marketplace import CURATED_PACKS

        for pack in CURATED_PACKS:
            if pack.get('id') == pack_id:
                return pack.get('skills') or []
    except Exception:  # pragma: no cover - marketplace optional
        pass
    return []


@router.get('/categories')
def plugin_categories():
    """Execute or process plugin categories operation."""
    cats = {}
    for p in BUILTIN_REGISTRY:
        c = p.get('category', 'other')
        cats[c] = cats.get(c, 0) + 1
    return [{'id': k, 'count': v} for k, v in sorted(cats.items())]


@router.get('/export')
def export_workspace():
    """Export entire workspace: agents, skills, settings, memory snapshot."""
    try:
        from ..services.memory_db import agents_list, memory_list
        from .skills import load_skills

        agents = agents_list()
        skills = load_skills()
        memories = memory_list(limit=200)
        installed = _load_installed()

        return {
            'version': '6.0',
            'exported': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'agents': agents,
            'skills': skills,
            'plugins': installed,
            'memories': [{'source': m['source'], 'content': m['content'][:500], 'tags': m['tags']} for m in memories],
        }
    except Exception as e:
        log.error('export_workspace error: %s', e)
        return {'ok': False, 'error': str(e)}


@router.post('/import')
async def import_workspace(req: Request):
    """Import agents, skills, plugins from an export JSON.

    SECURITY FIX — this was the safety scanner's own bypass.

    Every other way a skill can enter the platform runs it past
    `plugin_safety.review_pack()`, which REFUSES format-string traversal:
    `skills.run_skill()` renders templates with `template.format(**inputs)`, and
    Python's format mini-language evaluates attribute access, so a template is
    executable to a degree. This endpoint appended `data['skills']` straight to
    skills.json with no review at all.

    Verified live, the same payload through both doors:

        POST /api/plugins/install/json  {"prompt_template": "{topic.__class__.__mro__}"}
          -> 400 "Plugin rejected by the safety check."
        POST /api/plugins/import        (identical skill)
          -> 200 {"ok": true, "imported": {"skills": 1}}

    and the smuggled template then rendered:

        "Value: {topic.__class__.__mro__}"  ->  "Value: (<class 'str'>, <class 'object'>)"

    An export file is exactly the artefact a user is most likely to accept from
    someone else ("here is my workspace"), so the least-reviewed door was also
    the most socially trusted one. It now runs the same review as the front
    door, and refuses on the same grounds.
    """
    try:
        body = await req.json()
    except Exception:
        body = {}
    # `body.get` assumed an object. A bare JSON array or string body raised
    # AttributeError BEFORE the isinstance check below and still produced a 500
    # -- found by this module's own parametrised malformed-payload test after
    # the first fix, which is exactly what that test is for.
    data = body.get('workspace') or body if isinstance(body, dict) else body
    if not isinstance(data, dict):
        return JSONResponse(
            {'ok': False, 'error': 'Import payload must be a JSON object'}, status_code=400
        )

    imported = {'agents': 0, 'skills': 0, 'memories': 0}
    rejected: list[str] = []
    warnings: list[str] = []

    # Import agents
    agents_in = data.get('agents')
    if isinstance(agents_in, list):
        from ..services.memory_db import agent_upsert

        for agent in agents_in:
            if not isinstance(agent, dict):
                continue
            try:
                agent_upsert(agent)
                imported['agents'] += 1
            except Exception:
                pass

    # Import skills — reviewed exactly as an installed pack is.
    skills_in = data.get('skills')
    # Two overlapping guards on purpose: this one rejects a non-list `skills`
    # wholesale, and the per-entry isinstance below rejects junk items. Removing
    # THIS one alone changes no observable behaviour (proven by revert-proof:
    # zero tests fail), because a string is iterable and its characters are then
    # each refused by the inner guard. It stays as the cheaper, clearer check --
    # but the inner one is the load-bearing one, which is why the malformed-
    # payload tests target that.
    if isinstance(skills_in, list):
        from ..services.plugin_safety import review_skill
        from .skills import load_skills, save_skills

        all_skills = load_skills()
        current = {s['id'] for s in all_skills}
        for skill in skills_in:
            # These shapes used to raise AttributeError on skill.get(...) and
            # took the whole endpoint out with an unhandled HTTP 500. Verified:
            # {"skills": "not-a-list"} and {"skills": [null, "a string"]} both
            # returned "Internal Server Error".
            if not isinstance(skill, dict) or not skill.get('id'):
                continue
            review = review_skill(skill)
            if review['errors']:
                rejected.extend(f'{review["name"]}: {e}' for e in review['errors'])
                continue
            warnings.extend(f'{review["name"]}: {w}' for w in review['warnings'])
            if skill['id'] not in current:
                all_skills.append(skill)
                current.add(skill['id'])
                imported['skills'] += 1
        save_skills(all_skills)

    # Import memories
    memories_in = data.get('memories')
    if isinstance(memories_in, list):
        from ..services.memory_db import memory_add

        for m in memories_in:
            if isinstance(m, dict) and m.get('content'):
                memory_add(m.get('source', 'import'), str(m['content']), m.get('tags', ''))
                imported['memories'] += 1

    from ..services.memory_db import audit_log

    audit_log(
        'workspace_import',
        f'{imported} rejected={len(rejected)}',
    )
    return {
        # A partial import is not a clean success. If anything was refused the
        # caller must be told, or a workspace silently arrives incomplete.
        'ok': not rejected,
        'imported': imported,
        'rejected': rejected,
        'rejected_count': len(rejected),
        'warnings': warnings[:20],
        'error': (
            None
            if not rejected
            else f'{len(rejected)} skill(s) were refused by the safety check and NOT imported.'
        ),
    }
