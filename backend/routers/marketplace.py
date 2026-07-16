"""
Agentic OS — Plugin Marketplace CDN Router
Full marketplace with: versioned pack hosting, search/filter, ratings,
featured packs, auto-update checks, install/uninstall, changelogs.

Architecture:
  - Local CDN in workspaces/marketplace/ (served as static + API)
  - Each pack: manifest.json + optional assets/ + skills/
  - Versioned releases: packs/{id}/releases/{version}.zip
  - Ratings, download counts, reviews stored in SQLite
  - Auto-update polling endpoint
"""

from __future__ import annotations

import contextlib

import hashlib
import io
import json
import logging
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter(prefix='/api/marketplace', tags=['marketplace'])
log = logging.getLogger('agentic.marketplace')

ROOT = Path(__file__).resolve().parents[2]
MKT_DIR = ROOT / 'workspaces' / 'marketplace'
PACKS_DIR = MKT_DIR / 'packs'
ASSETS_DIR = MKT_DIR / 'assets'

MKT_DIR.mkdir(parents=True, exist_ok=True)
PACKS_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# ── DB schema ──────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS mkt_packs (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    description  TEXT DEFAULT '',
    icon         TEXT DEFAULT '🔧',
    author       TEXT DEFAULT '',
    author_url   TEXT DEFAULT '',
    license      TEXT DEFAULT 'MIT',
    category     TEXT DEFAULT 'utility',
    tags         TEXT DEFAULT '',
    homepage     TEXT DEFAULT '',
    repository   TEXT DEFAULT '',
    latest_ver   TEXT DEFAULT '1.0.0',
    downloads    INTEGER DEFAULT 0,
    rating_sum   REAL DEFAULT 0,
    rating_count INTEGER DEFAULT 0,
    featured     INTEGER DEFAULT 0,
    verified     INTEGER DEFAULT 0,
    published    INTEGER DEFAULT 1,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mkt_releases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id     TEXT NOT NULL,
    version     TEXT NOT NULL,
    changelog   TEXT DEFAULT '',
    zip_path    TEXT DEFAULT '',
    zip_size    INTEGER DEFAULT 0,
    checksum    TEXT DEFAULT '',
    min_version TEXT DEFAULT '1.0.0',
    published   INTEGER DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pack_id, version),
    FOREIGN KEY(pack_id) REFERENCES mkt_packs(id)
);
CREATE TABLE IF NOT EXISTS mkt_reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id     TEXT NOT NULL,
    reviewer    TEXT DEFAULT 'Anonymous',
    rating      INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    review_text TEXT DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mkt_installed (
    pack_id    TEXT PRIMARY KEY,
    version    TEXT NOT NULL,
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    auto_update  INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_mkt_cat  ON mkt_packs(category);
CREATE INDEX IF NOT EXISTS idx_mkt_feat ON mkt_packs(featured DESC);
CREATE INDEX IF NOT EXISTS idx_mkt_dl   ON mkt_packs(downloads DESC);
"""

# ── Built-in curated packs (seeded on first run) ──────────────────────────────
CURATED_PACKS = [
    {
        'id': 'agenticai-core',
        'name': 'Agentic Core Skills',
        'icon': '🤖',
        'author': 'Agentic OS',
        'category': 'core',
        'tags': 'ai,llm,core,essential',
        'description': 'Essential AI skills: summarize, explain, translate, classify, extract. The foundation pack.',
        'latest_ver': '2.1.0',
        'downloads': 12483,
        'featured': 1,
        'verified': 1,
        'rating_sum': 23.5,
        'rating_count': 5,
        'skills': [
            {
                'id': 'summarize',
                'name': 'Summarize',
                'prompt': 'Summarize this in 3 key points: {{input}}',
                'icon': '📝',
            },
            {
                'id': 'explain',
                'name': 'Explain Simply',
                'prompt': "Explain this like I'm 12 years old: {{input}}",
                'icon': '💡',
            },
            {'id': 'translate', 'name': 'Translate', 'prompt': 'Translate to English: {{input}}', 'icon': '🌐'},
            {
                'id': 'classify',
                'name': 'Classify Intent',
                'prompt': 'Classify the intent of: {{input}}\nOutput: one of [question, request, feedback, complaint, compliment]',
                'icon': '🏷️',
            },
            {
                'id': 'extract',
                'name': 'Extract Facts',
                'prompt': 'Extract all facts and key information as a bullet list from: {{input}}',
                'icon': '🔍',
            },
        ],
    },
    {
        'id': 'code-wizard',
        'name': 'Code Wizard Pack',
        'icon': '🧙',
        'author': 'DevTools Team',
        'category': 'developer',
        'tags': 'code,debug,review,refactor,test',
        'description': 'Complete coding toolkit: review, refactor, debug, generate tests, explain code, convert languages.',
        'latest_ver': '3.0.1',
        'downloads': 9241,
        'featured': 1,
        'verified': 1,
        'rating_sum': 19.0,
        'rating_count': 4,
        'skills': [
            {
                'id': 'code_review',
                'name': 'Code Review',
                'prompt': 'Review this code for bugs, security issues, and improvements:\n\n```\n{{input}}\n```\n\nProvide specific, actionable feedback.',
                'icon': '🔍',
            },
            {
                'id': 'refactor',
                'name': 'Refactor',
                'prompt': 'Refactor this code to be cleaner, more readable, and follow best practices:\n\n```\n{{input}}\n```',
                'icon': '✨',
            },
            {
                'id': 'debug',
                'name': 'Debug Assistant',
                'prompt': 'Debug this code and find the bug:\n\n```\n{{input}}\n```\n\nExplain the bug and provide the fix.',
                'icon': '🐛',
            },
            {
                'id': 'test_gen',
                'name': 'Generate Tests',
                'prompt': 'Write comprehensive unit tests for:\n\n```\n{{input}}\n```',
                'icon': '🧪',
            },
            {
                'id': 'explain_code',
                'name': 'Explain Code',
                'prompt': 'Explain this code line by line, in plain English:\n\n```\n{{input}}\n```',
                'icon': '📖',
            },
            {
                'id': 'convert',
                'name': 'Convert Language',
                'prompt': 'Convert this code to Python (or specify target language in input):\n\n```\n{{input}}\n```',
                'icon': '🔄',
            },
        ],
    },
    {
        'id': 'content-creator',
        'name': 'Content Creator Pack',
        'icon': '✍️',
        'author': 'Creative Studio',
        'category': 'content',
        'tags': 'writing,blog,social,email,copywriting',
        'description': 'Professional writing tools: blog posts, social media, email campaigns, product descriptions, SEO.',
        'latest_ver': '1.4.2',
        'downloads': 7830,
        'featured': 1,
        'verified': 1,
        'rating_sum': 21.5,
        'rating_count': 5,
        'skills': [
            {
                'id': 'blog_post',
                'name': 'Write Blog Post',
                'prompt': 'Write a professional blog post about: {{input}}\n\nInclude: catchy title, introduction, 3-5 sections with subheadings, conclusion, call-to-action.',
                'icon': '📝',
            },
            {
                'id': 'social_tweet',
                'name': 'Twitter/X Thread',
                'prompt': 'Create an engaging Twitter/X thread (5-7 tweets) about: {{input}}',
                'icon': '🐦',
            },
            {
                'id': 'linkedin_post',
                'name': 'LinkedIn Post',
                'prompt': 'Write a professional LinkedIn post about: {{input}}\nMake it insightful, include 3-5 hashtags.',
                'icon': '💼',
            },
            {
                'id': 'email_campaign',
                'name': 'Email Campaign',
                'prompt': 'Write a compelling marketing email for: {{input}}\nInclude: subject line, preheader, body, CTA.',
                'icon': '📧',
            },
            {
                'id': 'product_desc',
                'name': 'Product Description',
                'prompt': 'Write a persuasive product description for: {{input}}\nHighlight benefits, features, and unique selling points.',
                'icon': '🛍️',
            },
            {
                'id': 'seo_meta',
                'name': 'SEO Meta Tags',
                'prompt': 'Generate SEO-optimised title, description, and keywords for a page about: {{input}}',
                'icon': '🔎',
            },
        ],
    },
    {
        'id': 'data-analyst',
        'name': 'Data Analyst Pack',
        'icon': '📊',
        'author': 'Analytics Pro',
        'category': 'analytics',
        'tags': 'data,analysis,sql,visualization,insights',
        'description': 'Data analysis and insights: SQL generation, data summaries, chart suggestions, anomaly detection.',
        'latest_ver': '2.0.0',
        'downloads': 5620,
        'featured': 0,
        'verified': 1,
        'rating_sum': 17.5,
        'rating_count': 4,
        'skills': [
            {
                'id': 'sql_gen',
                'name': 'Generate SQL',
                'prompt': 'Generate a SQL query for: {{input}}\nOutput only the SQL with comments.',
                'icon': '🗄️',
            },
            {
                'id': 'analyze_data',
                'name': 'Analyze Data',
                'prompt': 'Analyze this data and provide insights, trends, and recommendations:\n\n{{input}}',
                'icon': '📈',
            },
            {
                'id': 'chart_suggest',
                'name': 'Chart Suggestions',
                'prompt': 'Suggest the best chart types and visualizations for this data:\n\n{{input}}',
                'icon': '📊',
            },
            {
                'id': 'anomaly_detect',
                'name': 'Detect Anomalies',
                'prompt': 'Identify anomalies, outliers, and unusual patterns in:\n\n{{input}}',
                'icon': '⚠️',
            },
        ],
    },
    {
        'id': 'research-assistant',
        'name': 'Research Assistant Pack',
        'icon': '🔬',
        'author': 'Academic AI',
        'category': 'research',
        'tags': 'research,academic,citations,summarize,literature',
        'description': 'Research tools: paper summaries, citation extraction, literature review, hypothesis generation.',
        'latest_ver': '1.2.0',
        'downloads': 4310,
        'featured': 0,
        'verified': 1,
        'rating_sum': 14.5,
        'rating_count': 3,
        'skills': [
            {
                'id': 'paper_summary',
                'name': 'Summarize Paper',
                'prompt': 'Summarize this research paper:\n{{input}}\n\nInclude: objective, methodology, key findings, limitations, implications.',
                'icon': '📄',
            },
            {
                'id': 'cite_extract',
                'name': 'Extract Citations',
                'prompt': 'Extract all citations and references from:\n{{input}}\nFormat as a numbered list.',
                'icon': '📚',
            },
            {
                'id': 'lit_review',
                'name': 'Literature Review',
                'prompt': 'Write a literature review section covering the key themes in:\n{{input}}',
                'icon': '📖',
            },
            {
                'id': 'hypothesis',
                'name': 'Generate Hypotheses',
                'prompt': 'Generate 5 testable research hypotheses related to:\n{{input}}',
                'icon': '💭',
            },
        ],
    },
    {
        'id': 'devops-toolkit',
        'name': 'DevOps Toolkit',
        'icon': '🚀',
        'author': 'Infrastructure Team',
        'category': 'devops',
        'tags': 'devops,docker,kubernetes,ci,monitoring',
        'description': 'DevOps automation: Dockerfile generation, K8s configs, CI/CD pipelines, monitoring setup.',
        'latest_ver': '1.1.3',
        'downloads': 3890,
        'featured': 0,
        'verified': 1,
        'rating_sum': 19.0,
        'rating_count': 4,
        'skills': [
            {
                'id': 'dockerfile',
                'name': 'Generate Dockerfile',
                'prompt': 'Create an optimized Dockerfile for:\n{{input}}',
                'icon': '🐳',
            },
            {
                'id': 'k8s_manifest',
                'name': 'K8s Manifest',
                'prompt': 'Generate a Kubernetes deployment manifest for:\n{{input}}\nInclude deployment, service, and configmap.',
                'icon': '☸️',
            },
            {
                'id': 'ci_pipeline',
                'name': 'CI/CD Pipeline',
                'prompt': 'Create a GitHub Actions CI/CD workflow for:\n{{input}}',
                'icon': '⚙️',
            },
            {
                'id': 'monitoring',
                'name': 'Monitoring Setup',
                'prompt': 'Recommend monitoring metrics, alerts, and dashboards for:\n{{input}}',
                'icon': '📡',
            },
        ],
    },
    {
        'id': 'prompt-engineering',
        'name': 'Prompt Engineering Pack',
        'icon': '🎯',
        'author': 'AI Craft',
        'category': 'ai',
        'tags': 'prompts,engineering,optimization,templates',
        'description': 'Meta-prompting tools: improve prompts, generate system prompts, create prompt chains.',
        'latest_ver': '2.3.0',
        'downloads': 6750,
        'featured': 1,
        'verified': 1,
        'rating_sum': 22.0,
        'rating_count': 5,
        'skills': [
            {
                'id': 'improve_prompt',
                'name': 'Improve Prompt',
                'prompt': 'Improve this AI prompt to be more specific, effective, and produce better results:\n\n{{input}}\n\nReturn the improved prompt only.',
                'icon': '✨',
            },
            {
                'id': 'system_prompt',
                'name': 'Generate System Prompt',
                'prompt': 'Create a detailed system prompt for an AI assistant that: {{input}}',
                'icon': '🤖',
            },
            {
                'id': 'chain',
                'name': 'Create Prompt Chain',
                'prompt': 'Design a multi-step prompt chain workflow to accomplish: {{input}}',
                'icon': '🔗',
            },
            {
                'id': 'few_shot',
                'name': 'Few-Shot Examples',
                'prompt': 'Create 5 diverse few-shot examples to teach an AI how to handle: {{input}}',
                'icon': '🎓',
            },
        ],
    },
    {
        'id': 'customer-success',
        'name': 'Customer Success Pack',
        'icon': '🎯',
        'author': 'CX Team',
        'category': 'business',
        'tags': 'customer,support,crm,tickets,feedback',
        'description': 'Customer success tools: ticket responses, sentiment analysis, FAQ generation, escalation handling.',
        'latest_ver': '1.0.5',
        'downloads': 2980,
        'featured': 0,
        'verified': 0,
        'rating_sum': 12.0,
        'rating_count': 3,
        'skills': [
            {
                'id': 'ticket_response',
                'name': 'Support Response',
                'prompt': 'Write a professional, empathetic customer support response to:\n\n{{input}}\n\nBe helpful, clear, and offer next steps.',
                'icon': '🎫',
            },
            {
                'id': 'sentiment',
                'name': 'Analyze Sentiment',
                'prompt': 'Analyze the sentiment and emotion of this customer feedback:\n{{input}}\nRate: positive/negative/neutral and identify key emotions.',
                'icon': '😊',
            },
            {
                'id': 'faq_gen',
                'name': 'Generate FAQ',
                'prompt': 'Generate 10 likely FAQ questions and answers for:\n{{input}}',
                'icon': '❓',
            },
        ],
    },
]


def _ensure_schema_and_seed():
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.executescript(_SCHEMA)
        with contextlib.suppress(Exception):
            con.execute("ALTER TABLE mkt_packs ADD COLUMN skills_json TEXT DEFAULT '[]'")
        con.commit()
        # Seed curated packs
        for pack in CURATED_PACKS:
            row = con.execute('SELECT id FROM mkt_packs WHERE id=?', (pack['id'],)).fetchone()
            if not row:
                con.execute(
                    """
                    INSERT INTO mkt_packs(id,name,description,icon,author,category,tags,
                                          latest_ver,downloads,featured,verified,
                                          rating_sum,rating_count,published)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                """,
                    (
                        pack['id'],
                        pack['name'],
                        pack['description'],
                        pack['icon'],
                        pack['author'],
                        pack['category'],
                        pack['tags'],
                        pack['latest_ver'],
                        pack['downloads'],
                        pack.get('featured', 0),
                        pack.get('verified', 0),
                        pack.get('rating_sum', 0),
                        pack.get('rating_count', 0),
                    ),
                )
                # Save skills manifest
                pack_dir = PACKS_DIR / pack['id']
                pack_dir.mkdir(exist_ok=True)
                manifest = {
                    k: v
                    for k, v in pack.items()
                    if k not in ('rating_sum', 'rating_count', 'downloads', 'featured', 'verified')
                }
                (pack_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        con.commit()
    finally:
        con.close()


_ensure_schema_and_seed()


# ── Helpers ────────────────────────────────────────────────────────────────────
def _pack_row_to_dict(row) -> dict:
    d = dict(row)
    d['rating'] = round(d['rating_sum'] / max(d['rating_count'], 1), 1) if d.get('rating_count') else 0
    d['tags_list'] = [t.strip() for t in (d.get('tags', '')).split(',') if t.strip()]
    manifest_path = PACKS_DIR / d['id'] / 'manifest.json'
    if manifest_path.exists():
        try:
            m = json.loads(manifest_path.read_text())
            d['skills'] = m.get('skills', [])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            d['skills'] = []
    else:
        try:
            d['skills'] = json.loads(d.get('skills_json') or '[]')
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            d['skills'] = []
    return d


# ── List / Search ──────────────────────────────────────────────────────────────
@router.get('')
def list_packs(
    q: str = '',
    category: str = '',
    sort: str = 'featured',  # featured | downloads | rating | newest
    featured: bool = False,
    verified: bool = False,
    limit: int = 50,
    offset: int = 0,
):
    """Retrieve and return list packs."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        where = ['published=1']
        params: list = []
        if q:
            where.append('(name LIKE ? OR description LIKE ? OR tags LIKE ? OR author LIKE ?)')
            params.extend([f'%{q}%'] * 4)
        if category:
            where.append('category=?')
            params.append(category)
        if featured:
            where.append('featured=1')
        if verified:
            where.append('verified=1')

        order = {
            'featured': 'featured DESC, downloads DESC',
            'downloads': 'downloads DESC',
            'rating': '(rating_sum/MAX(rating_count,1)) DESC',
            'newest': 'created_at DESC',
        }.get(sort, 'featured DESC, downloads DESC')

        sql = f"""SELECT * FROM mkt_packs WHERE {' AND '.join(where)}
                  ORDER BY {order} LIMIT ? OFFSET ?"""
        params += [min(limit, 100), offset]
        rows = con.execute(sql, params).fetchall()
        total = con.execute(f'SELECT COUNT(*) FROM mkt_packs WHERE {" AND ".join(where)}', params[:-2]).fetchone()[0]
    finally:
        con.close()

    return {
        'packs': [_pack_row_to_dict(r) for r in rows],
        'total': total,
        'limit': limit,
        'offset': offset,
    }


@router.get('/featured')
def featured_packs(limit: int = 6):
    """Execute or process featured packs operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT * FROM mkt_packs WHERE featured=1 AND published=1 ORDER BY downloads DESC LIMIT ?', (limit,)
        ).fetchall()
    finally:
        con.close()
    return {'packs': [_pack_row_to_dict(r) for r in rows]}


@router.get('/categories')
def list_categories():
    """Retrieve and return list categories."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT category, COUNT(*) as count FROM mkt_packs WHERE published=1 GROUP BY category ORDER BY count DESC'
        ).fetchall()
    finally:
        con.close()
    return {'categories': [dict(r) for r in rows]}


@router.get('/trending')
def trending_packs(limit: int = 10):
    """Execute or process trending packs operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT * FROM mkt_packs WHERE published=1 ORDER BY downloads DESC, rating_sum DESC LIMIT ?', (limit,)
        ).fetchall()
    finally:
        con.close()
    return {'packs': [_pack_row_to_dict(r) for r in rows]}


@router.get('/new-arrivals')
def new_arrivals(limit: int = 10):
    """Create and initialize a new new arrivals."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT * FROM mkt_packs WHERE published=1 ORDER BY created_at DESC LIMIT ?', (limit,)
        ).fetchall()
    finally:
        con.close()
    return {'packs': [_pack_row_to_dict(r) for r in rows]}


# ── Single pack ────────────────────────────────────────────────────────────────
@router.get('/{pack_id}')
def get_pack(pack_id: str):
    """Retrieve and return get pack."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute('SELECT * FROM mkt_packs WHERE id=?', (pack_id,)).fetchone()
        releases = con.execute(
            'SELECT * FROM mkt_releases WHERE pack_id=? ORDER BY created_at DESC', (pack_id,)
        ).fetchall()
        reviews = con.execute(
            'SELECT * FROM mkt_reviews WHERE pack_id=? ORDER BY created_at DESC LIMIT 20', (pack_id,)
        ).fetchall()
    finally:
        con.close()
    if not row:
        return {'ok': False, 'error': 'Pack not found'}
    d = _pack_row_to_dict(row)
    d['releases'] = [dict(r) for r in releases]
    d['reviews'] = [dict(r) for r in reviews]
    return d


# ── Install / Uninstall ────────────────────────────────────────────────────────
@router.post('/{pack_id}/install')
async def install_pack(pack_id: str, req: Request):
    """Execute or process install pack operation."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        body = {}
    version = body.get('version', '') if isinstance(body, dict) else ''

    import time as _t

    from ..services.memory_db import get_conn

    last_err = None
    for _attempt in range(3):  # retry up to 3x on lock
        try:
            con = get_conn()
            try:
                pack = con.execute('SELECT * FROM mkt_packs WHERE id=?', (pack_id,)).fetchone()
                if not pack:
                    con.close()
                    return {'ok': False, 'error': 'Pack not found'}
                version = version or pack['latest_ver']
                con.execute('DELETE FROM mkt_installed WHERE pack_id=?', (pack_id,))
                con.execute('INSERT INTO mkt_installed(pack_id,version,auto_update) VALUES (?,?,1)', (pack_id, version))
                con.execute('UPDATE mkt_packs SET downloads=downloads+1 WHERE id=?', (pack_id,))
                con.commit()
            finally:
                con.close()
            break  # success
        except Exception as ex:
            last_err = ex
            _t.sleep(0.05 * (_attempt + 1))
    else:
        return {'ok': False, 'error': f'Install failed after retries: {last_err}'}

    # Load manifest and register skills
    manifest_path = PACKS_DIR / pack_id / 'manifest.json'
    skills = []
    if manifest_path.exists():
        with contextlib.suppress(Exception):
            m = json.loads(manifest_path.read_text())
            skills = m.get('skills', [])
    else:
        # Find from curated
        cp = next((p for p in CURATED_PACKS if p['id'] == pack_id), None)
        if cp:
            skills = cp.get('skills', [])

    # Also install into SDK packs for use in Plugin SDK pane
    sdk_dir = ROOT / 'workspaces' / 'plugin_sdk' / 'packs'
    sdk_dir.mkdir(parents=True, exist_ok=True)
    sdk_pack = {
        'id': pack_id,
        'name': dict(pack)['name'] if pack else pack_id,
        'version': version,
        'description': dict(pack)['description'] if pack else '',
        'icon': dict(pack)['icon'] if pack else '🔧',
        'author': dict(pack)['author'] if pack else '',
        'source': 'marketplace',
        'installed': True,
        'skills': skills,
    }
    (sdk_dir / f'{pack_id}.json').write_text(json.dumps(sdk_pack, indent=2))

    return {
        'ok': True,
        'pack_id': pack_id,
        'version': version,
        'skills': len(skills),
        'message': f'✅ Installed {dict(pack)["name"] if pack else pack_id} v{version} with {len(skills)} skills',
    }


@router.delete('/{pack_id}/uninstall')
def uninstall_pack(pack_id: str):
    """Execute or process uninstall pack operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute('DELETE FROM mkt_installed WHERE pack_id=?', (pack_id,))
        con.commit()
    finally:
        con.close()
    # Remove from SDK packs
    sdk_pack = ROOT / 'workspaces' / 'plugin_sdk' / 'packs' / f'{pack_id}.json'
    if sdk_pack.exists():
        with contextlib.suppress(Exception):
            sdk_pack.unlink()
    return {'ok': True, 'pack_id': pack_id}


@router.get('/installed/list')
def list_installed():
    """Retrieve and return list installed."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute("""
            SELECT i.*, p.name, p.icon, p.author, p.latest_ver, p.description
            FROM mkt_installed i
            LEFT JOIN mkt_packs p ON p.id = i.pack_id
            ORDER BY i.installed_at DESC
        """).fetchall()
    finally:
        con.close()
    return {'installed': [dict(r) for r in rows], 'count': len(rows)}


# ── Update checks ──────────────────────────────────────────────────────────────
@router.get('/installed/check-updates')
def check_updates():
    """Verify and validate check updates functionality or health."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute("""
            SELECT i.pack_id, i.version as installed_ver, p.latest_ver, p.name, p.icon
            FROM mkt_installed i
            JOIN mkt_packs p ON p.id=i.pack_id
        """).fetchall()
    finally:
        con.close()
    updates = []
    for row in rows:
        d = dict(row)
        if d['installed_ver'] != d['latest_ver']:
            updates.append(d)
    return {'updates': updates, 'count': len(updates)}


@router.post('/installed/update-all')
async def update_all():
    """Update existing all record or state."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute("""
            SELECT i.pack_id, p.latest_ver FROM mkt_installed i
            JOIN mkt_packs p ON p.id=i.pack_id
            WHERE i.version != p.latest_ver AND i.auto_update=1
        """).fetchall()
    finally:
        con.close()

    updated = []
    for row in rows:
        from ..services.memory_db import get_conn as _gc

        con2 = _gc()
        con2.execute(
            'UPDATE mkt_installed SET version=?,installed_at=CURRENT_TIMESTAMP WHERE pack_id=?',
            (row['latest_ver'], row['pack_id']),
        )
        con2.commit()
        con2.close()
        updated.append({'pack_id': row['pack_id'], 'version': row['latest_ver']})

    return {'ok': True, 'updated': updated, 'count': len(updated)}


# ── Ratings & Reviews ──────────────────────────────────────────────────────────
@router.post('/{pack_id}/review')
async def submit_review(pack_id: str, req: Request):
    """Execute or process submit review operation."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return {'ok': False, 'error': 'Invalid JSON'}
    try:
        rating = int(float(body.get('rating', 5) or 5))
    except (ValueError, TypeError):
        rating = 5
    text = (body.get('review', '') or '')[:2000]
    name = (body.get('reviewer', 'Anonymous') or 'Anonymous')[:64]

    if not 1 <= rating <= 5:
        return {'ok': False, 'error': 'Rating must be 1-5'}

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'INSERT INTO mkt_reviews(pack_id,reviewer,rating,review_text) VALUES (?,?,?,?)',
            (pack_id, name, rating, text),
        )
        con.execute(
            'UPDATE mkt_packs SET rating_sum=rating_sum+?,rating_count=rating_count+1 WHERE id=?', (rating, pack_id)
        )
        con.commit()
        pack = con.execute('SELECT rating_sum,rating_count FROM mkt_packs WHERE id=?', (pack_id,)).fetchone()
        avg = round(pack['rating_sum'] / max(pack['rating_count'], 1), 1) if pack else 0
    finally:
        con.close()

    return {'ok': True, 'new_avg': avg, 'rating': rating}


@router.get('/{pack_id}/reviews')
def get_reviews(pack_id: str, limit: int = 20):
    """Retrieve and return get reviews."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT * FROM mkt_reviews WHERE pack_id=? ORDER BY created_at DESC LIMIT ?', (pack_id, min(limit, 100))
        ).fetchall()
    finally:
        con.close()
    return {'reviews': [dict(r) for r in rows], 'count': len(rows)}


@router.post('/community/submit')
async def submit_community_pack(req: Request):
    """Submit a community plugin/skill pack with author attribution and initial ratings."""
    _ensure_schema_and_seed()
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    pack_id = (body.get('id') or body.get('pack_id') or '').strip().lower().replace(' ', '-')
    name = (body.get('name') or pack_id).strip()
    description = (body.get('description') or 'Community skill pack').strip()
    author = (body.get('author') or 'Community Builder').strip()
    skills = body.get('skills') or []
    if not pack_id:
        return {'ok': False, 'error': 'id required'}

    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        existing = con.execute('SELECT id FROM mkt_packs WHERE id=?', (pack_id,)).fetchone()
        if existing:
            con.execute(
                'UPDATE mkt_packs SET name=?,description=?,author=?,skills_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                (name, description, author, json.dumps(skills), pack_id),
            )
        else:
            con.execute(
                'INSERT INTO mkt_packs(id,name,icon,author,category,tags,description,latest_ver,downloads,featured,verified,rating_sum,rating_count,skills_json,published) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)',
                (pack_id, name, body.get('icon', '⚡'), author, body.get('category', 'community'), body.get('tags', 'community,skills'), description, body.get('version', '1.0.0'), 1, 0, 0, 5.0, 1, json.dumps(skills)),
            )
        con.commit()
        return {'ok': True, 'pack_id': pack_id, 'name': name, 'message': 'Community pack submitted successfully'}
    finally:
        con.close()


@router.get('/community/list')
def list_community_packs():
    """Retrieve all community-submitted and unverified packs."""
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        rows = con.execute('SELECT * FROM mkt_packs WHERE verified=0 AND published=1 ORDER BY created_at DESC LIMIT 100').fetchall()
        from .marketplace import _pack_row_to_dict
        return {'ok': True, 'count': len(rows), 'packs': [_pack_row_to_dict(r) for r in rows]}
    finally:
        con.close()


# ── Publish user packs ─────────────────────────────────────────────────────────
@router.post('/publish')
async def publish_pack(req: Request):
    """Publish a user-created pack from Plugin SDK to marketplace."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    pack_id = body.get('pack_id', '')

    # Load from SDK
    sdk_path = ROOT / 'workspaces' / 'plugin_sdk' / 'packs' / f'{pack_id}.json'
    if not sdk_path.exists():
        return {'ok': False, 'error': 'Pack not found in SDK. Create it in Plugin SDK first.'}

    pack = json.loads(sdk_path.read_text())

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        existing = con.execute('SELECT id FROM mkt_packs WHERE id=?', (pack['id'],)).fetchone()
        if existing:
            con.execute(
                """
                UPDATE mkt_packs SET name=?,description=?,icon=?,tags=?,
                  latest_ver=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """,
                (
                    pack.get('name', ''),
                    pack.get('description', ''),
                    pack.get('icon', '🔧'),
                    ','.join(pack.get('tags', [])),
                    pack.get('version', '1.0.0'),
                    pack['id'],
                ),
            )
        else:
            con.execute(
                """
                INSERT INTO mkt_packs(id,name,description,icon,author,category,tags,latest_ver)
                VALUES (?,?,?,?,?,?,?,?)
            """,
                (
                    pack['id'],
                    pack.get('name', ''),
                    pack.get('description', ''),
                    pack.get('icon', '🔧'),
                    pack.get('author', ''),
                    'user',
                    ','.join(pack.get('tags', [])),
                    pack.get('version', '1.0.0'),
                ),
            )

        # Save manifest
        pack_dir = PACKS_DIR / pack['id']
        pack_dir.mkdir(exist_ok=True)
        (pack_dir / 'manifest.json').write_text(json.dumps(pack, indent=2))

        con.commit()
    finally:
        con.close()

    return {'ok': True, 'pack_id': pack['id'], 'message': f'Published {pack.get("name", "")} to marketplace'}


@router.post('/upload')
async def upload_pack(file: UploadFile = File(...)):
    """Upload a ZIP pack file to the marketplace."""
    data = await file.read()
    buf = io.BytesIO(data)

    try:
        with zipfile.ZipFile(buf) as zf:
            if 'manifest.json' not in zf.namelist():
                return {'ok': False, 'error': 'ZIP must contain manifest.json'}
            manifest = json.loads(zf.read('manifest.json'))
            pack_id = manifest.get('id', '')
            if not pack_id:
                return {'ok': False, 'error': 'manifest.json must have id field'}

            # Extract to pack dir
            pack_dir = PACKS_DIR / pack_id
            pack_dir.mkdir(exist_ok=True)
            zf.extractall(str(pack_dir))
    except Exception as ex:
        return {'ok': False, 'error': f'Invalid ZIP: {ex}'}

    # Register in DB
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        checksum = hashlib.sha256(data).hexdigest()
        zip_path = str(PACKS_DIR / pack_id / f'v{manifest.get("version", "1.0.0")}.zip')
        buf.seek(0)
        Path(zip_path).write_bytes(buf.read())

        con.execute(
            """
            INSERT INTO mkt_packs(id,name,description,icon,author,category,tags,latest_ver)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name, description=excluded.description,
              latest_ver=excluded.latest_ver, updated_at=CURRENT_TIMESTAMP
        """,
            (
                pack_id,
                manifest.get('name', ''),
                manifest.get('description', ''),
                manifest.get('icon', '🔧'),
                manifest.get('author', ''),
                manifest.get('category', 'utility'),
                ','.join(manifest.get('tags', [])),
                manifest.get('version', '1.0.0'),
            ),
        )
        con.execute(
            """
            INSERT OR REPLACE INTO mkt_releases(pack_id,version,zip_path,zip_size,checksum)
            VALUES (?,?,?,?,?)
        """,
            (pack_id, manifest.get('version', '1.0.0'), zip_path, len(data), checksum),
        )
        con.commit()
    finally:
        con.close()

    return {'ok': True, 'pack_id': pack_id, 'version': manifest.get('version')}


# ── Download pack ZIP ──────────────────────────────────────────────────────────
@router.get('/{pack_id}/download')
def download_pack(pack_id: str, version: str = ''):
    """Execute or process download pack operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        pack = con.execute('SELECT * FROM mkt_packs WHERE id=?', (pack_id,)).fetchone()
    finally:
        con.close()
    if not pack:
        return {'ok': False, 'error': 'Not found'}

    # Build zip on the fly from manifest
    manifest_path = PACKS_DIR / pack_id / 'manifest.json'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        if manifest_path.exists():
            zf.writestr('manifest.json', manifest_path.read_text())
        else:
            # Build from DB
            zf.writestr('manifest.json', json.dumps(_pack_row_to_dict(pack), indent=2))
        zf.writestr(
            'README.md',
            f'# {pack["name"]}\n\n{pack["description"]}\n\nVersion: {pack["latest_ver"]}\nAuthor: {pack["author"]}\n',
        )
    buf.seek(0)

    # Bump download count
    from ..services.memory_db import get_conn as _gc

    con2 = _gc()
    con2.execute('UPDATE mkt_packs SET downloads=downloads+1 WHERE id=?', (pack_id,))
    con2.commit()
    con2.close()

    return StreamingResponse(
        buf,
        media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename={pack_id}-{pack["latest_ver"]}.zip'},
    )


# ── Stats ──────────────────────────────────────────────────────────────────────
@router.get('/stats/overview')
def marketplace_stats():
    """Execute or process marketplace stats operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        total = con.execute('SELECT COUNT(*) FROM mkt_packs WHERE published=1').fetchone()[0]
        cats = con.execute('SELECT COUNT(DISTINCT category) FROM mkt_packs').fetchone()[0]
        dl_total = con.execute('SELECT SUM(downloads) FROM mkt_packs').fetchone()[0] or 0
        inst = con.execute('SELECT COUNT(*) FROM mkt_installed').fetchone()[0]
        reviews = con.execute('SELECT COUNT(*) FROM mkt_reviews').fetchone()[0]
        top = con.execute(
            'SELECT name,downloads FROM mkt_packs WHERE published=1 ORDER BY downloads DESC LIMIT 5'
        ).fetchall()
    finally:
        con.close()
    return {
        'total_packs': total,
        'categories': cats,
        'total_downloads': dl_total,
        'installed': inst,
        'reviews': reviews,
        'top_packs': [dict(r) for r in top],
    }
