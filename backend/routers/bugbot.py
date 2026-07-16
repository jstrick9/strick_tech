"""
Agentic OS — BugBot: AI Pull Request Reviewer
Matches Cursor's BugBot feature — auto-review diffs, suggest fixes,
learn from PR feedback, post comments. ~80% issue resolution rate target.

Works with:
 - GitHub PRs (via GITHUB_TOKEN)
 - Local git diff (no token needed)
 - Manual code paste review
"""

from __future__ import annotations

import contextlib

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix='/api/bugbot', tags=['bugbot'])
log = logging.getLogger('agentic.bugbot')

from backend.config import get_data_dir
ROOT = get_data_dir()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bugbot_reviews (
    id          TEXT PRIMARY KEY,
    pr_url      TEXT DEFAULT '',
    repo        TEXT DEFAULT '',
    pr_number   INTEGER DEFAULT 0,
    title       TEXT DEFAULT '',
    diff        TEXT DEFAULT '',
    issues      TEXT DEFAULT '[]',
    fixes       TEXT DEFAULT '[]',
    severity    TEXT DEFAULT 'low',
    score       INTEGER DEFAULT 100,
    status      TEXT DEFAULT 'pending',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS bugbot_feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id   TEXT NOT NULL,
    issue_index INTEGER DEFAULT 0,
    feedback    TEXT DEFAULT 'correct',
    note        TEXT DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _ensure_schema():
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.executescript(_SCHEMA)
        con.commit()
    finally:
        con.close()


_ensure_schema()

REVIEW_SYSTEM = """You are BugBot, an expert code reviewer with the precision of a senior engineer.
Review the provided code diff and identify ALL issues across these categories:

1. 🐛 BUGS — Logic errors, off-by-one, null pointer, race conditions, type mismatches
2. 🔒 SECURITY — SQL injection, XSS, CSRF, path traversal, secret exposure, insecure deserialization
3. ⚡ PERFORMANCE — N+1 queries, blocking I/O, memory leaks, unnecessary re-renders, O(n²) loops
4. 🧹 CODE QUALITY — DRY violations, dead code, long functions, missing error handling
5. ✅ TESTS — Missing test coverage, untested edge cases, flaky test patterns
6. 📚 DOCS — Missing docstrings for public APIs, confusing variable names

For each issue return:
{
  "severity": "critical|high|medium|low",
  "category": "bug|security|performance|quality|test|docs",
  "file": "filename or 'unknown'",
  "line": line_number_or_null,
  "description": "Clear explanation of the problem",
  "fix": "Concrete code fix or recommendation",
  "confidence": 0.0-1.0
}

Return a JSON object:
{
  "issues": [...],
  "summary": "2-sentence overall assessment",
  "score": 0-100,  // code quality score
  "severity": "critical|high|medium|low",  // overall severity
  "positive_notes": ["things done well"]
}

Be thorough but focused. Only real issues, no nitpicks."""


async def _run_review(diff: str, context: str = '') -> dict:
    from ..services import llm as llm_svc

    prompt = f'{context}\n\n## Diff to Review:\n```diff\n{diff[:12000]}\n```'
    result = await llm_svc.complete(
        [{'role': 'system', 'content': REVIEW_SYSTEM}, {'role': 'user', 'content': prompt}],
        agent_id='bugbot',
        max_tokens=3000,
        temperature=0.1,
        inject_steering=False,  # prevent steering context from biasing code reviews
    )
    text = result.get('text', '')
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        with contextlib.suppress(Exception):
            return json.loads(m.group(0))
    # Fallback parse
    return {
        'issues': [],
        'summary': text[:300] if text else 'Review complete',
        'score': 75,
        'severity': 'low',
        'positive_notes': [],
    }


# ── REST endpoints ─────────────────────────────────────────────────────────────
@router.get('/reviews')
def list_reviews(limit: int = 20):
    """Retrieve and return list reviews."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT id,pr_url,title,severity,score,status,created_at FROM bugbot_reviews ORDER BY created_at DESC LIMIT ?',
            (min(limit, 100),),
        ).fetchall()
    finally:
        con.close()
    return {'reviews': [dict(r) for r in rows], 'count': len(rows)}


@router.post('/review/diff')
async def review_diff(req: Request):
    """Review a raw diff pasted directly."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    diff = (body.get('diff') or '').strip()
    context = body.get('context') or ''
    title = (body.get('title') or 'Manual Review')[:200]

    if not diff:
        return {'ok': False, 'error': 'diff required'}

    review_id = f'rev_{int(time.time() * 1000)}'
    result = await _run_review(diff, context)
    issues = result.get('issues', [])
    score = result.get('score', 75)
    severity = result.get('severity', 'low')

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'INSERT INTO bugbot_reviews(id,title,diff,issues,fixes,severity,score,status) VALUES (?,?,?,?,?,?,?,?)',
            (
                review_id,
                title,
                diff[:8000],
                json.dumps(issues),
                json.dumps([i.get('fix', '') for i in issues]),
                severity,
                score,
                'done',
            ),
        )
        con.commit()
    finally:
        con.close()

    return {
        'ok': True,
        'review_id': review_id,
        'issues': issues,
        'summary': result.get('summary', ''),
        'score': score,
        'severity': severity,
        'positives': result.get('positive_notes', []),
        'issue_count': len(issues),
    }


@router.post('/review/diff/stream')
async def review_diff_stream(req: Request):
    """Stream a review of a diff."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    diff = (body.get('diff') or '').strip()
    context = body.get('context') or ''
    title = (body.get('title') or 'Streaming Review')[:200]

    if not diff:
        return {'ok': False, 'error': 'diff required'}

    review_id = f'rev_{int(time.time() * 1000)}'

    async def _stream():
        from ..services import llm as llm_svc

        yield f'data: {json.dumps({"type": "start", "review_id": review_id})}\n\n'

        prompt = f'{context}\n\n## Diff:\n```diff\n{diff[:12000]}\n```'
        full_text = ''
        async for chunk in llm_svc.stream(
            [{'role': 'system', 'content': REVIEW_SYSTEM}, {'role': 'user', 'content': prompt}],
            agent_id='bugbot',
            max_tokens=3000,
            inject_steering=False,
        ):
            # FIX 1: parse actual text delta from SSE chunk (not raw SSE string)
            delta = ''
            try:
                if chunk.startswith('data:'):
                    delta = json.loads(chunk[5:].strip()).get('delta', '')
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass
            if delta:
                full_text += delta
                yield f'data: {json.dumps({"type": "chunk", "text": delta})}\n\n'

        # Parse result from accumulated plain text
        m = re.search(r'\{.*\}', full_text, re.DOTALL)
        parsed = {}
        if m:
            try:
                parsed = json.loads(m.group(0))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass

        issues = parsed.get('issues', [])
        score = parsed.get('score', 75)
        severity = parsed.get('severity', 'low')
        # FIX 2: save actual fixes extracted from issues (not hardcoded "[]")
        fixes = [i.get('fix', '') for i in issues]

        from ..services.memory_db import get_conn

        con = get_conn()
        try:
            con.execute(
                'INSERT INTO bugbot_reviews(id,title,diff,issues,fixes,severity,score,status) VALUES (?,?,?,?,?,?,?,?)',
                (review_id, title, diff[:8000], json.dumps(issues), json.dumps(fixes), severity, score, 'done'),
            )
            con.commit()
        finally:
            con.close()

        yield f'data: {json.dumps({"type": "done", "review_id": review_id, "issues": issues, "score": score, "severity": severity, "summary": parsed.get("summary", "")})}\n\n'

    return StreamingResponse(
        _stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@router.post('/review/git')
async def review_git_diff(req: Request):
    """Review the current local git diff (unstaged or staged)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    staged = body.get('staged', False)
    branch = body.get('branch', '')

    try:
        cmd = ['git', 'diff']
        if staged:
            cmd.append('--cached')
        if branch:
            cmd.append(branch)

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=10)
        diff = result.stdout.strip()

        if not diff:
            diff = subprocess.run(
                ['git', 'diff', 'HEAD~1', 'HEAD'], capture_output=True, text=True, cwd=str(ROOT), timeout=10
            ).stdout.strip()

        if not diff:
            return {'ok': False, 'error': 'No changes to review (no diff found)'}
    except Exception as ex:
        return {'ok': False, 'error': f'git error: {ex}'}

    review_id = f'rev_{int(time.time() * 1000)}'
    review = await _run_review(diff, f'Git diff from {ROOT.name}')
    issues = review.get('issues', [])

    # FIX 3: include fixes column (was missing from git review INSERT)
    fixes_git = [i.get('fix', '') for i in issues]
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'INSERT INTO bugbot_reviews(id,title,diff,issues,fixes,severity,score,status) VALUES (?,?,?,?,?,?,?,?)',
            (
                review_id,
                f'git diff {branch or "HEAD"}',
                diff[:8000],
                json.dumps(issues),
                json.dumps(fixes_git),
                review.get('severity', 'low'),
                review.get('score', 75),
                'done',
            ),
        )
        con.commit()
    finally:
        con.close()

    return {
        'ok': True,
        'review_id': review_id,
        'diff_lines': len(diff.splitlines()),
        'issues': issues,
        'summary': review.get('summary', ''),
        'score': review.get('score', 75),
        'severity': review.get('severity', 'low'),
        'positives': review.get('positive_notes', []),
    }


@router.post('/review/github-pr')
async def review_github_pr(req: Request):
    """Fetch and review a GitHub PR diff."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    pr_url = (body.get('pr_url') or '').strip()
    auto_post = body.get('auto_post_comment', False)

    # Parse owner/repo/PR number from URL
    m = re.search(r'github\.com/([^/]+)/([^/]+)/pull/(\d+)', pr_url)
    if not m:
        return {'ok': False, 'error': 'Invalid GitHub PR URL. Expected: https://github.com/owner/repo/pull/123'}

    owner, repo, pr_num = m.group(1), m.group(2), int(m.group(3))
    token = os.getenv('GITHUB_TOKEN', '')

    import httpx

    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = f'Bearer {token}'

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Get PR metadata
            pr_r = await client.get(f'https://api.github.com/repos/{owner}/{repo}/pulls/{pr_num}', headers=headers)
            # FIX 8: check HTTP status before proceeding
            if pr_r.status_code == 401:
                return {'ok': False, 'error': 'GitHub authentication failed. Set GITHUB_TOKEN in Settings → API Keys.'}
            if pr_r.status_code == 403:
                return {
                    'ok': False,
                    'error': 'GitHub rate limit exceeded or insufficient permissions. Add a GITHUB_TOKEN.',
                }
            if pr_r.status_code == 404:
                return {
                    'ok': False,
                    'error': f'PR not found: {pr_url}. Check the URL and ensure the repo is accessible.',
                }
            if pr_r.status_code >= 400:
                return {'ok': False, 'error': f'GitHub API error {pr_r.status_code}: {pr_r.text[:200]}'}
            pr_data = pr_r.json()

            # Get PR diff
            diff_r = await client.get(
                f'https://api.github.com/repos/{owner}/{repo}/pulls/{pr_num}',
                headers={**headers, 'Accept': 'application/vnd.github.diff'},
            )
            if diff_r.status_code >= 400:
                return {'ok': False, 'error': f'Could not fetch PR diff (HTTP {diff_r.status_code})'}
            diff = diff_r.text
    except Exception as ex:
        return {'ok': False, 'error': f'GitHub API error: {ex}'}

    pr_title = pr_data.get('title', '')
    context = (
        f'PR #{pr_num}: {pr_title}\nRepo: {owner}/{repo}\nAuthor: {pr_data.get("user", {}).get("login", "unknown")}'
    )

    review_id = f'rev_gh_{pr_num}_{int(time.time())}'
    review = await _run_review(diff, context)
    issues = review.get('issues', [])

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'INSERT INTO bugbot_reviews(id,pr_url,repo,pr_number,title,diff,issues,severity,score,status) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (
                review_id,
                pr_url,
                f'{owner}/{repo}',
                pr_num,
                pr_title,
                diff[:8000],
                json.dumps(issues),
                review.get('severity', 'low'),
                review.get('score', 75),
                'done',
            ),
        )
        con.commit()
    finally:
        con.close()

    # Optionally post comment to GitHub PR
    comment_url = ''
    if auto_post and token and issues:
        try:
            critical = [i for i in issues if i.get('severity') in ('critical', 'high')]
            comment = _format_pr_comment(review, issues, review_id)
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f'https://api.github.com/repos/{owner}/{repo}/issues/{pr_num}/comments',
                    headers=headers,
                    json={'body': comment},
                )
                comment_url = r.json().get('html_url', '')
        except Exception as ex:
            log.warning('Could not post PR comment: %s', ex)

    return {
        'ok': True,
        'review_id': review_id,
        'pr_title': pr_title,
        'issues': issues,
        'summary': review.get('summary', ''),
        'score': review.get('score', 75),
        'severity': review.get('severity', 'low'),
        'comment_url': comment_url,
        'issue_count': len(issues),
    }


def _format_pr_comment(review: dict, issues: list, review_id: str) -> str:
    """Format a GitHub PR comment from a review."""
    score = review.get('score', 75)
    severity = review.get('severity', 'low')
    emoji = {'critical': '🚨', 'high': '⚠️', 'medium': '⚡', 'low': '✅'}.get(severity, 'ℹ️')

    lines = [
        f'## {emoji} BugBot Review — Score: {score}/100',
        '',
        f'> {review.get("summary", "")}',
        '',
    ]

    if issues:
        by_sev: dict[str, list] = {}
        for i in issues:
            by_sev.setdefault(i.get('severity', 'low'), []).append(i)

        for sev in ['critical', 'high', 'medium', 'low']:
            if sev not in by_sev:
                continue
            sev_emoji = {'critical': '🚨', 'high': '⚠️', 'medium': '⚡', 'low': '💡'}[sev]
            lines.append(f'### {sev_emoji} {sev.title()} Issues')
            for iss in by_sev[sev]:
                loc = f'`{iss.get("file", "")}:{iss.get("line", "")}` — ' if iss.get('file') else ''
                lines.append(f'- **{iss.get("category", "").upper()}** {loc}{iss.get("description", "")}')
                if iss.get('fix'):
                    lines.append(f'  - **Fix:** {iss["fix"]}')
            lines.append('')

    positives = review.get('positive_notes', [])
    if positives:
        lines.append('### ✅ Looks Good')
        for p in positives:
            lines.append(f'- {p}')

    lines.append(f'\n*Generated by Agentic OS BugBot · Review ID: `{review_id}`*')
    return '\n'.join(lines)


@router.get('/reviews/{review_id}')
def get_review(review_id: str):
    """Retrieve and return get review."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute('SELECT * FROM bugbot_reviews WHERE id=?', (review_id,)).fetchone()
        fb = con.execute(
            'SELECT * FROM bugbot_feedback WHERE review_id=? ORDER BY created_at DESC', (review_id,)
        ).fetchall()
    finally:
        con.close()
    if not row:
        return {'ok': False, 'error': 'Not found'}
    d = dict(row)
    d['issues'] = json.loads(d.get('issues', '[]') or '[]')
    d['fixes'] = json.loads(d.get('fixes', '[]') or '[]')
    d['feedback'] = [dict(f) for f in fb]
    return d


@router.post('/reviews/{review_id}/feedback')
async def submit_feedback(review_id: str, req: Request):
    """Submit feedback on a BugBot review (helps it learn)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    issue_idx = int(body.get('issue_index', 0))
    feedback = body.get('feedback', 'correct')  # correct|wrong|helpful|not_helpful
    note = (body.get('note', ''))[:500]

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'INSERT INTO bugbot_feedback(review_id,issue_index,feedback,note) VALUES (?,?,?,?)',
            (review_id, issue_idx, feedback, note),
        )
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@router.post('/review/file')
async def review_file(req: Request):
    """Review a single file's content for issues."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    content = (body.get('content') or '').strip()
    filename = body.get('filename', 'unknown')
    if not content:
        return {'ok': False, 'error': 'content required'}

    # Format as a fake diff for the reviewer
    diff = f'+++ b/{filename}\n' + '\n'.join(f'+{line}' for line in content.splitlines())
    review_id = f'rev_{int(time.time() * 1000)}'
    review = await _run_review(diff, f'Full file review: {filename}')
    issues = review.get('issues', [])

    return {
        'ok': True,
        'review_id': review_id,
        'filename': filename,
        'issues': issues,
        'summary': review.get('summary', ''),
        'score': review.get('score', 75),
        'positives': review.get('positive_notes', []),
    }


@router.get('/stats')
def bugbot_stats():
    """Execute or process bugbot stats operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        total = con.execute('SELECT COUNT(*) FROM bugbot_reviews').fetchone()[0]
        avg_score = con.execute('SELECT AVG(score) FROM bugbot_reviews').fetchone()[0]
        by_severity = con.execute('SELECT severity,COUNT(*) as c FROM bugbot_reviews GROUP BY severity').fetchall()
        total_issues = con.execute('SELECT SUM(json_array_length(issues)) FROM bugbot_reviews').fetchone()[0]
    finally:
        con.close()
    return {
        'total_reviews': total,
        'avg_score': round(avg_score or 0, 1),
        'by_severity': {r['severity']: r['c'] for r in by_severity},
        'total_issues_found': total_issues or 0,
    }
