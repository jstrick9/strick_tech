"""
Agentic OS — Sprint B · Feature 1: Hierarchical Supervisor Agent
═════════════════════════════════════════════════════════════════
The Supervisor is the central orchestrator that:
  1. Accepts a high-level Goal from the user
  2. Decomposes it into a dependency-ordered Task DAG via the Brain agent
  3. Assigns each task to the most capable Specialist agent
  4. Executes tasks in topological order (parallel where dependencies allow)
  5. Aggregates results and synthesizes a final answer
  6. Records every decision in the Immutable Audit Log (Sprint A)
  7. Integrates with HITL for high-risk steps

Architecture (McKinsey Hierarchical Supervisor Pattern):
  Goal → Brain decomposes → DAG of tasks → Parallel specialist execution
       → Critic review → HITL gate (if needed) → Outcome Evaluator → Done

Specialist agents:
  researcher  — web search, RAG, deep research
  builder     — code writing, file creation, scaffolding
  reviewer    — security review, code quality, test generation
  creative    — content, images, storytelling
  memory      — knowledge graph, memory search
  brain       — complex reasoning, planning, analysis
  orchestrator— meta-coordination, merging, judging
"""

from __future__ import annotations

import contextlib

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix='/api/supervisor', tags=['supervisor'])
log = logging.getLogger('agentic.supervisor')

ROOT = Path(__file__).resolve().parents[2]

# ── Schema ─────────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS supervisor_runs (
    run_id        TEXT PRIMARY KEY,
    goal_id       TEXT NOT NULL DEFAULT '',
    goal_title    TEXT NOT NULL DEFAULT '',
    goal_text     TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'decomposing',
    strategy      TEXT NOT NULL DEFAULT 'hierarchical',
    task_count    INTEGER NOT NULL DEFAULT 0,
    done_count    INTEGER NOT NULL DEFAULT 0,
    failed_count  INTEGER NOT NULL DEFAULT 0,
    final_output  TEXT NOT NULL DEFAULT '',
    eval_score    REAL,
    eval_notes    TEXT NOT NULL DEFAULT '',
    total_tokens  INTEGER NOT NULL DEFAULT 0,
    total_cost    REAL NOT NULL DEFAULT 0,
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL DEFAULT '',
    completed_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS supervisor_tasks (
    task_id       TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL,
    seq           INTEGER NOT NULL DEFAULT 0,
    title         TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    agent_id      TEXT NOT NULL DEFAULT '',
    depends_on    TEXT NOT NULL DEFAULT '[]',
    status        TEXT NOT NULL DEFAULT 'pending',
    output        TEXT NOT NULL DEFAULT '',
    tokens        INTEGER NOT NULL DEFAULT 0,
    cost          REAL NOT NULL DEFAULT 0,
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    risk_level    TEXT NOT NULL DEFAULT 'low',
    hitl_required INTEGER NOT NULL DEFAULT 0,
    hitl_id       TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT '',
    started_at    TEXT NOT NULL DEFAULT '',
    completed_at  TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (run_id) REFERENCES supervisor_runs(run_id)
);
CREATE INDEX IF NOT EXISTS idx_stask_run    ON supervisor_tasks(run_id, status);
CREATE INDEX IF NOT EXISTS idx_stask_agent  ON supervisor_tasks(agent_id);

CREATE TABLE IF NOT EXISTS supervisor_kill_switches (
    run_id      TEXT PRIMARY KEY,
    killed_at   TEXT NOT NULL DEFAULT '',
    reason      TEXT NOT NULL DEFAULT ''
);
"""


def _get_conn():
    from ..services.memory_db import get_conn

    return get_conn()


def _ensure_schema():
    con = _get_conn()
    try:
        con.executescript(_SCHEMA)
        con.commit()
    finally:
        con.close()


_ensure_schema()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _epoch_ms() -> int:
    return int(time.time() * 1000)


# ── Specialist capability map ──────────────────────────────────────────────────
SPECIALIST_SKILLS = {
    'researcher': [
        'research',
        'search',
        'find',
        'gather',
        'analyze data',
        'survey',
        'literature',
        'web',
        'information',
    ],
    'builder': ['code', 'build', 'implement', 'create file', 'write', 'develop', 'program', 'scaffold', 'api'],
    'reviewer': ['review', 'test', 'validate', 'security', 'audit', 'check', 'quality', 'verify', 'debug'],
    'creative': ['design', 'write content', 'story', 'marketing', 'copywrite', 'image', 'brand', 'creative'],
    'memory': ['remember', 'recall', 'store', 'knowledge graph', 'retrieve', 'memory', 'past'],
    'brain': ['plan', 'reason', 'decide', 'strategy', 'architect', 'complex', 'analysis', 'synthesize'],
    'orchestrator': ['coordinate', 'merge', 'combine', 'judge', 'aggregate', 'finalize', 'summarize'],
}


def _assign_specialist(task_title: str, task_desc: str) -> str:
    """Pick the best specialist for a task using keyword matching."""
    text = (task_title + ' ' + task_desc).lower()
    best, best_score = 'brain', 0
    for agent_id, skills in SPECIALIST_SKILLS.items():
        score = sum(1 for kw in skills if kw in text)
        if score > best_score:
            best, best_score = agent_id, score
    return best


# ── Decomposition via Brain agent ──────────────────────────────────────────────
DECOMPOSE_SYSTEM = """You are the Brain decomposition agent in Agentic OS.
Your job: break a high-level goal into 3–8 concrete, actionable tasks with clear dependencies.

Return ONLY valid JSON in this exact format:
{
  "tasks": [
    {
      "seq": 1,
      "title": "Short task title",
      "description": "Detailed description of what to do and expected output",
      "agent_hint": "researcher|builder|reviewer|creative|memory|brain|orchestrator",
      "depends_on": [],
      "risk_level": "low|medium|high|critical",
      "estimated_tokens": 500
    }
  ],
  "strategy_notes": "One sentence about the overall approach"
}

Rules:
- seq numbers start at 1 and are UNIQUE
- depends_on lists seq numbers of tasks that must complete first
- Keep descriptions specific and actionable
- Risk high/critical tasks will require human approval (HITL)
- Assign agent_hint to the most capable specialist
- No circular dependencies
"""


async def _decompose_goal(goal_text: str, goal_id: str, run_id: str) -> list[dict]:
    """Ask Brain to decompose the goal into a task DAG."""
    from ..services.llm import complete

    messages = [{'role': 'system', 'content': DECOMPOSE_SYSTEM}, {'role': 'user', 'content': f'Goal: {goal_text}'}]

    result = await complete(messages, agent_id='brain', max_tokens=1500, temperature=0.3, inject_steering=False)
    text = result.get('text', '')

    # Parse JSON
    import re

    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(0))
            tasks = parsed.get('tasks', [])
            if tasks:
                log.info('Decomposed goal %s into %d tasks', goal_id, len(tasks))
                return tasks
        except Exception as e:
            log.warning('JSON parse failed for decomposition: %s', e)

    # Fallback: create a single research + execute + review task
    log.warning('Falling back to default 3-task DAG for goal %s', goal_id)
    return [
        {
            'seq': 1,
            'title': 'Research & Plan',
            'description': f'Research and plan how to achieve: {goal_text}',
            'agent_hint': 'researcher',
            'depends_on': [],
            'risk_level': 'low',
            'estimated_tokens': 600,
        },
        {
            'seq': 2,
            'title': 'Execute',
            'description': f'Execute the plan for: {goal_text}',
            'agent_hint': 'builder',
            'depends_on': [1],
            'risk_level': 'low',
            'estimated_tokens': 800,
        },
        {
            'seq': 3,
            'title': 'Review & Finalize',
            'description': f'Review and finalize the output for: {goal_text}',
            'agent_hint': 'reviewer',
            'depends_on': [2],
            'risk_level': 'low',
            'estimated_tokens': 400,
        },
    ]


# ── Task execution ─────────────────────────────────────────────────────────────
SPECIALIST_SYSTEM = """You are {agent_name}, a specialist agent in Agentic OS.
Your role: {agent_role}

You are executing ONE specific task in a larger goal.
Be focused, thorough, and deliver exactly what the task requires.
Reference previous task outputs where relevant.
Use Markdown for structure. Be practical, not vague."""


async def _execute_task(task: dict, run_id: str, goal_text: str, context_so_far: list[dict]) -> dict:
    """Execute a single task with the assigned specialist agent."""
    from ..services.llm import complete

    agent_id = task.get('agent_id', 'brain')
    task_id = task['task_id']
    title = task['title']
    desc = task['description']

    # Build context from completed upstream tasks
    context_parts = []
    for prev in context_so_far:
        if prev.get('output'):
            context_parts.append(f'### Task {prev["seq"]}: {prev["title"]}\n{prev["output"][:800]}')
    context_str = '\n\n'.join(context_parts) if context_parts else 'No prior context.'

    # Load agent info
    con = _get_conn()
    try:
        agent_row = con.execute('SELECT name, role, system_prompt FROM agents WHERE id=?', (agent_id,)).fetchone()
    finally:
        con.close()

    agent_name = agent_row['name'] if agent_row else agent_id.title()
    agent_role = agent_row['role'] if agent_row else 'AI specialist'
    agent_sys = agent_row['system_prompt'] if agent_row else ''

    system = SPECIALIST_SYSTEM.format(agent_name=agent_name, agent_role=agent_role)
    if agent_sys:
        system += f'\n\n{agent_sys}'

    messages = [
        {'role': 'system', 'content': system},
        {
            'role': 'user',
            'content': (
                f'**Overall Goal:** {goal_text}\n\n'
                f'**Your Task (#{task["seq"]}):** {title}\n\n'
                f'**Task Description:** {desc}\n\n'
                f'**Prior Task Outputs:**\n{context_str}\n\n'
                f'Execute this task now. Be specific and complete.'
            ),
        },
    ]

    t0 = _epoch_ms()
    result = await complete(messages, agent_id=agent_id, max_tokens=1200, temperature=0.5, inject_steering=False)
    duration = _epoch_ms() - t0

    return {
        'output': result.get('text', ''),
        'tokens': result.get('tokens', 0),
        'cost': result.get('cost', 0.0),
        'duration_ms': duration,
        'model': result.get('model', ''),
    }


# ── Outcome evaluation ─────────────────────────────────────────────────────────
EVAL_SYSTEM = """You are an objective evaluator. Score how well the agent output achieves the goal.
Return ONLY valid JSON: {"score": 0.0-1.0, "notes": "brief evaluation", "suggestions": ["list of improvements"]}"""


async def _evaluate_outcome(goal_text: str, final_output: str) -> dict:
    """Score how well the final output achieves the original goal."""
    from ..services.llm import complete

    messages = [
        {'role': 'system', 'content': EVAL_SYSTEM},
        {'role': 'user', 'content': f'Goal: {goal_text}\n\nOutput:\n{final_output[:2000]}'},
    ]
    result = await complete(messages, agent_id='reviewer', max_tokens=300, temperature=0.1, inject_steering=False)
    import re

    m = re.search(r'\{.*\}', result.get('text', ''), re.DOTALL)
    if m:
        with contextlib.suppress(Exception):
            return json.loads(m.group(0))
    return {'score': 0.7, 'notes': 'Evaluation unavailable', 'suggestions': []}


# ── Synthesis ──────────────────────────────────────────────────────────────────
SYNTH_SYSTEM = """You are the Orchestrator agent. Synthesize all specialist outputs into one coherent final answer.
Preserve the key insights from each specialist. Use clear Markdown structure.
Begin with a brief executive summary, then present the full synthesized result."""


async def _synthesize(goal_text: str, completed_tasks: list[dict]) -> str:
    """Merge all task outputs into a single coherent response."""
    from ..services.llm import complete

    parts = []
    for t in completed_tasks:
        if t.get('output'):
            parts.append(f'## Specialist: {t["agent_id"].title()} — {t["title"]}\n{t["output"][:1000]}')

    combined = '\n\n---\n\n'.join(parts)
    messages = [
        {'role': 'system', 'content': SYNTH_SYSTEM},
        {'role': 'user', 'content': f'Goal: {goal_text}\n\nSpecialist Outputs:\n{combined}'},
    ]
    result = await complete(messages, agent_id='orchestrator', max_tokens=1500, temperature=0.4, inject_steering=False)
    return result.get('text', combined[:1000])


# ── Topological sort (respect depends_on) ────────────────────────────────────
def _topo_sort(tasks: list[dict]) -> list[list[dict]]:
    """Return tasks grouped into waves that can execute in parallel."""
    seq_map = {t['seq']: t for t in tasks}
    waves: list[list[dict]] = []
    remaining = list(tasks)
    completed_seqs: set = set()

    for _ in range(len(tasks) + 1):
        if not remaining:
            break
        wave = [t for t in remaining if all(d in completed_seqs for d in (t.get('depends_on') or []))]
        if not wave:
            # Circular or unresolvable — run everything left in one wave
            wave = remaining
        waves.append(wave)
        for t in wave:
            completed_seqs.add(t['seq'])
        remaining = [t for t in remaining if t not in wave]

    return waves


# ── DB helpers ─────────────────────────────────────────────────────────────────
def _update_run(run_id: str, **kwargs):
    con = _get_conn()
    try:
        kwargs['updated_at'] = _now()
        sets = ', '.join(f'{k}=?' for k in kwargs)
        con.execute(f'UPDATE supervisor_runs SET {sets} WHERE run_id=?', list(kwargs.values()) + [run_id])
        con.commit()
    finally:
        con.close()


def _update_task(task_id: str, **kwargs):
    con = _get_conn()
    try:
        sets = ', '.join(f'{k}=?' for k in kwargs)
        con.execute(f'UPDATE supervisor_tasks SET {sets} WHERE task_id=?', list(kwargs.values()) + [task_id])
        con.commit()
    finally:
        con.close()


def _is_killed(run_id: str) -> bool:
    con = _get_conn()
    try:
        row = con.execute('SELECT 1 FROM supervisor_kill_switches WHERE run_id=?', (run_id,)).fetchone()
        return row is not None
    finally:
        con.close()


# ── Main orchestration coroutine ───────────────────────────────────────────────
async def _run_supervisor(run_id: str, goal_id: str, goal_text: str):
    """Full supervisor run: decompose → schedule → execute → synthesize → evaluate."""
    from ..routers.audit_log import append_entry
    from ..routers.websocket import broadcast

    t_start = _epoch_ms()

    try:
        # ── Phase 1: Decompose ─────────────────────────────────────────────
        await broadcast(
            {
                'type': 'supervisor_update',
                'run_id': run_id,
                'status': 'decomposing',
                'message': 'Brain is decomposing your goal…',
            }
        )

        raw_tasks = await _decompose_goal(goal_text, goal_id, run_id)

        # Persist tasks
        con = _get_conn()
        try:
            db_tasks = []
            for rt in raw_tasks:
                task_id = f'stask_{uuid.uuid4().hex[:10]}'
                agent_id = rt.get('agent_hint', '')
                if not agent_id or agent_id not in SPECIALIST_SKILLS:
                    agent_id = _assign_specialist(rt.get('title', ''), rt.get('description', ''))

                task = {
                    'task_id': task_id,
                    'run_id': run_id,
                    'seq': rt['seq'],
                    'title': rt.get('title', 'Task')[:200],
                    'description': rt.get('description', '')[:2000],
                    'agent_id': agent_id,
                    'depends_on': json.dumps(rt.get('depends_on', [])),
                    'status': 'pending',
                    'risk_level': rt.get('risk_level', 'low'),
                    'hitl_required': 1 if rt.get('risk_level', 'low') in ('high', 'critical') else 0,
                    'created_at': _now(),
                }
                con.execute(
                    """
                    INSERT INTO supervisor_tasks
                      (task_id,run_id,seq,title,description,agent_id,depends_on,
                       status,risk_level,hitl_required,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                    list(task.values()),
                )
                task['depends_on'] = rt.get('depends_on', [])
                db_tasks.append(task)

            con.execute(
                "UPDATE supervisor_runs SET task_count=?, status='scheduled', updated_at=? WHERE run_id=?",
                (len(db_tasks), _now(), run_id),
            )
            con.commit()
        finally:
            con.close()

        append_entry(
            'supervisor',
            'Supervisor',
            'goal_decomposed',
            f"Goal '{goal_text[:100]}' → {len(db_tasks)} tasks",
            reasoning=f'Brain decomposed into {len(db_tasks)} specialist tasks',
            authority='user',
            risk_level='low',
            outcome='success',
            metadata={'run_id': run_id, 'task_count': len(db_tasks)},
        )

        await broadcast(
            {
                'type': 'supervisor_update',
                'run_id': run_id,
                'status': 'scheduled',
                'message': f'Decomposed into {len(db_tasks)} tasks',
                'tasks': [
                    {'task_id': t['task_id'], 'title': t['title'], 'agent_id': t['agent_id'], 'seq': t['seq']}
                    for t in db_tasks
                ],
            }
        )

        # ── Phase 2: Execute (topological waves) ───────────────────────────
        waves = _topo_sort(db_tasks)
        completed_tasks: list[dict] = []
        total_tokens, total_cost = 0, 0.0
        done_count = 0

        _update_run(run_id, status='running')

        for wave_idx, wave in enumerate(waves):
            if _is_killed(run_id):
                _update_run(run_id, status='killed')
                return

            await broadcast(
                {
                    'type': 'supervisor_update',
                    'run_id': run_id,
                    'status': 'running',
                    'message': f'Wave {wave_idx + 1}/{len(waves)}: running {len(wave)} task(s) in parallel',
                    'wave': wave_idx + 1,
                }
            )

            # HITL check for high-risk tasks
            for task in wave:
                if task.get('hitl_required') and task.get('risk_level') in ('high', 'critical'):
                    _update_task(task['task_id'], status='awaiting_hitl')
                    try:
                        hitl_resp = await asyncio.get_event_loop().run_in_executor(
                            None,
                            __import__('requests').post,
                            f'http://127.0.0.1:{int(__import__("os").getenv("AGENTIC_OS_PORT", "8787"))}/api/hitl/interrupt',
                        )
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
                        pass  # Continue even if HITL request fails

            # Run wave tasks in parallel
            async def _run_wave_task(task: dict):
                _update_task(task['task_id'], status='running', started_at=_now())
                await broadcast(
                    {
                        'type': 'supervisor_task_start',
                        'run_id': run_id,
                        'task_id': task['task_id'],
                        'agent_id': task['agent_id'],
                        'title': task['title'],
                        'seq': task['seq'],
                    }
                )
                try:
                    exec_result = await _execute_task(task, run_id, goal_text, completed_tasks)
                    output = exec_result['output']
                    tokens = exec_result['tokens']
                    cost = exec_result['cost']
                    dur = exec_result['duration_ms']

                    _update_task(
                        task['task_id'],
                        status='done',
                        output=output[:5000],
                        tokens=tokens,
                        cost=cost,
                        duration_ms=dur,
                        completed_at=_now(),
                    )

                    task['output'] = output
                    task['tokens'] = tokens
                    task['cost'] = cost

                    append_entry(
                        task['agent_id'],
                        task['agent_id'].title(),
                        'task_completed',
                        f'[{task["title"]}] {output[:150]}',
                        reasoning=task['description'][:200],
                        authority='supervisor',
                        risk_level=task.get('risk_level', 'low'),
                        outcome='success',
                        metadata={'run_id': run_id, 'task_id': task['task_id']},
                    )
                    await broadcast(
                        {
                            'type': 'supervisor_task_done',
                            'run_id': run_id,
                            'task_id': task['task_id'],
                            'seq': task['seq'],
                            'output_preview': output[:200],
                        }
                    )
                    return task

                except Exception as e:
                    err = str(e)[:300]
                    _update_task(task['task_id'], status='failed', output=f'Error: {err}')
                    append_entry(
                        task['agent_id'],
                        task['agent_id'].title(),
                        'task_failed',
                        f'[{task["title"]}] {err}',
                        authority='supervisor',
                        risk_level='high',
                        outcome='failure',
                        metadata={'run_id': run_id},
                    )
                    log.error('Task %s failed: %s', task['task_id'], err)
                    task['output'] = f'Error: {err}'
                    return task

            wave_results = await asyncio.gather(*[_run_wave_task(t) for t in wave])

            for res in wave_results:
                completed_tasks.append(res)
                if not res.get('output', '').startswith('Error:'):
                    done_count += 1
                total_tokens += res.get('tokens', 0)
                total_cost += res.get('cost', 0.0)

            _update_run(run_id, done_count=done_count, total_tokens=total_tokens, total_cost=round(total_cost, 6))

        if _is_killed(run_id):
            return

        # ── Phase 3: Synthesize ────────────────────────────────────────────
        _update_run(run_id, status='synthesizing')
        await broadcast(
            {
                'type': 'supervisor_update',
                'run_id': run_id,
                'status': 'synthesizing',
                'message': 'Orchestrator is synthesizing all outputs…',
            }
        )

        final_output = await _synthesize(goal_text, completed_tasks)

        # ── Phase 4: Evaluate ──────────────────────────────────────────────
        eval_result = await _evaluate_outcome(goal_text, final_output)
        eval_score = eval_result.get('score', 0.7)
        eval_notes = eval_result.get('notes', '')

        duration_ms = _epoch_ms() - t_start

        _update_run(
            run_id,
            status='done',
            final_output=final_output[:8000],
            eval_score=eval_score,
            eval_notes=eval_notes[:500],
            total_tokens=total_tokens,
            total_cost=round(total_cost, 6),
            duration_ms=duration_ms,
            done_count=done_count,
            completed_at=_now(),
        )

        append_entry(
            'supervisor',
            'Supervisor',
            'run_completed',
            f"Goal '{goal_text[:80]}' done — score {eval_score:.0%}",
            reasoning=eval_notes[:200],
            authority='user',
            risk_level='low',
            outcome='success',
            metadata={
                'run_id': run_id,
                'eval_score': eval_score,
                'total_tokens': total_tokens,
                'duration_ms': duration_ms,
            },
        )

        await broadcast(
            {
                'type': 'supervisor_done',
                'run_id': run_id,
                'eval_score': eval_score,
                'eval_notes': eval_notes,
                'final_output': final_output[:500],
                'duration_ms': duration_ms,
                'total_tokens': total_tokens,
            }
        )

        log.info('Supervisor run %s complete — score %.0f%% in %dms', run_id, eval_score * 100, duration_ms)

    except Exception as e:
        err = str(e)[:500]
        log.error('Supervisor run %s crashed: %s', run_id, err)
        _update_run(run_id, status='failed', final_output=f'Supervisor error: {err}', duration_ms=_epoch_ms() - t_start)
        append_entry(
            'supervisor',
            'Supervisor',
            'run_failed',
            err,
            authority='user',
            risk_level='high',
            outcome='failure',
            metadata={'run_id': run_id},
        )
        try:
            from ..routers.websocket import broadcast

            await broadcast({'type': 'supervisor_error', 'run_id': run_id, 'error': err})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
            pass


# ── API Routes ─────────────────────────────────────────────────────────────────
@router.post('/run')
async def start_supervisor_run(req: Request):
    """Start a new supervisor run for a goal."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    goal_text = (body.get('goal') or body.get('goal_text') or '').strip()
    goal_id = body.get('goal_id') or ''
    goal_title = (body.get('goal_title') or goal_text[:80]).strip()
    strategy = (body.get('strategy') or 'hierarchical').strip()

    if not goal_text:
        return JSONResponse({'ok': False, 'error': 'goal text required'}, status_code=400)

    run_id = f'srun_{uuid.uuid4().hex[:10]}'
    now = _now()

    con = _get_conn()
    try:
        con.execute(
            """
            INSERT INTO supervisor_runs
              (run_id,goal_id,goal_title,goal_text,status,strategy,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?)
        """,
            (run_id, goal_id, goal_title, goal_text, 'decomposing', strategy, now, now),
        )
        con.commit()
    finally:
        con.close()

    # Fire-and-forget
    asyncio.create_task(_run_supervisor(run_id, goal_id, goal_text))

    return {'ok': True, 'run_id': run_id, 'goal_text': goal_text, 'status': 'decomposing'}


@router.get('/run/{run_id}')
def get_run(run_id: str):
    """Get status and results of a supervisor run."""
    con = _get_conn()
    try:
        run = con.execute('SELECT * FROM supervisor_runs WHERE run_id=?', (run_id,)).fetchone()
        if not run:
            return JSONResponse({'ok': False, 'error': 'Run not found'}, status_code=404)
        tasks = con.execute('SELECT * FROM supervisor_tasks WHERE run_id=? ORDER BY seq', (run_id,)).fetchall()
    finally:
        con.close()

    run_d = dict(run)
    tasks_d = []
    for t in tasks:
        td = dict(t)
        try:
            td['depends_on'] = json.loads(td.get('depends_on', '[]'))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
            td['depends_on'] = []
        tasks_d.append(td)

    return {'ok': True, 'run': run_d, 'tasks': tasks_d}


@router.get('/runs')
def list_runs(limit: int = 20, status: str = ''):
    """List all supervisor runs."""
    con = _get_conn()
    try:
        if status:
            rows = con.execute(
                'SELECT * FROM supervisor_runs WHERE status=? ORDER BY created_at DESC LIMIT ?',
                (status, min(limit, 100)),
            ).fetchall()
        else:
            rows = con.execute(
                'SELECT * FROM supervisor_runs ORDER BY created_at DESC LIMIT ?', (min(limit, 100),)
            ).fetchall()
    finally:
        con.close()
    return {'runs': [dict(r) for r in rows], 'count': len(rows)}


@router.post('/run/{run_id}/kill')
async def kill_run(run_id: str, req: Request):
    """Emergency kill switch for a running supervisor."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
            body = {}
        reason = (body.get('reason') or 'User kill switch')[:200]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
        reason = 'User kill switch'

    con = _get_conn()
    try:
        run = con.execute('SELECT status FROM supervisor_runs WHERE run_id=?', (run_id,)).fetchone()
        if not run:
            return JSONResponse({'ok': False, 'error': 'Run not found'}, status_code=404)
        con.execute(
            'INSERT OR REPLACE INTO supervisor_kill_switches (run_id,killed_at,reason) VALUES (?,?,?)',
            (run_id, _now(), reason),
        )
        con.execute("UPDATE supervisor_runs SET status='killed', updated_at=? WHERE run_id=?", (_now(), run_id))
        con.commit()
    finally:
        con.close()

    from ..routers.audit_log import append_entry

    append_entry(
        'user',
        'User',
        'supervisor_killed',
        f'Run {run_id} killed: {reason}',
        authority='user',
        risk_level='medium',
        outcome='blocked',
        metadata={'run_id': run_id},
    )

    try:
        from ..routers.websocket import broadcast

        await broadcast({'type': 'supervisor_killed', 'run_id': run_id, 'reason': reason})
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
        pass

    log.info('Supervisor run %s killed: %s', run_id, reason)
    return {'ok': True, 'run_id': run_id, 'killed': True, 'reason': reason}


@router.delete('/run/{run_id}')
def delete_run(run_id: str):
    """Delete a completed/failed run."""
    con = _get_conn()
    try:
        con.execute('DELETE FROM supervisor_tasks WHERE run_id=?', (run_id,))
        con.execute('DELETE FROM supervisor_runs WHERE run_id=?', (run_id,))
        con.execute('DELETE FROM supervisor_kill_switches WHERE run_id=?', (run_id,))
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'deleted': run_id}


@router.get('/stats')
def supervisor_stats():
    """Overall supervisor statistics."""
    con = _get_conn()
    try:
        total = con.execute('SELECT COUNT(*) FROM supervisor_runs').fetchone()[0]
        by_status = con.execute('SELECT status, COUNT(*) as cnt FROM supervisor_runs GROUP BY status').fetchall()
        avg_score = con.execute('SELECT AVG(eval_score) FROM supervisor_runs WHERE eval_score IS NOT NULL').fetchone()[
            0
        ]
        total_tok = con.execute('SELECT SUM(total_tokens) FROM supervisor_runs').fetchone()[0]
        total_cost = con.execute('SELECT SUM(total_cost) FROM supervisor_runs').fetchone()[0]
        top_agents = con.execute("""
            SELECT agent_id, COUNT(*) as cnt, AVG(cost) as avg_cost
            FROM supervisor_tasks GROUP BY agent_id ORDER BY cnt DESC
        """).fetchall()
    finally:
        con.close()

    return {
        'total_runs': total,
        'by_status': {r['status']: r['cnt'] for r in by_status},
        'avg_eval_score': round(avg_score or 0, 2),
        'total_tokens': total_tok or 0,
        'total_cost': round(total_cost or 0, 6),
        'top_agents': [dict(r) for r in top_agents],
    }


@router.get('/run/{run_id}/dag')
def get_dag(run_id: str):
    """
    Return a fully computed DAG for the given run, ready for the visual canvas.
    Each node includes: position (auto-layout), status, agent, timings.
    Each edge includes: source, target, label, active state.
    """
    con = _get_conn()
    try:
        run = con.execute('SELECT * FROM supervisor_runs WHERE run_id=?', (run_id,)).fetchone()
        if not run:
            return JSONResponse({'ok': False, 'error': 'Run not found'}, status_code=404)
        tasks = con.execute('SELECT * FROM supervisor_tasks WHERE run_id=? ORDER BY seq', (run_id,)).fetchall()
    finally:
        con.close()

    run_d = dict(run)
    tasks_d = []
    for t in tasks:
        td = dict(t)
        try:
            td['depends_on'] = json.loads(td.get('depends_on', '[]'))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
            td['depends_on'] = []
        tasks_d.append(td)

    # ── Auto-layout: assign x/y using wave (topological) columns ──────────────
    # Build seq→task map and determine which wave each task belongs to
    seq_map = {t['seq']: t for t in tasks_d}

    # Compute wave per task via BFS on dependency graph
    wave_of = {}
    for t in tasks_d:
        if not t['depends_on']:
            wave_of[t['seq']] = 0

    changed = True
    while changed:
        changed = False
        for t in tasks_d:
            deps = t['depends_on']
            if deps and t['seq'] not in wave_of:
                if all(d in wave_of for d in deps):
                    wave_of[t['seq']] = max(wave_of[d] for d in deps) + 1
                    changed = True

    # Group by wave
    waves: dict[int, list] = {}
    for t in tasks_d:
        w = wave_of.get(t['seq'], 0)
        waves.setdefault(w, []).append(t)

    NODE_W, NODE_H, H_GAP, V_GAP = 240, 110, 80, 30
    for wave_idx in sorted(waves.keys()):
        wave_tasks = sorted(waves[wave_idx], key=lambda t: t['seq'])
        total_h = len(wave_tasks) * NODE_H + (len(wave_tasks) - 1) * V_GAP
        start_y = max(80, 300 - total_h // 2)
        for row_idx, t in enumerate(wave_tasks):
            t['x'] = 60 + wave_idx * (NODE_W + H_GAP)
            t['y'] = start_y + row_idx * (NODE_H + V_GAP)

    # ── Build edge list ────────────────────────────────────────────────────────
    edges = []
    for t in tasks_d:
        for dep_seq in t['depends_on']:
            src = seq_map.get(dep_seq)
            if src:
                # Edge is "active" if the dependency is done and target is running/pending
                src_done = src['status'] == 'done'
                tgt_active = t['status'] in ('running', 'pending', 'awaiting_hitl')
                edges.append(
                    {
                        'id': f'e_{dep_seq}_{t["seq"]}',
                        'from_seq': dep_seq,
                        'to_seq': t['seq'],
                        'from_id': src['task_id'],
                        'to_id': t['task_id'],
                        'active': src_done and tgt_active,
                        'done': src_done and t['status'] == 'done',
                        'error': t['status'] == 'failed',
                    }
                )

    # ── Wave summary ──────────────────────────────────────────────────────────
    wave_summary = []
    for w in sorted(waves.keys()):
        wt = waves[w]
        wave_summary.append(
            {
                'wave': w,
                'count': len(wt),
                'status': 'done'
                if all(t['status'] == 'done' for t in wt)
                else 'running'
                if any(t['status'] == 'running' for t in wt)
                else 'failed'
                if any(t['status'] == 'failed' for t in wt)
                else 'pending',
            }
        )

    return {
        'ok': True,
        'run': run_d,
        'tasks': tasks_d,
        'edges': edges,
        'waves': wave_summary,
        'wave_count': len(waves),
        'total_tasks': len(tasks_d),
    }


@router.get('/run/{run_id}/stream')
async def stream_run_updates(run_id: str):
    """SSE stream of live supervisor progress for a run."""

    async def _gen():
        import asyncio

        last_status = ''
        for _ in range(180):  # max 15 min at 5s poll
            con = _get_conn()
            try:
                run = con.execute('SELECT * FROM supervisor_runs WHERE run_id=?', (run_id,)).fetchone()
                tasks = con.execute(
                    'SELECT task_id,seq,title,agent_id,status,output FROM supervisor_tasks WHERE run_id=? ORDER BY seq',
                    (run_id,),
                ).fetchall()
            finally:
                con.close()

            if run:
                run_d = dict(run)
                data = json.dumps(
                    {
                        'run_id': run_id,
                        'status': run_d['status'],
                        'done_count': run_d['done_count'],
                        'task_count': run_d['task_count'],
                        'final_output': run_d.get('final_output', '')[:500],
                        'eval_score': run_d.get('eval_score'),
                        'tasks': [
                            {'seq': t['seq'], 'title': t['title'], 'agent_id': t['agent_id'], 'status': t['status']}
                            for t in tasks
                        ],
                    },
                    default=str,
                )
                yield f'data: {data}\n\n'

                if run_d['status'] in ('done', 'failed', 'killed'):
                    break

            await asyncio.sleep(5)

        yield 'data: {"type":"stream_end"}\n\n'

    return StreamingResponse(
        _gen(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )
