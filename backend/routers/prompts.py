"""
Agentic OS — Prompt Library Router
Save, organize, tag, search, and reuse AI prompts across sessions.
Like Claude's prompt library but integrated into the full OS.
"""

from __future__ import annotations

import contextlib

import time
import uuid

from fastapi import APIRouter, Request

from ..services.memory_db import audit_log, get_conn

router = APIRouter(prefix='/api/prompts', tags=['prompts'])

VALID_CATEGORIES = {
    'general',
    'build',
    'review',
    'testing',
    'refactor',
    'debug',
    'docs',
    'auth',
    'seo',
    'database',
    'ux',
    'quality',
}
VALID_SORTS = {'updated': 'updated_at DESC', 'used': 'use_count DESC', 'title': 'title ASC'}


def _ensure_table():
    con = get_conn()
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS prompt_library (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                content     TEXT NOT NULL,
                category    TEXT DEFAULT 'general',
                tags        TEXT DEFAULT '',
                agent_id    TEXT DEFAULT '',
                use_count   INTEGER DEFAULT 0,
                is_favorite INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()
        # Seed useful default prompts only if table is empty
        count = con.execute('SELECT COUNT(*) FROM prompt_library').fetchone()[0]
        if count == 0:
            defaults = [
                (
                    'Build a SaaS landing page',
                    'Build a complete SaaS landing page with: hero section, feature grid, pricing tiers (free/pro/enterprise), testimonials, FAQ, and CTA. Use Tailwind CSS, dark theme, modern design.',
                    'build',
                    'saas,landing,tailwind',
                ),
                (
                    'Code review for security',
                    'Review this code for: SQL injection, XSS vulnerabilities, authentication bypasses, insecure direct object references, exposed secrets, missing input validation, and CSRF protection.',
                    'review',
                    'security,code-review,audit',
                ),
                (
                    'Write comprehensive tests',
                    'Write a complete test suite for this code covering: happy path, edge cases, error conditions, boundary values, and integration points. Use descriptive test names.',
                    'testing',
                    'tests,jest,pytest',
                ),
                (
                    'Refactor for performance',
                    'Refactor this code for performance: identify bottlenecks, optimize database queries, add caching, reduce bundle size, improve algorithm complexity, and add lazy loading where appropriate.',
                    'refactor',
                    'performance,optimization',
                ),
                (
                    'Generate API documentation',
                    'Generate comprehensive API documentation for these endpoints: include description, parameters (required/optional), request/response schemas, example curl commands, and error codes.',
                    'docs',
                    'api,documentation',
                ),
                (
                    'Debug this error',
                    'Debug this error systematically: identify root cause, explain why it occurs, provide the fix, and suggest how to prevent similar issues in the future.',
                    'debug',
                    'debugging,error',
                ),
                (
                    'Create database schema',
                    'Design a normalized database schema for this use case. Include: table definitions, primary keys, foreign keys, indexes, constraints, and sample seed data.',
                    'database',
                    'sql,schema,database',
                ),
                (
                    'Add authentication',
                    'Add complete authentication to this app: user registration, login, password reset, session management, JWT tokens, protected routes, and role-based access control.',
                    'auth',
                    'authentication,jwt,security',
                ),
                (
                    'Make it mobile responsive',
                    'Make this layout fully responsive for mobile (320px+), tablet (768px+), and desktop (1280px+). Use mobile-first CSS, touch-friendly interactions, and proper viewport handling.',
                    'ux',
                    'responsive,mobile,css',
                ),
                (
                    'Optimize for SEO',
                    'Optimize this page for SEO: meta tags, Open Graph, structured data, canonical URLs, sitemap, robots.txt, image alt text, semantic HTML, and core web vitals.',
                    'seo',
                    'seo,meta,performance',
                ),
                (
                    'Add error handling',
                    'Add comprehensive error handling: try/catch blocks, meaningful error messages, error boundaries, logging, graceful degradation, and user-friendly error states.',
                    'quality',
                    'errors,reliability',
                ),
                (
                    'Convert to TypeScript',
                    'Convert this JavaScript to TypeScript: add proper types, interfaces, generics, strict mode compatibility, and fix any type errors while preserving all functionality.',
                    'refactor',
                    'typescript,types',
                ),
                (
                    'Explain this code',
                    'Explain this code clearly and simply: what it does, how it works step by step, any design patterns used, potential issues, and how it could be improved.',
                    'general',
                    'explain,learning',
                ),
                (
                    'Generate README',
                    'Write a comprehensive README.md for this project: include description, features, installation, usage, API reference, contributing guide, and license.',
                    'docs',
                    'readme,documentation',
                ),
            ]
            # Keep a useful starter library available on a fresh install. These
            # compact prompts cover the common build, product, and operations
            # workflows without requiring an external marketplace connection.
            defaults.extend([
                ('Plan a product launch', 'Create a product launch plan with milestones, owners, risks, channels, and success metrics.', 'general', 'product,launch,planning'),
                ('Write user stories', 'Convert this product idea into prioritized user stories with acceptance criteria and edge cases.', 'general', 'product,user-stories,requirements'),
                ('Design an API contract', 'Design a versioned REST API contract with endpoints, schemas, authentication, pagination, and errors.', 'docs', 'api,rest,contract'),
                ('Review database indexes', 'Review these queries and recommend indexes, query changes, and migration-safe rollout steps.', 'database', 'sql,indexes,performance'),
                ('Create a migration plan', 'Create a safe migration plan including backups, compatibility, rollout, validation, and rollback.', 'database', 'migration,rollback,operations'),
                ('Threat-model a feature', 'Threat-model this feature using assets, actors, trust boundaries, abuse cases, mitigations, and residual risk.', 'auth', 'threat-model,security'),
                ('Review dependencies', 'Review project dependencies for vulnerabilities, licensing concerns, freshness, and upgrade strategy.', 'quality', 'dependencies,supply-chain'),
                ('Improve accessibility', 'Audit this interface for WCAG issues and provide prioritized fixes with keyboard and screen-reader behavior.', 'ux', 'accessibility,wcag,ui'),
                ('Create a UX research plan', 'Create a UX research plan with hypotheses, participant criteria, tasks, questions, and analysis method.', 'ux', 'research,ux,interviews'),
                ('Analyze user feedback', 'Cluster this user feedback into themes, identify severity and frequency, and recommend product actions.', 'general', 'feedback,analysis,product'),
                ('Write release notes', 'Write concise release notes grouped by new features, improvements, fixes, breaking changes, and known issues.', 'docs', 'release,notes,changelog'),
                ('Prepare an incident report', 'Write a blameless incident report with timeline, impact, root cause, contributing factors, and corrective actions.', 'quality', 'incident,postmortem,reliability'),
                ('Create an observability plan', 'Define logs, metrics, traces, dashboards, alerts, SLOs, and runbooks for this service.', 'quality', 'observability,slo,monitoring'),
                ('Optimize cloud costs', 'Analyze this architecture for cost drivers and recommend savings while preserving reliability and performance.', 'general', 'cloud,cost,finops'),
                ('Plan a CI pipeline', 'Design a CI pipeline covering formatting, linting, tests, security scans, artifacts, and deployment gates.', 'build', 'ci,automation,devops'),
                ('Write a Dockerfile', 'Create a secure production Dockerfile with minimal layers, non-root execution, health checks, and caching.', 'build', 'docker,containers,devops'),
                ('Review a pull request', 'Review this pull request for correctness, regressions, security, performance, tests, and maintainability.', 'review', 'pull-request,code-review'),
                ('Explain an architecture', 'Explain this architecture by component, data flow, dependencies, failure modes, and operational responsibilities.', 'docs', 'architecture,documentation'),
                ('Generate test cases', 'Generate a test matrix for this feature including positive, negative, boundary, concurrency, and recovery cases.', 'testing', 'qa,test-cases'),
                ('Debug a production issue', 'Triage this production issue from symptoms and logs, propose hypotheses, experiments, mitigation, and permanent fixes.', 'debug', 'production,debugging,incident'),
                ('Create a performance test', 'Design a performance test with workload model, data volume, concurrency, metrics, thresholds, and analysis.', 'testing', 'performance,load-testing'),
                ('Plan a refactor', 'Create an incremental refactor plan with seams, compatibility steps, tests, risk controls, and measurable outcomes.', 'refactor', 'refactoring,plan,legacy'),
                ('Draft a privacy review', 'Review this feature for personal data collection, retention, access, deletion, consent, and disclosure risks.', 'auth', 'privacy,data-protection'),
                ('Design an event schema', 'Design an event schema with versioning, idempotency, ordering, retention, replay, and compatibility rules.', 'build', 'events,messaging,schema'),
                ('Create a rollout plan', 'Create a progressive rollout plan with feature flags, cohorts, monitoring, rollback triggers, and communication.', 'quality', 'rollout,feature-flags'),
                ('Compare implementation options', 'Compare these implementation options using a decision matrix for cost, risk, complexity, performance, and maintainability.', 'general', 'decision,tradeoffs'),
                ('Turn notes into a spec', 'Turn these notes into a clear technical specification with goals, non-goals, requirements, interfaces, and open questions.', 'docs', 'spec,requirements'),
                ('Prepare a demo script', 'Create a concise product demo script with setup, narrative, key interactions, expected outcomes, and fallback steps.', 'general', 'demo,presentation'),
            ])
            for title, content, category, tags in defaults:
                pid = str(uuid.uuid4())[:8]
                con.execute(
                    'INSERT OR IGNORE INTO prompt_library(id,title,content,category,tags) VALUES(?,?,?,?,?)',
                    (pid, title, content, category, tags),
                )
            con.commit()
    finally:
        con.close()


_ensure_table()


# ── List ───────────────────────────────────────────────────────────────────────


@router.get('')
def list_prompts(
    category: str = '',
    q: str = '',
    favorites: bool = False,
    limit: int = 100,
    sort: str = 'updated',
    agent_id: str = '',
):
    """List prompts with optional filtering and sorting."""
    limit = min(max(1, int(limit)), 500)
    con = get_conn()
    try:
        where, params = [], []
        if category and category in VALID_CATEGORIES:
            where.append('category=?')
            params.append(category)
        if favorites:
            where.append('is_favorite=1')
        if agent_id:
            where.append('agent_id=?')
            params.append(agent_id)
        if q:
            where.append('(title LIKE ? OR content LIKE ? OR tags LIKE ?)')
            params.extend([f'%{q}%', f'%{q}%', f'%{q}%'])

        sql = 'SELECT * FROM prompt_library'
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += f' ORDER BY {VALID_SORTS.get(sort, "updated_at DESC")} LIMIT ?'
        params.append(limit)

        rows = con.execute(sql, params).fetchall()
        total = con.execute('SELECT COUNT(*) FROM prompt_library').fetchone()[0]
    finally:
        con.close()

    return {
        'prompts': [dict(r) for r in rows],
        'count': len(rows),
        'total': total,
    }


# ── Single prompt ──────────────────────────────────────────────────────────────


@router.get('/categories')
def list_categories():
    """Return all categories with prompt counts."""
    con = get_conn()
    try:
        rows = con.execute(
            'SELECT category, COUNT(*) as cnt FROM prompt_library GROUP BY category ORDER BY cnt DESC'
        ).fetchall()
        total = con.execute('SELECT COUNT(*) FROM prompt_library').fetchone()[0]
    finally:
        con.close()
    return {
        'categories': [{'id': r[0], 'count': r[1]} for r in rows],
        'total': total,
    }


@router.get('/search')
def search_prompts(q: str = '', limit: int = 10):
    """Full-text search with relevance scoring."""
    if not q or not q.strip():
        return {'results': [], 'count': 0}
    limit = min(max(1, int(limit)), 50)
    con = get_conn()
    try:
        rows = con.execute(
            """SELECT *,
               (CASE WHEN title LIKE ? THEN 3 ELSE 0 END +
                CASE WHEN tags LIKE ? THEN 2 ELSE 0 END +
                CASE WHEN content LIKE ? THEN 1 ELSE 0 END) as score
               FROM prompt_library
               WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
               ORDER BY score DESC, use_count DESC
               LIMIT ?""",
            (f'%{q}%',) * 3 + (f'%{q}%',) * 3 + (limit,),
        ).fetchall()
    finally:
        con.close()
    return {'results': [dict(r) for r in rows], 'count': len(rows)}


@router.get('/export')
def export_prompts():
    """Export all prompts as JSON."""
    con = get_conn()
    try:
        rows = con.execute('SELECT * FROM prompt_library ORDER BY category, title').fetchall()
    finally:
        con.close()
    return {
        'prompts': [dict(r) for r in rows],
        'count': len(rows),
        'exported_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }


@router.get('/{prompt_id}')
def get_prompt(prompt_id: str):
    """Get a single prompt by ID."""
    con = get_conn()
    try:
        row = con.execute('SELECT * FROM prompt_library WHERE id=?', (prompt_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return {'ok': False, 'error': 'Prompt not found'}
    return {**dict(row), 'ok': True}


# ── Create ─────────────────────────────────────────────────────────────────────


@router.post('')
async def create_prompt(req: Request):
    """Create and initialize a new prompt."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        body = {}
    title = (body.get('title') or '').strip()[:120]
    content = (body.get('content') or '').strip()
    if not title or not content:
        return {'ok': False, 'error': 'title and content required'}

    category = (body.get('category') or 'general').strip()[:32]
    if category not in VALID_CATEGORIES:
        category = 'general'

    pid = str(uuid.uuid4())[:8]
    con = get_conn()
    try:
        con.execute(
            'INSERT INTO prompt_library(id,title,content,category,tags,agent_id,is_favorite) VALUES(?,?,?,?,?,?,?)',
            (
                pid,
                title,
                content[:8000],
                category,
                (
                    ','.join(str(t) for t in body['tags'])
                    if isinstance(body.get('tags'), list)
                    else (body.get('tags') or '')
                )[:200],
                (body.get('agent_id') or '')[:64],
                int(bool(body.get('is_favorite', False))),
            ),
        )
        con.commit()
        audit_log('prompt_save', f'{pid}: {title[:60]}')
    finally:
        con.close()
    return {'ok': True, 'id': pid, 'title': title}


# ── Import (bulk) ──────────────────────────────────────────────────────────────


@router.post('/import')
async def import_prompts(req: Request):
    """Import multiple prompts from JSON (skips duplicates by title)."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        body = {}
    prompts = body.get('prompts', [])
    if not isinstance(prompts, list):
        return {'ok': False, 'error': 'prompts must be a list'}

    imported = 0
    skipped = 0
    con = get_conn()
    try:
        for p in prompts[:200]:
            title = (p.get('title') or '').strip()[:120]
            content = (p.get('content') or '').strip()
            if not title or not content:
                skipped += 1
                continue
            category = (p.get('category') or 'general').strip()[:32]
            if category not in VALID_CATEGORIES:
                category = 'general'
            pid = str(uuid.uuid4())[:8]
            try:
                con.execute(
                    'INSERT OR IGNORE INTO prompt_library(id,title,content,category,tags,agent_id,is_favorite) VALUES(?,?,?,?,?,?,?)',
                    (
                        pid,
                        title,
                        content[:8000],
                        category,
                        (p.get('tags') or '')[:200],
                        (p.get('agent_id') or '')[:64],
                        int(bool(p.get('is_favorite', False))),
                    ),
                )
                imported += 1
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                skipped += 1
        con.commit()
        audit_log('prompts_import', f'{imported} imported, {skipped} skipped')
    finally:
        con.close()
    return {'ok': True, 'imported': imported, 'skipped': skipped}


# ── Update ─────────────────────────────────────────────────────────────────────


@router.patch('/{prompt_id}')
async def update_prompt(prompt_id: str, req: Request):
    """Update existing prompt record or state."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        body = {}
    allowed = {'title', 'content', 'category', 'tags', 'agent_id', 'is_favorite'}
    sets, vals = [], []
    for k in allowed:
        if k in body:
            v = body[k]
            if k == 'title':
                v = str(v).strip()[:120]
            elif k == 'content':
                v = str(v)[:8000]
            elif k == 'category':
                v = str(v).strip()[:32]
                if v not in VALID_CATEGORIES:
                    v = 'general'
            elif k in ('tags', 'agent_id'):
                v = str(v)[:200]
            elif k == 'is_favorite':
                v = int(bool(v))
            sets.append(f'{k}=?')
            vals.append(v)

    if not sets:
        return {'ok': False, 'error': 'no fields to update'}

    sets.append('updated_at=CURRENT_TIMESTAMP')
    vals.append(prompt_id)

    con = get_conn()
    try:
        cur = con.execute(f'UPDATE prompt_library SET {", ".join(sets)} WHERE id=?', vals)
        con.commit()
        updated = cur.rowcount > 0
    finally:
        con.close()

    if not updated:
        return {'ok': False, 'error': 'Prompt not found'}
    return {'ok': True}


# ── Delete ─────────────────────────────────────────────────────────────────────


@router.delete('/{prompt_id}')
def delete_prompt(prompt_id: str):
    """Delete or remove specified prompt."""
    con = get_conn()
    try:
        cur = con.execute('DELETE FROM prompt_library WHERE id=?', (prompt_id,))
        con.commit()
        deleted = cur.rowcount > 0
    finally:
        con.close()
    if not deleted:
        return {'ok': False, 'error': 'Prompt not found'}
    audit_log('prompt_delete', prompt_id)
    return {'ok': True, 'deleted': prompt_id}


# ── Use counter ────────────────────────────────────────────────────────────────


@router.post('/{prompt_id}/use')
def record_use(prompt_id: str):
    """Record that a prompt was used — increments use_count."""
    con = get_conn()
    try:
        cur = con.execute(
            'UPDATE prompt_library SET use_count=use_count+1, updated_at=CURRENT_TIMESTAMP WHERE id=?', (prompt_id,)
        )
        con.commit()
        updated = cur.rowcount > 0
    finally:
        con.close()
    if not updated:
        return {'ok': False, 'error': 'Prompt not found'}
    return {'ok': True}


# ── Duplicate ──────────────────────────────────────────────────────────────────


@router.post('/{prompt_id}/duplicate')
def duplicate_prompt(prompt_id: str):
    """Duplicate a prompt with 'Copy of' prefix."""
    con = get_conn()
    try:
        row = con.execute('SELECT * FROM prompt_library WHERE id=?', (prompt_id,)).fetchone()
        if not row:
            return {'ok': False, 'error': 'Prompt not found'}

        d = dict(row)
        new_id = str(uuid.uuid4())[:8]
        new_title = f'Copy of {d["title"]}'[:120]
        con.execute(
            'INSERT INTO prompt_library(id,title,content,category,tags,agent_id,is_favorite) VALUES(?,?,?,?,?,?,0)',
            (new_id, new_title, d['content'], d['category'], d['tags'], d['agent_id']),
        )
        con.commit()
        audit_log('prompt_duplicate', f'{prompt_id} → {new_id}')
    finally:
        con.close()
    return {'ok': True, 'id': new_id, 'title': new_title}
