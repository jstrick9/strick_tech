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
from pathlib import Path

import httpx
from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/plugins', tags=['plugins'])
log = logging.getLogger('agentic.plugins')

from backend.config import get_data_dir
ROOT = get_data_dir()
PLUGIN_DIR = ROOT / 'plugins'
PLUGIN_DIR.mkdir(exist_ok=True)
REGISTRY_URL = 'https://raw.githubusercontent.com/jstrick9/agentic-os/main/plugins/registry.json'

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
    url = (body.get('url') or '').strip()
    if not url:
        return {'ok': False, 'error': 'url required'}

    # Convert GitHub blob URL to raw
    url = re.sub(r'github\.com/([^/]+/[^/]+)/blob/', r'raw.githubusercontent.com/\1/', url)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={'User-Agent': 'AgenticOS/6.0'})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return {'ok': False, 'error': f'Failed to fetch: {e}'}

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
        return {'ok': False, 'error': 'Plugin must be a JSON object'}
    if 'skills' not in data:
        return {'ok': False, 'error': "Plugin must have a 'skills' array"}

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

    if not any(p.get('id') == plugin_id for p in BUILTIN_REGISTRY):
        BUILTIN_REGISTRY.append(data)
    return await install_plugin(plugin_id, None)


@router.post('/install/{plugin_id}')
async def install_plugin(plugin_id: str, req: Request):
    """Install a plugin from the registry."""
    plugin = next((p for p in BUILTIN_REGISTRY if p['id'] == plugin_id), None)
    if not plugin:
        return {'ok': False, 'error': f"Plugin '{plugin_id}' not found in registry"}

    installed = _load_installed()
    if plugin_id in installed:
        return {'ok': False, 'error': 'Already installed', 'installed': True}

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
    installed[plugin_id] = {
        'id': plugin['id'],
        'name': plugin['name'],
        'version': plugin['version'],
        'author': plugin['author'],
        'category': plugin['category'],
        'emoji': plugin['emoji'],
        'skill_count': len(plugin.get('skills', [])),
        'installed_at': time.strftime('%Y-%m-%d'),
    }
    _save_installed(installed)

    from ..services.memory_db import audit_log

    audit_log('plugin_install', f'{plugin_id}: {added} skills added')

    return {
        'ok': True,
        'plugin': plugin['name'],
        'skills_added': added,
        'message': f'✅ Installed {plugin["name"]} — {added} skills added to Skills Hub',
    }


@router.delete('/uninstall/{plugin_id}')
@router.post('/uninstall/{plugin_id}')  # POST alias for compatibility
def uninstall_plugin(plugin_id: str):
    """Uninstall a plugin (removes its skills)."""
    plugin = next((p for p in BUILTIN_REGISTRY if p['id'] == plugin_id), None)
    if not plugin:
        return {'ok': False, 'error': 'Not found'}

    from .skills import load_skills, save_skills

    skill_ids = {s['id'] for s in plugin.get('skills', [])}
    skills = [s for s in load_skills() if s['id'] not in skill_ids]
    save_skills(skills)

    installed = _load_installed()
    installed.pop(plugin_id, None)
    _save_installed(installed)

    from ..services.memory_db import audit_log

    audit_log('plugin_uninstall', plugin_id)
    return {'ok': True, 'removed_skills': len(skill_ids)}


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
    """Import agents, skills, plugins from an export JSON."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    data = body.get('workspace') or body

    imported = {'agents': 0, 'skills': 0, 'memories': 0}

    # Import agents
    if 'agents' in data:
        from ..services.memory_db import agent_upsert

        for agent in data['agents']:
            try:
                agent_upsert(agent)
                imported['agents'] += 1
            except Exception:
                pass

    # Import skills
    if 'skills' in data:
        from .skills import load_skills, save_skills

        current = {s['id'] for s in load_skills()}
        all_skills = load_skills()
        for skill in data['skills']:
            if skill.get('id') and skill['id'] not in current:
                all_skills.append(skill)
                imported['skills'] += 1
        save_skills(all_skills)

    # Import memories
    if 'memories' in data:
        from ..services.memory_db import memory_add

        for m in data['memories']:
            if m.get('content'):
                memory_add(m.get('source', 'import'), m['content'], m.get('tags', ''))
                imported['memories'] += 1

    from ..services.memory_db import audit_log

    audit_log('workspace_import', str(imported))
    return {'ok': True, 'imported': imported}
