"""
Agentic OS — Natural Language Git + AI Changelog + Dependency Auditor + Security Scanner

Natural Language Git: "revert the auth changes from yesterday", "show what changed in last 3 commits",
"create a branch for the new payment feature", "merge the feature branch"

AI Changelog: Automatic CHANGELOG.md generation from git history

Dependency Auditor: Safe package upgrade scanner (requirements.txt + package.json)

Security Scanner: OWASP Top 10, secret detection, SQL injection, XSS, path traversal
"""

from __future__ import annotations

import contextlib

import json
import logging
import re
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/gitai', tags=['gitai'])
log = logging.getLogger('agentic.gitai')

from backend.config import get_data_dir
ROOT = get_data_dir()
PREVIEW_DIR = ROOT / 'preview'  # FIX 2: define PREVIEW_DIR for security scanner


def _git(args: list[str], cwd=None) -> tuple[str, str, int]:
    """Run a git command. Returns (stdout, stderr, returncode)."""
    try:
        r = subprocess.run(['git'] + args, capture_output=True, text=True, cwd=str(cwd or ROOT), timeout=15)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except Exception as ex:
        return '', str(ex), 1


# ══════════════════════════════════════════════════════════════════
#  NATURAL LANGUAGE GIT
# ══════════════════════════════════════════════════════════════════


@router.post('/nl-git')
async def natural_language_git(req: Request):
    """
    Parse a natural language git command and execute it safely.
    Examples:
      "show what changed in the last 3 commits"
      "create a branch called feature/payments"
      "revert the last commit"
      "show me the git log for index.html"
      "what files were changed yesterday?"
      "stage all Python files"
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    query = (body.get('query') or '').strip()
    dry_run = body.get('dry_run', True)  # default safe: show command before running

    if not query:
        return {'ok': False, 'error': 'query required'}

    from ..services import llm as llm_svc

    parse_prompt = f"""You are a Git expert. Convert this natural language request into git commands.

Request: {query}

Return a JSON object:
{{
  "commands": [
    {{"cmd": ["git", "log", "--oneline", "-10"], "description": "Show last 10 commits", "safe": true}},
    ...
  ],
  "explanation": "What this will do in plain English",
  "warnings": ["any risks or irreversible actions to warn about"],
  "is_destructive": false
}}

Rules:
- "safe": true for read-only commands (log, diff, status, show)
- "safe": false for write commands (commit, push, reset, revert, merge, branch -d)
- Always use specific flags (e.g. "git reset --soft" not bare "git reset")
- Break complex operations into multiple safe steps
- Return ONLY valid JSON."""

    result = await llm_svc.complete(
        [{'role': 'user', 'content': parse_prompt}],
        agent_id='gitai',
        max_tokens=800,
        temperature=0.1,
        inject_steering=False,
    )
    text = result.get('text', '')

    parsed = {}
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        with contextlib.suppress(Exception):
            parsed = json.loads(m.group(0))

    if not parsed:
        return {'ok': False, 'error': 'Could not parse git command from query', 'raw': text[:200]}

    commands = parsed.get('commands', [])
    is_dest = parsed.get('is_destructive', False)
    warnings = parsed.get('warnings', [])
    explanation = parsed.get('explanation', '')

    # If dry_run or destructive, just return the plan
    if dry_run or is_dest:
        return {
            'ok': True,
            'dry_run': True,
            'query': query,
            'explanation': explanation,
            'commands': commands,
            'warnings': warnings,
            'is_destructive': is_dest,
            'note': 'Set dry_run=false to execute (not recommended for destructive ops)',
        }

    # Execute safe commands
    results = []
    for cmd_info in commands:
        cmd = cmd_info.get('cmd', [])
        safe = cmd_info.get('safe', True)
        if not cmd or cmd[0] != 'git':
            continue
        if not safe and not body.get('allow_unsafe', False):
            results.append(
                {'cmd': ' '.join(cmd), 'skipped': True, 'reason': 'Unsafe command skipped (set allow_unsafe=true)'}
            )
            continue
        stdout, stderr, code = _git(cmd[1:])
        results.append(
            {
                'cmd': ' '.join(cmd),
                'stdout': stdout[:2000],
                'stderr': stderr[:500] if stderr else '',
                'code': code,
                'ok': code == 0,
            }
        )

    return {
        'ok': True,
        'query': query,
        'explanation': explanation,
        'executed': len(results),
        'results': results,
        'warnings': warnings,
    }


@router.get('/status')
def git_status():
    """Get current git status."""
    stdout, stderr, code = _git(['status', '--porcelain'])
    branch_out, _, _ = _git(['branch', '--show-current'])
    log_out, _, _ = _git(['log', '--oneline', '-5'])

    changed = []
    for line in stdout.splitlines():
        if len(line) >= 3:
            status = line[:2].strip()
            path = line[3:].strip()
            changed.append({'status': status, 'path': path})

    return {
        'branch': branch_out,
        'changed_files': changed,
        'changed_count': len(changed),
        'recent_commits': log_out.splitlines(),
        'clean': len(changed) == 0,
    }


@router.get('/log')
def git_log(limit: int = 20, file: str = '', since: str = '', author: str = ''):
    """Get git log with optional filters."""
    args = ['log', '--pretty=format:%H|%an|%ae|%ad|%s', '--date=short', f'-{min(limit, 100)}']
    if file:
        args += ['--', '' + file]
    if since:
        args += [f'--since={since}']
    if author:
        args += [f'--author={author}']

    stdout, _, _ = _git(args)
    commits = []
    for line in stdout.splitlines():
        parts = line.split('|', 4)
        if len(parts) >= 5:
            commits.append(
                {
                    'hash': parts[0][:8],
                    'full_hash': parts[0],
                    'author': parts[1],
                    'email': parts[2],
                    'date': parts[3],
                    'message': parts[4],
                }
            )
    return {'commits': commits, 'count': len(commits)}


@router.get('/diff')
def git_diff(ref: str = '', staged: bool = False, file: str = ''):
    """Get git diff."""
    args = ['diff']
    if staged:
        args.append('--cached')
    if ref:
        args.append(ref)
    if file:
        args += ['--', file]

    stdout, _, _ = _git(args)
    return {'diff': stdout[:20000], 'lines': len(stdout.splitlines())}


@router.post('/commit')
async def ai_commit(req: Request):
    """Generate an AI commit message from staged changes and commit."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    auto_commit = body.get('auto_commit', False)
    extra_hint = body.get('hint', '')

    # Get staged diff
    diff, _, _ = _git(['diff', '--cached'])
    if not diff:
        # Try unstaged
        diff, _, _ = _git(['diff'])
    if not diff:
        return {'ok': False, 'error': 'No changes to commit'}

    from ..services import llm as llm_svc

    prompt = f"""Generate a concise, descriptive git commit message for this diff.

{f'Hint from developer: {extra_hint}' if extra_hint else ''}

Diff:
```diff
{diff[:6000]}
```

Format: <type>(<scope>): <description>
Types: feat|fix|refactor|docs|test|chore|perf|style|ci

Rules:
- Subject line max 72 chars
- Use imperative mood ("add" not "added")
- Be specific about what changed

Return ONLY the commit message, no explanation."""

    result = await llm_svc.complete(
        [{'role': 'user', 'content': prompt}], agent_id='gitai', max_tokens=200, temperature=0.3, inject_steering=False
    )
    message = result.get('text', '').strip().split('\n')[0][:200]

    if auto_commit and message:
        # Stage all and commit
        _git(['add', '-A'])
        stdout, stderr, code = _git(['commit', '-m', message])
        return {'ok': code == 0, 'message': message, 'committed': True, 'output': stdout}

    return {'ok': True, 'message': message, 'committed': False}


# ══════════════════════════════════════════════════════════════════
#  AI CHANGELOG GENERATOR
# ══════════════════════════════════════════════════════════════════


@router.post('/changelog')
async def generate_changelog(req: Request):
    """Generate/update CHANGELOG.md from git history."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    since = body.get('since', '')  # tag or date: "v1.0.0" or "2025-01-01"
    version = body.get('version', '')  # new version to add
    limit = min(int(body.get('limit', 50)), 200)

    # Get recent commits
    args = ['log', '--pretty=format:%H|%ad|%an|%s', '--date=short']
    if since:
        args.append(f'--since={since}' if '-' in since else f'{since}..HEAD')
    args.append(f'-{limit}')
    stdout, _, _ = _git(args)

    commits = []
    for line in stdout.splitlines():
        parts = line.split('|', 3)
        if len(parts) >= 4:
            commits.append({'hash': parts[0][:8], 'date': parts[1], 'author': parts[2], 'msg': parts[3]})

    if not commits:
        return {'ok': False, 'error': 'No commits found in range'}

    from ..services import llm as llm_svc

    commit_text = '\n'.join(f'- {c["date"]} [{c["hash"]}] {c["msg"]} ({c["author"]})' for c in commits)

    prompt = f"""Generate a professional CHANGELOG.md entry from these git commits.

Version: {version or 'Unreleased'}
Date: {time.strftime('%Y-%m-%d')}

Commits:
{commit_text[:5000]}

Follow Keep a Changelog format (https://keepachangelog.com):
## [version] - date

### Added
- ...

### Changed
- ...

### Fixed
- ...

### Removed
- ...

### Security
- ...

Group commits intelligently. Skip trivial commits (typos, whitespace).
Return only the markdown changelog section."""

    result = await llm_svc.complete(
        [{'role': 'user', 'content': prompt}], agent_id='gitai', max_tokens=1500, temperature=0.3, inject_steering=False
    )
    changelog_entry = result.get('text', '').strip()

    # Update or create CHANGELOG.md
    changelog_path = ROOT / 'CHANGELOG.md'
    if changelog_path.exists():
        existing = changelog_path.read_text(encoding='utf-8')
        # Insert after first heading
        if '## [' in existing:
            # Find insertion point after header
            insert_at = existing.find('## [')
            new_content = existing[:insert_at] + changelog_entry + '\n\n' + existing[insert_at:]
        else:
            new_content = existing + '\n\n' + changelog_entry
    else:
        new_content = f'# Changelog\n\nAll notable changes to Agentic OS.\n\n{changelog_entry}'

    changelog_path.write_text(new_content, encoding='utf-8')

    return {
        'ok': True,
        'version': version or 'Unreleased',
        'commits_used': len(commits),
        'entry': changelog_entry,
        'changelog_path': str(changelog_path.relative_to(ROOT)),
    }


# ══════════════════════════════════════════════════════════════════
#  DEPENDENCY AUDITOR
# ══════════════════════════════════════════════════════════════════


@router.get('/deps/audit')
async def dependency_audit():
    """Scan requirements.txt and package.json for outdated/vulnerable packages."""
    from ..services import llm as llm_svc

    findings: list[dict] = []
    package_lists: dict = {}

    # Python requirements
    req_file = ROOT / 'requirements.txt'
    if req_file.exists():
        content = req_file.read_text(encoding='utf-8')
        pinned = re.findall(r'^([a-zA-Z][a-zA-Z0-9_-]*)==([\d.]+)', content, re.MULTILINE)
        package_lists['python'] = [{'name': n, 'version': v} for n, v in pinned]

    # Node packages
    pkg_file = ROOT / 'package.json'
    if pkg_file.exists():
        try:
            pkg = json.loads(pkg_file.read_text())
            node_deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
            package_lists['node'] = [{'name': k, 'version': v.lstrip('^~')} for k, v in node_deps.items()]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass

    if not package_lists:
        return {'ok': False, 'error': 'No requirements.txt or package.json found'}

    # AI analysis
    pkg_summary = json.dumps(package_lists, indent=2)[:3000]
    prompt = f"""Analyze these dependencies for security and maintenance issues.

Packages:
{pkg_summary}

For each package with known issues, return:
{{
  "findings": [
    {{
      "name": "package_name",
      "current_version": "x.y.z",
      "latest_version": "x.y.z or unknown",
      "severity": "critical|high|medium|low|info",
      "issue_type": "vulnerability|outdated|deprecated|maintenance",
      "description": "specific issue description",
      "recommendation": "upgrade to x.y.z" or "replace with..."
    }}
  ],
  "summary": "overall dependency health",
  "upgrade_commands": {{
    "python": "pip install --upgrade ...",
    "node": "npm update ..."
  }}
}}

Be specific about known CVEs or major version differences.
Return ONLY valid JSON."""

    result = await llm_svc.complete(
        [{'role': 'user', 'content': prompt}], agent_id='gitai', max_tokens=2000, temperature=0.1, inject_steering=False
    )
    text = result.get('text', '')
    m = re.search(r'\{.*\}', text, re.DOTALL)
    audit_result = {}
    if m:
        with contextlib.suppress(Exception):
            audit_result = json.loads(m.group(0))

    findings = audit_result.get('findings', [])
    return {
        'ok': True,
        'findings': findings,
        'summary': audit_result.get('summary', ''),
        'upgrade_commands': audit_result.get('upgrade_commands', {}),
        'packages_scanned': sum(len(v) for v in package_lists.values()),
        'issues_found': len(findings),
        'critical_count': len([f for f in findings if f.get('severity') == 'critical']),
    }


@router.post('/deps/upgrade')
async def apply_dep_upgrade(req: Request):
    """Apply a specific package upgrade to requirements.txt."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    package = body.get('package', '')
    version = body.get('version', '')
    eco = body.get('ecosystem', 'python')  # python|node

    if not package or not version:
        return {'ok': False, 'error': 'package and version required'}

    if eco == 'python':
        req_file = ROOT / 'requirements.txt'
        if not req_file.exists():
            return {'ok': False, 'error': 'requirements.txt not found'}
        content = req_file.read_text()
        new_content = re.sub(rf'^({re.escape(package)})==[^\s]+', f'{package}=={version}', content, flags=re.MULTILINE)
        if new_content == content:
            return {'ok': False, 'error': f'Package {package} not found in requirements.txt'}
        req_file.write_text(new_content)
        return {'ok': True, 'package': package, 'version': version, 'file': 'requirements.txt'}

    elif eco == 'node':
        pkg_file = ROOT / 'package.json'
        if not pkg_file.exists():
            return {'ok': False, 'error': 'package.json not found'}
        pkg = json.loads(pkg_file.read_text())
        found = False
        for section in ('dependencies', 'devDependencies'):
            if package in pkg.get(section, {}):
                pkg[section][package] = f'^{version}'
                found = True
        if not found:
            return {'ok': False, 'error': f'Package {package} not found in package.json'}
        pkg_file.write_text(json.dumps(pkg, indent=2))
        return {'ok': True, 'package': package, 'version': version, 'file': 'package.json'}

    return {'ok': False, 'error': "ecosystem must be 'python' or 'node'"}


# ══════════════════════════════════════════════════════════════════
#  SECURITY SCANNER
# ══════════════════════════════════════════════════════════════════

# OWASP Top 10 patterns
SECURITY_RULES = [
    # A01: Broken Access Control
    {
        'id': 'A01',
        'name': 'Missing Auth Check',
        'pattern': r"@app\.(get|post|put|delete)\(['\"](?!/api/auth).*['\"\)]\)\s*\nasync def [^(]+\([^)]*\):",
        'desc': 'API endpoint may be missing authentication',
        'severity': 'high',
        'category': 'access_control',
    },
    # A02: Cryptographic Failures
    {
        'id': 'A02-1',
        'name': 'Weak Hash (MD5)',
        'pattern': r'md5\(|hashlib\.md5',
        'desc': 'MD5 is cryptographically broken',
        'severity': 'high',
        'category': 'crypto',
    },
    {
        'id': 'A02-2',
        'name': 'Weak Hash (SHA1)',
        'pattern': r'sha1\(|hashlib\.sha1',
        'desc': 'SHA1 is considered weak for security use',
        'severity': 'medium',
        'category': 'crypto',
    },
    {
        'id': 'A02-3',
        'name': 'Hardcoded Secret',
        'pattern': r'(?i)(password|secret|api_key|token)\s*=\s*["\'][^"\']{8,}["\']',
        'desc': 'Hardcoded credentials detected',
        'severity': 'critical',
        'category': 'crypto',
    },
    # A03: Injection
    {
        'id': 'A03-1',
        'name': 'SQL Injection Risk',
        'pattern': r'(?i)(execute|cursor\.execute)\s*\(\s*f["\'].*{',
        'desc': 'f-string SQL query may allow injection',
        'severity': 'critical',
        'category': 'injection',
    },
    {
        'id': 'A03-2',
        'name': 'Shell Injection Risk',
        'pattern': r'subprocess\.(run|Popen|call)\(.*shell=True',
        'desc': 'shell=True with user input risks command injection',
        'severity': 'high',
        'category': 'injection',
    },
    {
        'id': 'A03-3',
        'name': 'XSS Risk',
        'pattern': r'innerHTML\s*[+]?=\s*(?!.*escHtml)[^;]+(?:user|input|param|query)',
        'desc': 'innerHTML with unescaped user input may allow XSS',
        'severity': 'high',
        'category': 'injection',
    },
    # A04: Insecure Design
    {
        'id': 'A04',
        'name': 'Debug Mode',
        'pattern': r'debug\s*=\s*True|DEBUG\s*=\s*True',
        'desc': 'Debug mode should not be enabled in production',
        'severity': 'medium',
        'category': 'design',
    },
    # A05: Security Misconfiguration
    {
        'id': 'A05-1',
        'name': 'CORS Wildcard',
        'pattern': r'allow_origins.*\[.*\"\*\"|CORSMiddleware.*origins.*\*',
        'desc': 'Wildcard CORS allows any origin — restrict in production',
        'severity': 'medium',
        'category': 'misconfig',
    },
    {
        'id': 'A05-2',
        'name': 'No Rate Limiting',
        'pattern': r'@app\.(post|put)\(["\']',
        'desc': 'Consider adding rate limiting to mutation endpoints',
        'severity': 'low',
        'category': 'misconfig',
    },
    # A07: Authentication Failures
    {
        'id': 'A07',
        'name': 'Plain Text Password',
        'pattern': r'password\s*=\s*request|password\s*=\s*body',
        'desc': 'Ensure passwords are never stored or logged as plaintext',
        'severity': 'high',
        'category': 'auth',
    },
    # A09: Logging Failures
    {
        'id': 'A09',
        'name': 'Sensitive Data in Logs',
        'pattern': r'log\.(info|debug|warning)\(.*(?:password|token|secret|key)',
        'desc': 'Sensitive data may be logged',
        'severity': 'medium',
        'category': 'logging',
    },
    # A10: SSRF
    {
        'id': 'A10',
        'name': 'SSRF Risk',
        'pattern': r'httpx\.get\(.*(?:url|endpoint|target)|requests\.get\(.*(?:url|endpoint)',
        'desc': 'Dynamic URLs from user input may allow SSRF',
        'severity': 'high',
        'category': 'ssrf',
    },
]


@router.post('/security/scan')
async def security_scan(req: Request):
    """
    OWASP Top 10 security scan across all project files.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    target = body.get('target', 'all')  # all|preview|backend
    max_files = min(int(body.get('max_files', 100)), 200)

    scan_dirs = []
    if target in ('all', 'backend'):
        scan_dirs.append(ROOT / 'backend')
    if target in ('all', 'preview'):
        scan_dirs.append(PREVIEW_DIR)

    vulnerabilities: list[dict] = []
    files_scanned = 0

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for f in list(scan_dir.rglob('*'))[:max_files]:
            if not f.is_file() or f.suffix not in ('.py', '.js', '.ts', '.jsx', '.tsx', '.html'):
                continue
            if '__pycache__' in str(f):
                continue
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
                rel = str(f.relative_to(ROOT))
                files_scanned += 1

                for rule in SECURITY_RULES:
                    m = re.search(rule['pattern'], content, re.MULTILINE | re.IGNORECASE)
                    if m:
                        line_no = content[: m.start()].count('\n') + 1
                        vulnerabilities.append(
                            {
                                'rule_id': rule['id'],
                                'name': rule['name'],
                                'severity': rule['severity'],
                                'category': rule['category'],
                                'file': rel,
                                'line': line_no,
                                'description': rule['desc'],
                                'match': m.group(0)[:100],
                            }
                        )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass

    # Deduplicate by file+rule
    seen = set()
    unique_vulns = []
    for v in vulnerabilities:
        key = f'{v["rule_id"]}:{v["file"]}'
        if key not in seen:
            seen.add(key)
            unique_vulns.append(v)

    # Summary by severity
    by_sev: dict[str, int] = {}
    for v in unique_vulns:
        by_sev[v['severity']] = by_sev.get(v['severity'], 0) + 1

    score = max(
        0,
        100
        - by_sev.get('critical', 0) * 20
        - by_sev.get('high', 0) * 10
        - by_sev.get('medium', 0) * 5
        - by_sev.get('low', 0) * 2,
    )

    return {
        'ok': True,
        'vulnerabilities': unique_vulns,
        'files_scanned': files_scanned,
        'total_findings': len(unique_vulns),
        'by_severity': by_sev,
        'security_score': score,
        'grade': 'A' if score >= 90 else 'B' if score >= 80 else 'C' if score >= 70 else 'D' if score >= 60 else 'F',
        'owasp_summary': _owasp_summary(unique_vulns),
    }


def _owasp_summary(vulns: list[dict]) -> dict:
    cats: dict[str, int] = {}
    for v in vulns:
        cat = v.get('category', 'other')
        cats[cat] = cats.get(cat, 0) + 1
    return cats


@router.get('/security/rules')
def security_rules():
    """Execute or process security rules operation."""
    return {'rules': SECURITY_RULES, 'count': len(SECURITY_RULES)}


@router.post('/security/scan/file')
async def scan_file(req: Request):
    """Scan a single file for security issues."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    content = (body.get('content') or '').strip()
    filename = body.get('filename', 'unknown')

    vulns = []
    for rule in SECURITY_RULES:
        m = re.search(rule['pattern'], content, re.MULTILINE | re.IGNORECASE)
        if m:
            line_no = content[: m.start()].count('\n') + 1
            vulns.append(
                {
                    'rule_id': rule['id'],
                    'name': rule['name'],
                    'severity': rule['severity'],
                    'category': rule['category'],
                    'file': filename,
                    'line': line_no,
                    'description': rule['desc'],
                }
            )

    score = max(0, 100 - sum({'critical': 20, 'high': 10, 'medium': 5, 'low': 2}.get(v['severity'], 0) for v in vulns))
    return {'ok': True, 'filename': filename, 'findings': vulns, 'count': len(vulns), 'score': score}
