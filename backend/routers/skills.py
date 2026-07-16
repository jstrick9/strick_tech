"""
Agentic OS — Skills Hub Router
Real skill execution engine. Skills are defined in skills/skills.json
and executed via LLM + MCP tools chain.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/skills', tags=['skills'])
log = logging.getLogger('agentic.skills')

from backend.config import get_data_dir
ROOT = get_data_dir()
SKILLS_FILE = ROOT / 'skills' / 'skills.json'

# ── Default skills catalogue ───────────────────────────────────────────────────
DEFAULT_SKILLS = [
    {
        'id': 'seo_audit',
        'name': 'SEO Audit',
        'emoji': '🔍',
        'category': 'marketing',
        'description': 'Audit a URL for SEO: title, meta, headings, performance tips',
        'agent': 'researcher',
        'inputs': [{'id': 'url', 'label': 'URL to audit', 'type': 'text', 'required': True}],
        'prompt_template': 'Perform a comprehensive SEO audit for: {url}\n\nCheck: title tag, meta description, heading structure (H1-H6), keyword density, mobile-friendliness signals, page speed considerations, internal linking opportunities. Format results as a structured report with a score out of 100 and actionable recommendations.',
    },
    {
        'id': 'content_writer',
        'name': 'Content Writer',
        'emoji': '✍️',
        'category': 'content',
        'description': 'Write long-form blog posts, landing pages, or social copy',
        'agent': 'creative',
        'inputs': [
            {'id': 'topic', 'label': 'Topic', 'type': 'text', 'required': True},
            {
                'id': 'tone',
                'label': 'Tone',
                'type': 'select',
                'required': False,
                'options': ['professional', 'casual', 'technical', 'persuasive', 'friendly'],
            },
            {
                'id': 'length',
                'label': 'Length',
                'type': 'select',
                'required': False,
                'options': ['short (300w)', 'medium (600w)', 'long (1200w)', 'epic (2500w)'],
            },
        ],
        'prompt_template': 'Write a {length} {tone} article about: {topic}\n\nInclude: compelling headline, introduction hook, well-structured body with subheadings, actionable takeaways, strong conclusion. Optimise for reader engagement and SEO.',
    },
    {
        'id': 'code_review',
        'name': 'Code Review',
        'emoji': '🔨',
        'category': 'development',
        'description': 'Deep code review: security, performance, best practices',
        'agent': 'reviewer',
        'inputs': [
            {'id': 'code', 'label': 'Code to review', 'type': 'textarea', 'required': True},
            {'id': 'language', 'label': 'Language', 'type': 'text', 'required': False},
        ],
        'prompt_template': 'Perform a thorough code review of this {language} code:\n\n```{language}\n{code}\n```\n\nReview for: security vulnerabilities, performance issues, code smells, best practice violations, missing error handling, test coverage gaps. Provide specific line-level feedback and suggested fixes.',
    },
    {
        'id': 'market_research',
        'name': 'Market Research',
        'emoji': '📊',
        'category': 'research',
        'description': 'Research a market, competitor, or trend with structured output',
        'agent': 'researcher',
        'inputs': [
            {'id': 'topic', 'label': 'Market/Topic', 'type': 'text', 'required': True},
            {
                'id': 'depth',
                'label': 'Depth',
                'type': 'select',
                'required': False,
                'options': ['overview', 'detailed', 'comprehensive'],
            },
        ],
        'prompt_template': 'Conduct {depth} market research on: {topic}\n\nCover: market size & growth, key players & competitive landscape, customer segments, pricing trends, opportunities & threats, emerging technologies, go-to-market insights. Format with clear sections, data where available.',
    },
    {
        'id': 'email_sequence',
        'name': 'Email Sequence',
        'emoji': '📧',
        'category': 'marketing',
        'description': 'Write a 5-email nurture or onboarding sequence',
        'agent': 'creative',
        'inputs': [
            {'id': 'product', 'label': 'Product/Service', 'type': 'text', 'required': True},
            {'id': 'audience', 'label': 'Target Audience', 'type': 'text', 'required': True},
            {
                'id': 'goal',
                'label': 'Goal',
                'type': 'select',
                'required': False,
                'options': ['nurture', 'onboarding', 're-engagement', 'upsell', 'cold outreach'],
            },
        ],
        'prompt_template': 'Write a 5-email {goal} sequence for {product} targeting {audience}.\n\nFor each email include: subject line (A/B variant), preview text, body copy, CTA, send timing. Make each email build on the last with a clear narrative arc. Focus on value-first, not sales-first.',
    },
    {
        'id': 'api_design',
        'name': 'API Designer',
        'emoji': '🔌',
        'category': 'development',
        'description': 'Design a RESTful API with OpenAPI spec',
        'agent': 'builder',
        'inputs': [
            {'id': 'description', 'label': 'What should the API do?', 'type': 'textarea', 'required': True},
            {'id': 'stack', 'label': 'Tech stack', 'type': 'text', 'required': False},
        ],
        'prompt_template': 'Design a RESTful API for: {description}\n\nStack: {stack}\n\nProvide: OpenAPI 3.0 spec (YAML), endpoint design with HTTP methods, request/response schemas, authentication approach, error handling patterns, rate limiting strategy, example curl commands for each endpoint.',
    },
    {
        'id': 'refactor_plan',
        'name': 'Refactor Planner',
        'emoji': '🏗️',
        'category': 'development',
        'description': 'Create a step-by-step refactoring plan for existing code',
        'agent': 'reviewer',
        'inputs': [
            {'id': 'description', 'label': 'Current code / architecture', 'type': 'textarea', 'required': True},
            {'id': 'goal', 'label': 'Refactoring goal', 'type': 'text', 'required': True},
        ],
        'prompt_template': 'Create a detailed refactoring plan.\n\nCurrent state: {description}\n\nGoal: {goal}\n\nProvide: risk assessment, step-by-step migration plan with milestones, rollback strategy, testing approach at each stage, estimated effort, before/after architecture diagram (ASCII).',
    },
    {
        'id': 'pitch_deck',
        'name': 'Pitch Deck Writer',
        'emoji': '🚀',
        'category': 'content',
        'description': 'Write slide-by-slide pitch deck content for investors or clients',
        'agent': 'creative',
        'inputs': [
            {'id': 'company', 'label': 'Company/Product', 'type': 'text', 'required': True},
            {
                'id': 'audience',
                'label': 'Audience',
                'type': 'select',
                'required': False,
                'options': ['seed investors', 'series A', 'enterprise clients', 'accelerator'],
            },
        ],
        'prompt_template': 'Write a compelling {audience} pitch deck for: {company}\n\n12 slides: Problem → Solution → Market Size → Product Demo → Business Model → Traction → Team → Competition → Go-to-Market → Financials → Ask → Appendix. For each slide: headline, 3-5 bullet points, speaker notes.',
    },
    {
        'id': 'bug_report',
        'name': 'Bug Report Analyzer',
        'emoji': '🐛',
        'category': 'development',
        'description': 'Analyze a bug report and suggest root cause + fix',
        'agent': 'reviewer',
        'inputs': [
            {'id': 'bug', 'label': 'Bug description / error', 'type': 'textarea', 'required': True},
            {'id': 'stack', 'label': 'Stack trace (if available)', 'type': 'textarea', 'required': False},
        ],
        'prompt_template': 'Analyze this bug and provide a comprehensive fix:\n\nBug: {bug}\n\nStack trace: {stack}\n\nProvide: root cause analysis, step-by-step fix, code snippet if applicable, how to prevent it in future, related issues to watch for.',
    },
    {
        'id': 'daily_standup',
        'name': 'Daily Standup',
        'emoji': '📅',
        'category': 'productivity',
        'description': 'Generate a daily standup summary from your Kanban board',
        'agent': 'brain',
        'inputs': [],
        'prompt_template': 'Generate a concise daily standup report from the current Kanban state.\n\nFormat:\n**Yesterday:** (done tasks)\n**Today:** (doing tasks)\n**Blockers:** (blocked tasks)\n**Notes:** (anything worth flagging)\n\nKeep it under 200 words. Professional but conversational tone.',
    },
    {
        'id': 'competitor_analysis',
        'name': 'Competitor Analysis',
        'emoji': '🎯',
        'category': 'research',
        'description': 'Deep dive on a competitor: strengths, weaknesses, strategy',
        'agent': 'researcher',
        'inputs': [
            {'id': 'competitor', 'label': 'Competitor name/URL', 'type': 'text', 'required': True},
            {'id': 'your_product', 'label': 'Your product (for comparison)', 'type': 'text', 'required': False},
        ],
        'prompt_template': 'Conduct a detailed competitor analysis for: {competitor}\n\nCompare against: {your_product}\n\nCover: product features & UX, pricing strategy, target market, marketing channels, content strategy, technical stack (if known), funding/team, SWOT analysis, strategic gaps you can exploit.',
    },
    {
        'id': 'test_writer',
        'name': 'Test Suite Writer',
        'emoji': '🧪',
        'category': 'development',
        'description': 'Write comprehensive unit and integration tests',
        'agent': 'builder',
        'inputs': [
            {'id': 'code', 'label': 'Code to test', 'type': 'textarea', 'required': True},
            {
                'id': 'framework',
                'label': 'Test framework',
                'type': 'select',
                'required': False,
                'options': ['pytest', 'jest', 'vitest', 'mocha', 'playwright', 'cypress'],
            },
        ],
        'prompt_template': 'Write a comprehensive test suite for this code using {framework}:\n\n```\n{code}\n```\n\nInclude: unit tests for all functions, edge cases, error conditions, mocks where needed, integration tests, setup/teardown. Aim for >90% coverage. Add descriptive test names.',
    },
]


def load_skills() -> list[dict]:
    """Load skills from JSON file, fall back to defaults."""
    if SKILLS_FILE.exists():
        try:
            return json.loads(SKILLS_FILE.read_text())
        except Exception as e:
            log.warning('skills.json parse error (using defaults): %s', e)
    return DEFAULT_SKILLS


def save_skills(skills: list[dict]) -> bool:
    """Persist skills to JSON file. Returns True on success."""
    try:
        SKILLS_FILE.parent.mkdir(exist_ok=True)
        SKILLS_FILE.write_text(json.dumps(skills, indent=2))
        return True
    except Exception as e:
        log.error('Failed to save skills.json: %s', e)
        return False


# Seed on import if missing
if not SKILLS_FILE.exists():
    try:
        save_skills(DEFAULT_SKILLS)
    except Exception:
        pass


# ── Endpoints ──────────────────────────────────────────────────────────────────
@router.get('')
def list_skills(category: str = ''):
    """Retrieve and return list skills."""
    skills = load_skills()
    if category:
        skills = [s for s in skills if s.get('category', '') == category]
    return skills


@router.get('/categories')
def list_categories():
    """Retrieve and return list categories."""
    skills = load_skills()
    cats = sorted(set(s.get('category', 'other') for s in skills))
    return [{'id': c, 'count': sum(1 for s in skills if s.get('category') == c)} for c in cats]


@router.get('/{skill_id}')
def get_skill(skill_id: str):
    """Retrieve and return get skill."""
    skills = load_skills()
    s = next((s for s in skills if s['id'] == skill_id), None)
    if not s:
        return {'ok': False, 'error': f"Skill '{skill_id}' not found"}
    return s


@router.post('/run')
async def run_skill(req: Request):
    """
    POST /api/skills/run
    Body: {skill_id, inputs: {key: value, ...}}
    Returns: {ok, output, skill_id, agent, latency_ms, tokens}
    """
    try:
        body = await req.json()
    except Exception:
        body = {}
    skill_id = body.get('skill_id', '')
    inputs = body.get('inputs', {})

    skills = load_skills()
    skill = next((s for s in skills if s['id'] == skill_id), None)
    if not skill:
        return {'ok': False, 'error': f"Skill '{skill_id}' not found"}

    # Build prompt from template
    template = skill.get('prompt_template', '')
    try:
        prompt = template.format(**{k: str(v) for k, v in inputs.items()})
    except KeyError as e:
        return {'ok': False, 'error': f'Missing input: {e}'}

    # Special handling for standup — enrich with live Kanban data
    if skill_id == 'daily_standup':
        prompt = await _enrich_standup_prompt(prompt)

    agent_id = skill.get('agent', 'brain')
    t0 = time.time()
    log.info("Running skill '%s' with agent '%s'", skill_id, agent_id)

    from ..services import llm, memory_db

    agents = {a['id']: a for a in memory_db.agents_list()}
    agent = agents.get(agent_id, {'id': agent_id, 'name': agent_id, 'model': '', 'system_prompt': ''})
    system = agent.get('system_prompt') or (
        f'You are {agent.get("name", agent_id)}, an expert AI assistant in Agentic OS. '
        f'Complete the requested task thoroughly and professionally. Use Markdown formatting.'
    )

    messages = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': prompt},
    ]

    result = await llm.complete(
        messages, agent_id=agent.get('model') or agent_id, max_tokens=2048, temperature=0.7, inject_steering=False
    )

    output = result.get('text', '')
    latency = round((time.time() - t0) * 1000)

    # Store in memory only on successful result
    if output and result.get('ok'):
        memory_db.memory_add(f'skill:{skill_id}', output[:600], f'skill,{skill_id},{agent_id}')
    memory_db.audit_log('skill_run', f'{skill_id} → {agent_id} ({latency}ms)')

    return {
        'ok': result.get('ok', False),
        'skill_id': skill_id,
        'skill_name': skill.get('name', skill_id),
        'agent': agent_id,
        'output': output,
        'tokens': result.get('tokens', 0),
        'cost': result.get('cost', 0.0),
        'latency_ms': latency,
        'model': result.get('model', ''),
    }


@router.post('')
async def create_skill(req: Request):
    """Create a custom skill."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    name = (body.get('name') or '').strip()
    if not name:
        return {'ok': False, 'error': 'name required'}

    import re

    skill = {
        'id': re.sub(r'[^a-z0-9_]', '_', name.lower())[:32],
        'name': name[:80],
        'emoji': body.get('emoji', '⚡')[:4],
        'category': body.get('category', 'custom')[:32],
        'description': body.get('description', '')[:200],
        'agent': body.get('agent', 'brain')[:32],
        'inputs': body.get('inputs', []),
        'prompt_template': body.get('prompt_template', '{prompt}')[:4000],
    }
    skills = load_skills()
    # Prevent overwriting built-in skill ids with custom skills
    builtin_ids = {s['id'] for s in DEFAULT_SKILLS}
    if skill['id'] in builtin_ids:
        # Append a suffix to avoid collision
        skill['id'] = skill['id'] + '_custom'
    # Replace if custom skill with same id exists
    skills = [s for s in skills if s['id'] != skill['id']]
    skills.append(skill)
    if not save_skills(skills):
        return {'ok': False, 'error': 'Failed to save skill — disk write error'}
    from ..services.memory_db import audit_log

    audit_log('skill_create', skill['id'])
    return {'ok': True, 'skill': skill}


@router.delete('/{skill_id}')
def delete_skill(skill_id: str):
    """Delete or remove specified skill."""
    skills = load_skills()
    before = len(skills)
    skills = [s for s in skills if s['id'] != skill_id]
    if len(skills) == before:
        return {'ok': False, 'error': 'Skill not found'}
    if not save_skills(skills):
        return {'ok': False, 'error': 'Failed to save — disk write error'}
    return {'ok': True, 'deleted': skill_id}


# ── Helpers ────────────────────────────────────────────────────────────────────
async def _enrich_standup_prompt(prompt: str) -> str:
    """Add live Kanban data to standup prompt."""
    try:
        from ..services.memory_db import get_conn

        con = get_conn()
        try:
            rows = con.execute(
                "SELECT title, status, agent FROM tasks ORDER BY CASE status WHEN 'done' THEN 0 WHEN 'doing' THEN 1 WHEN 'todo' THEN 2 ELSE 3 END, updated_at DESC LIMIT 20"
            ).fetchall()
        finally:
            con.close()
        kanban_summary = '\n'.join(f'- [{r["status"].upper()}] {r["title"]} ({r["agent"]})' for r in rows)
        return prompt + f'\n\nCurrent Kanban:\n{kanban_summary}'
    except Exception:
        return prompt
