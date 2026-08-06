"""
Agentic OS v6.0 — Backend Entry Point
Local-first Agentic AI Operating System
"""

from __future__ import annotations

import hmac
import logging
import os
import time as _time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# ── Load .env FIRST before any service imports ─────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / '.env', override=False)

import asyncio
import json
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocket
from starlette.websockets import WebSocketDisconnect

# Structured logging with JSON format option
_LOG_FORMAT = os.getenv('LOG_FORMAT', 'text')
if _LOG_FORMAT == 'json':
    import json as _json

    class _JSONFormatter(logging.Formatter):
        def format(self, record):
            """Execute or process format operation."""
            return _json.dumps(
                {
                    'ts': self.formatTime(record),
                    'level': record.levelname,
                    'logger': record.name,
                    'msg': record.getMessage(),
                    'module': record.module,
                    'func': record.funcName,
                }
            )

    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler()])
    for handler in logging.getLogger().handlers:
        handler.setFormatter(_JSONFormatter())
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
log = logging.getLogger('agentic.app')

# ── Services ───────────────────────────────────────────────────────────────────
from .routers.a2a import router as a2a_router
from .routers.agent_identity import router as agent_identity_router
from .routers.agent_leaderboard import router as leaderboard_router
from .routers.agents import router as agents_router
from .routers.ambient import router as ambient_router
from .routers.analytics import router as analytics_router
from .routers.arena import router as arena_router

# ── Sprint A: Governance Foundation ───────────────────────────────────────────
from .routers.audit_log import router as audit_log_router
from .routers.auth import router as auth_router
from .routers.bounty_hunter import router as bounty_hunter_router
from .routers.browser_agent import router as browser_router
from .routers.bugbot import router as bugbot_router
from .routers.builder import router as builder_router

# ── Routers ────────────────────────────────────────────────────────────────────
from .routers.chat import router as chat_router
from .routers.cluster import router as cluster_router
from .routers.codeindex import router as codeindex_router
from .routers.codesearch import router as codesearch_router
from .routers.collab import router as collab_router
from .routers.compliance import router as compliance_router
from .routers.connect_hub import router as connect_hub_router
from .routers.control_tower import router as control_tower_router
from .routers.crdt import router as crdt_router
from .routers.database import router as database_router
from .routers.deploy import router as deploy_router
from .routers.docs_center import router as docs_router
from .routers.documents import router as documents_router
from .routers.drift import router as drift_router
from .routers.e2e import router as e2e_router
from .routers.engine import router as engine_router
from .routers.evals import router as evals_router
from .routers.finetune import router as finetune_router
from .routers.fusion import router as fusion_router
from .routers.gitai import router as gitai_router
from .routers.github import router as github_router
from .routers.hierarchy import router as hierarchy_router
from .routers.hitl import router as hitl_router
from .routers.hooks import router as hooks_router
from .routers.imagegen import router as imagegen_router
from .routers.integrations import router as integrations_router
from .routers.knowledge_graph import router as knowledge_graph_router
from .routers.license import router as license_router
from .routers.loops import router as loops_router
from .routers.marketplace import router as marketplace_router
from .routers.mcp import router as mcp_router
from .routers.memory import router as memory_router
from .routers.mobile import router as mobile_router
from .routers.multifile_agent import router as composer_router
from .routers.multitab import router as multitab_router
from .routers.notifications import router as notifications_router
from .routers.observability import router as observability_router
from .routers.obsidian import router as obsidian_router
from .routers.onboarding import router as onboarding_router
from .routers.pipeline import router as pipeline_router
from .routers.plugin_hub import router as plugin_hub_router
from .routers.plugins import router as plugins_router
from .routers.pluginsdk import router as pluginsdk_router
from .routers.pqc import router as pqc_router
from .routers.profiler import router as profiler_router
from .routers.prompts import router as prompts_router
from .routers.rag import router as rag_router
from .routers.rbac import router as rbac_router
from .routers.replay import router as replay_router
from .routers.search import router as search_router
from .routers.secrets import router as secrets_router
from .routers.security import router as security_router
from .routers.sessions import router as sessions_router
from .routers.skills import router as skills_router
from .routers.specs import router as specs_router
from .routers.steering import router as steering_router
from .routers.swarm import router as swarm_router
from .routers.sync import router as sync_router
from .routers.system import router as system_router
from .routers.tasks import router as tasks_router
from .routers.tauri_build import router as tauri_router
from .routers.templates import router as templates_router
from .routers.terminal import router as terminal_router
from .routers.testgen import router as testgen_router
from .routers.tts import router as tts_router
from .routers.userprofile import router as userprofile_router
from .routers.voice import router as voice_router
from .routers.webhooks import router as webhooks_router
from .routers.websearch import router as websearch_router
from .routers.websocket import router as ws_router
from .routers.workflow import router as workflow_router
from .routers.workspace_export import router as workspace_export_router
from .routers.workspaces import router as workspaces_router
from .security_auth import require_websocket_auth
from .services import runtime_topology
from .services import scheduler as sched_svc
from .services.memory_db import (
    agents_seed_defaults,
    audit_list,
    ensure_schema,
    get_conn,
)
from .version import VERSION


# ── Lifespan (startup / shutdown) ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    """Execute or process lifespan operation."""
    log.info('Agentic OS %s starting…', VERSION)
    ensure_schema()
    agents_seed_defaults()
    # Inject vault secrets into env
    try:
        from .routers.secrets import _inject_to_env

        _inject_to_env()
        log.info('Vault secrets injected into env')
    except Exception as e:
        log.warning('Vault inject failed: %s', e)
    # Reconcile supervisor runs orphaned by the previous shutdown. These
    # execute as in-process asyncio tasks, so anything in flight when the
    # server stopped would otherwise stay 'running' in the database forever.
    try:
        from .routers.supervisor import reconcile_orphaned_runs

        orphaned = reconcile_orphaned_runs()
        if orphaned:
            log.info('Reconciled %d supervisor run(s) orphaned by a restart', orphaned)
    except Exception as e:
        log.warning('Supervisor reconciliation failed: %s', e)
    # Start autonomous scheduler
    try:
        sched_svc.start()
        log.info('Autonomous scheduler started')
    except Exception as e:
        log.warning('Scheduler failed: %s', e)
    # Rate limiting and CSRF tokens are per-process state. Under multiple
    # workers the first degrades silently (effective limit becomes
    # workers x configured) and the second breaks outright once enforcement is
    # on. An operator who scales out should learn that at startup, not from a
    # support ticket, so name the concrete consequences here.
    runtime_topology.warn_if_multiprocess(
        rate_limit_max=_RATE_LIMIT_MAX,
        csrf_strict=_CSRF_STRICT,
    )
    log.info(
        'CSRF enforcement: %s (AGENTIC_CSRF_STRICT=%s)',
        'ON' if _CSRF_STRICT else 'OFF',
        os.getenv('AGENTIC_CSRF_STRICT', '<unset — defaults to ON in every topology>'),
    )
    log.info('Agentic OS ready → http://localhost:%s', os.getenv('AGENTIC_OS_PORT', '8787'))
    yield
    # ── Shutdown ──
    log.info('Agentic OS shutting down…')
    sched_svc.stop()


# ── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title=f'Agentic OS v{VERSION}',
    description=(
        'Local-first Agentic AI Operating System.\n\n'
        '## Features\n'
        '- **Chat** — Multi-agent streaming chat with 8+ AI models\n'
        '- **Swarm** — Fan-out prompts to multiple agents, judge best response\n'
        '- **Memory Galaxy** — 3D interactive knowledge graph with hybrid search\n'
        '- **Studio** — Monaco editor + live preview + AI pair programming\n'
        '- **Voice** — 12 neural TTS voices + voice command input\n'
        '- **Browser** — Playwright-powered autonomous web browsing\n'
        '- **HITL** — Human-in-the-loop approval gates with confidence thresholds\n'
        '- **Marketplace** — Plugin packs with 37+ skills\n\n'
        '## Authentication\n'
        'This is a local-first application. API keys are stored in an encrypted vault.\n\n'
        '## Rate Limiting\n'
        '300 requests per minute per IP (5/second average).'
    ),
    version=VERSION,
    lifespan=lifespan,
    docs_url='/docs',
    redoc_url='/redoc',
    openapi_url='/api/openapi.json',
    openapi_tags=[
        {'name': 'chat', 'description': 'Multi-agent streaming chat'},
        {'name': 'agents', 'description': 'Agent CRUD and management'},
        {'name': 'swarm', 'description': 'Multi-agent fan-out and judging'},
        {'name': 'memory', 'description': 'Memory Galaxy — knowledge graph and search'},
        {'name': 'builder', 'description': 'Live app builder with Monaco editor'},
        {'name': 'secrets', 'description': 'Encrypted secrets vault'},
        {'name': 'tts', 'description': 'Text-to-speech with 12 neural voices'},
        {'name': 'voice', 'description': 'Voice commands and speech recognition'},
        {'name': 'browser', 'description': 'Autonomous web browsing agent'},
        {'name': 'hitl', 'description': 'Human-in-the-loop approval gates'},
        {'name': 'marketplace', 'description': 'Plugin marketplace with curated packs'},
        {'name': 'workflow', 'description': 'Visual workflow builder'},
        {'name': 'security', 'description': 'CSRF token management and request ID tracing'},
        {'name': 'notifications', 'description': 'System alerts, agent events, and unread counts'},
        {'name': 'search', 'description': 'Global search across navigation, agents, memory, and skills'},
        {'name': 'hierarchy', 'description': '2-Tier Information Hierarchy (Universal Context + IVREN)'},
        {'name': 'mobile', 'description': 'Mobile app bridge, manifest, and device push notifications'},
        {'name': 'sync', 'description': 'Self-hosted encrypted vault cloud synchronization (AES-256)'},
        {'name': 'rbac', 'description': 'Role-Based Access Control and fine-grained API token scoping'},
        {'name': 'cluster', 'description': 'Distributed multi-node edge device compute grid & task dispatch'},
        {'name': 'finetune', 'description': 'Local zero-shot LoRA fine-tuning engine (MLX / CUDA)'},
        {'name': 'bounty-hunter', 'description': 'Autonomous zero-day security scanner & self-patching loop'},
        {'name': 'pqc', 'description': 'SIMULATED post-quantum cryptography (demonstration only — SHA3/XOR, not ML-KEM or Dilithium; provides no confidentiality)'},
        {'name': 'system', 'description': 'System health and monitoring'},
    ],
)

_PORT = int(os.getenv('AGENTIC_OS_PORT', '8787'))
_DEFAULT_ALLOWED_ORIGINS = [
    f'http://localhost:{_PORT}',
    f'http://127.0.0.1:{_PORT}',
    'http://localhost:3000',
    'http://localhost:5173',
    'http://localhost:1420',  # Tauri dev
    'tauri://localhost',  # Tauri production
]
_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv('AGENTIC_OS_ALLOWED_ORIGINS', ','.join(_DEFAULT_ALLOWED_ORIGINS)).split(',')
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    # SECURITY FIX: Never combine allow_credentials=True with wildcard origin ("*").
    # Explicit origins are configurable for secure reverse-proxy deployments.
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


# ═══════════════════════════════════════════════════════════════
#  SECURITY MIDDLEWARE — Rate Limiting + Security Headers
# ═══════════════════════════════════════════════════════════════

# Rate limiting: track requests per IP
_rate_limit_store: dict[str, list[float]] = defaultdict(list)

# Cap on distinct client IPs tracked. The store was an unbounded defaultdict, so
# every new source address added a permanent entry -- a scan across a /16, or
# ordinary traffic on a public deployment, grows it without limit and the
# process never gives the memory back. Rate limiting is meant to protect
# against abuse, not become the thing that fails under it.
_RATE_LIMIT_MAX_CLIENTS = 10_000
_rate_limit_last_sweep = 0.0


def _sweep_rate_limit_store(now: float) -> None:
    """Drop clients with no requests inside the current window.

    Called opportunistically rather than on a timer: no background task, no
    lock, and the cost is paid by whoever happens to arrive after the interval.
    """
    global _rate_limit_last_sweep
    if now - _rate_limit_last_sweep < _RATE_LIMIT_WINDOW:
        return
    _rate_limit_last_sweep = now
    stale = [
        ip for ip, hits in _rate_limit_store.items()
        if not hits or now - hits[-1] >= _RATE_LIMIT_WINDOW
    ]
    for ip in stale:
        _rate_limit_store.pop(ip, None)
    if len(_rate_limit_store) > _RATE_LIMIT_MAX_CLIENTS:
        # Still oversized after the sweep: drop the least recently seen. Better
        # to under-limit a few clients than to exhaust memory.
        by_recency = sorted(_rate_limit_store.items(), key=lambda kv: kv[1][-1] if kv[1] else 0)
        for ip, _ in by_recency[: len(_rate_limit_store) - _RATE_LIMIT_MAX_CLIENTS]:
            _rate_limit_store.pop(ip, None)
        log.warning(
            'Rate-limit store exceeded %d clients; evicted the least recent. '
            'A shared store (Redis) is needed for multi-process deployments.',
            _RATE_LIMIT_MAX_CLIENTS,
        )
# Keep middleware behavior aligned with the validated configuration surface so
# local deployments and test environments can tune the limit without changing
# application code. Invalid values fall back to the documented defaults.
try:
    _RATE_LIMIT_WINDOW = max(10, int(os.getenv('RATE_LIMIT_WINDOW', '60')))
except (TypeError, ValueError):
    _RATE_LIMIT_WINDOW = 60
# ── CSRF configuration ─────────────────────────────────────────────────────────
# DEFAULT: ON. This was off during the rollout that introduced client-side token
# attachment, so an upgrade could not break scripted API clients without warning.
# "Off by default" is a migration state, not an end state -- left indefinitely it
# means the protection ships disabled and most deployments never enable it, so
# the security property only exists for operators who read release notes.
#
# The evidence for flipping it: frontend/js/00-csrf.js attaches a token to every
# same-origin mutation by wrapping window.fetch, so all 282 frontend POST call
# sites are covered automatically, including new ones. A bad token was always
# rejected; the only behaviour that changes is that a MISSING token is now
# rejected too.
#
# Escape hatch: AGENTIC_CSRF_STRICT=0 restores the permissive behaviour for a
# deployment with scripted clients that cannot yet fetch a token.
#
# SAFETY GATE -- multiple workers. The token store (_CSRF_TOKENS in
# routers/security.py) is a per-process dict, so a token minted by one worker is
# unknown to the others. Measured on this codebase with --workers 4 and
# enforcement on: of 60 POSTs carrying a VALID token, 27 succeeded and 33
# returned 403. Turning this on by default in that topology would be a
# self-inflicted outage, so the default yields to detection. An explicit
# AGENTIC_CSRF_STRICT=1 is still honoured -- an operator who insists is allowed
# to, and is warned loudly at startup.
_csrf_strict_env = os.getenv('AGENTIC_CSRF_STRICT', '').strip().lower()
if _csrf_strict_env in ('1', 'true', 'yes', 'on'):
    _CSRF_STRICT = True
elif _csrf_strict_env in ('0', 'false', 'no', 'off'):
    _CSRF_STRICT = False
else:
    # Previously `runtime_topology.csrf_strict_is_safe()`, which returned False
    # under multiple workers because the token store was per process. Tokens are
    # now stateless and signed with a shared key, so every worker accepts every
    # other worker's tokens and enforcement is safe in any topology.
    _CSRF_STRICT = True

# Endpoints that legitimately receive cross-origin POSTs and authenticate by
# other means. Webhook deliveries carry an HMAC signature (see routers/
# webhooks.py) and come from GitHub/Stripe/CI, which cannot know a CSRF token;
# requiring one would break every inbound integration. The token endpoint
# itself must be reachable to bootstrap.
_CSRF_EXEMPT = frozenset({
    '/api/security/csrf-token',
    '/api/health',
    # CSP violation reports. The BROWSER posts these itself, from its own
    # network stack, with no JavaScript involved -- so it cannot attach a CSRF
    # token and there is no way to make it. Enforcing CSRF here does not
    # protect anything; it just discards the reports.
    #
    # It did exactly that: after CSRF enforcement went on, every report was
    # answered 403 and the endpoint reported "0 violations" while the browser
    # console showed 1740. A measurement channel that silently reads zero is
    # worse than no channel, because the zero looks like good news.
    #
    # The endpoint is safe to exempt: it only appends to a bounded in-memory
    # ring buffer, returns no data to the poster, and performs no state change
    # a forged request could exploit.
    '/api/security/csp-report',
})


try:
    _RATE_LIMIT_CONFIGURED = max(10, int(os.getenv('RATE_LIMIT_MAX', '300')))
except (TypeError, ValueError):
    _RATE_LIMIT_CONFIGURED = 300

# Divide the budget across workers so the CONFIGURED ceiling is the one that
# actually applies.
#
# The counter is a per-process dict, so with N workers each one independently
# allowed the full limit and the real ceiling was N x configured. An operator
# who set RATE_LIMIT_MAX=300 and ran 4 workers got 1200 and was never told --
# the control degraded silently, which is the worst way for a limit to be
# wrong. Dividing restores the operator's intent.
#
# WHAT THIS IS AND IS NOT. Load balancers do not distribute perfectly evenly,
# so a client whose requests land disproportionately on one worker can be
# limited early. That is the conservative direction: the failure mode is "a
# heavy client is throttled slightly sooner", not "the limit does not apply".
# A shared counter (Redis) would be exact, and is still the answer for a
# deployment that needs exactness -- but it imposes an operational dependency
# on every single-process local-first user to serve a topology most of them
# never run. The trigger for revisiting is in
# docs/module-reviews/25-runtime-topology.md.
#
# A floor of 10 keeps a high worker count from producing an unusable limit.
_rate_limit_workers = runtime_topology.worker_count()
if _rate_limit_workers > 1:
    _RATE_LIMIT_MAX = max(10, _RATE_LIMIT_CONFIGURED // _rate_limit_workers)
else:
    _RATE_LIMIT_MAX = _RATE_LIMIT_CONFIGURED
# Secure deployment mode is opt-in so existing local-first usage remains
# frictionless. When enabled, every API route except health checks requires
# Authorization: Bearer $AGENTIC_OS_AUTH_TOKEN.
_SECURE_MODE = os.getenv('AGENTIC_OS_SECURE_MODE', 'false').lower() in ('1', 'true', 'yes', 'on')
_AUTH_TOKEN = os.getenv('AGENTIC_OS_AUTH_TOKEN', '')
if _SECURE_MODE and not _AUTH_TOKEN:
    raise RuntimeError('AGENTIC_OS_AUTH_TOKEN is required when AGENTIC_OS_SECURE_MODE is enabled')
_PUBLIC_SECURE_PATHS = {'/api/system/health', '/api/system/stats'}
# max requests per configured window (5/sec average by default)

# Security headers for all responses
# ── /preview/ CSP ─────────────────────────────────────────────────────────────
# CSP phase 2 dropped script-src 'unsafe-inline' from the enforcing policy.
# That was correct for the application, but the middleware applied the same
# policy to /preview/ — and /preview/ is not the application. It serves the
# HTML the user writes in Code Studio and the HTML the agent generates, and
# essentially all of it carries inline <script>.
#
# The result, verified in Chromium: an inline script in a preview document
# does not run at all.
#
#   GET /preview/csptest.html  ->  <h1> still reads "BEFORE"
#   console: Refused to execute inline script ... "script-src 'self'"
#
# So the entire Live Preview feature was silently dead for any generated page
# with script in it, which is most of them. It also broke Studio's own two
# instrumentation injections (01-app-core.js:4147 and :4923) — the ones that
# forward console output and runtime errors from the preview frame back to the
# Studio console and the "Fix with AI" error bar. Both were blocked on every
# load, so the preview console showed nothing and JS errors were never
# surfaced. Note the Report-Only policy already carried a `/preview/`
# exemption; the enforcing one never got the matching change. That is the
# "second door" pattern: a control applied at one call site while an identical
# one goes unprotected.
#
# This policy restores inline script for preview documents ONLY, and is
# tighter than the application's in the ways that matter for untrusted
# content:
#
#   • frame-ancestors 'self'   — only our own Studio may frame it.
#   • form-action 'none'       — generated markup cannot POST credentials out.
#   • object-src 'none'        — no plugin content.
#   • base-uri 'none'          — an injected <base> cannot reroute the page.
#
# The iframe additionally runs under a `sandbox` attribute (index.html:1712),
# so this is defence in depth rather than the only boundary.
PREVIEW_CSP = (
    "default-src 'self' data: blob:; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: data: "
    "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://cdn.tailwindcss.com "
    "https://unpkg.com https://cdn.monaco-editor.net; "
    "style-src 'self' 'unsafe-inline' data: https://fonts.googleapis.com "
    "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
    "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net "
    "https://cdnjs.cloudflare.com; "
    "img-src 'self' data: blob: https:; "
    "connect-src 'self' blob: data: ws: wss: https:; "
    "worker-src 'self' blob:; "
    "frame-src 'self' blob: data:;"
)


SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'SAMEORIGIN',
    'X-XSS-Protection': '1; mode=block',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    # CSP — script-src no longer carries 'unsafe-inline'.
    #
    # This was a known, documented weakness for the whole review. It could not
    # simply be dropped: the frontend rendered 1107 inline `on*=` handlers plus
    # 5 inline <script> blocks, every one of which stops working the moment the
    # directive is removed. A CSP that breaks the product gets reverted within
    # a day, so the handlers had to go first.
    #
    # They have. Phase 2 migrated all 1107 to the delegation shim
    # (frontend/js/00-delegate.js) and extracted all 5 inline blocks to
    # /static/js/. `scripts/migrate_inline_handlers.py` reports 0 remaining and
    # `scripts/lint_inline_handlers.py` keeps it that way in CI.
    #
    # What this buys, stated plainly: the platform's ~714 innerHTML assignments
    # are now backed by CSP rather than resting entirely on escHtml() at each
    # call site. Modules 10 and 17 each found a stored-XSS hole of exactly that
    # shape, which was the evidence that per-call-site escaping does not hold
    # on its own. An injected <script> or on*= attribute is now refused by the
    # browser even when a call site forgets to escape.
    #
    # style-src DELIBERATELY keeps 'unsafe-inline'. The codebase sets
    # element.style throughout and templates carry style="" attributes;
    # removing it is a separate, much larger piece of work with a far smaller
    # payoff, since a style injection cannot execute script under this policy.
    #
    # object-src and base-uri are also tightened; both are free (nothing uses
    # them) and each closes a real injection vector: <object>/<embed> can load
    # plugin content, and an injected <base> tag silently reroutes every
    # relative URL on the page, including script sources.
    'Content-Security-Policy': (
        "default-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'self'; "
        # All five CDN origins are gone: three.js, 3d-force-graph, highlight.js and
        # Monaco are vendored under frontend/vendor/ and served from /static.
        # 'self' plus five CDNs is materially weaker than 'self' -- each is an
        # origin that can execute script with full same-origin privileges, so a
        # compromise or DNS hijack of any one of them is a full application
        # compromise. It also means the product now works offline, which matters
        # for something that markets itself as a local-first agentic OS.
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; "
        "img-src 'self' data: blob: https:; "
        # BUG FIX: connect-src did not allow `blob:`, while img-src/
        # worker-src/frame-src all explicitly did. Image Generator's
        # "Save to Gallery" button calls `fetch(src)` to re-fetch an
        # AI-generated image's blob: URL for re-upload (needed because SVG
        # placeholders and Style Transfer results are both returned as
        # in-memory Blobs, not server-hosted files) — that fetch() was
        # silently blocked by CSP ("Refused to connect... violates the
        # document's Content Security Policy"), so Save to Gallery never
        # worked whenever an image came from a blob: URL, which is the
        # common case with no OPENROUTER_API_KEY configured. Reproduced
        # live and confirmed fixed by adding `blob:` here to match the
        # other three directives that already allow it.
        # BUG FIX: `https://jira.*.atlassian.net` is not a legal CSP
        # host-source. The grammar allows a wildcard ONLY as the entire
        # leftmost label (`*.atlassian.net`); it cannot appear inside a
        # label or after one. Chromium rejected the whole source and
        # logged, on every single page load:
        #   "The source list for the Content Security Policy directive
        #    'connect-src' contains an invalid source:
        #    'https://jira.*.atlassian.net'. It will be ignored."
        # Observed live in Chromium via the browser console. Two
        # consequences: every Jira connector call from the browser was
        # blocked by connect-src regardless of the host, because the
        # allowance never took effect; and the console noise trained
        # anyone debugging to ignore CSP errors. Corrected to the legal
        # form, which covers jira.<site>.atlassian.net as intended.
        # TIGHTENED. This listed nine external origins -- api.github.com,
        # openrouter.ai, slack.com, gmail.googleapis.com,
        # graph.microsoft.com, oauth2.googleapis.com, www.googleapis.com,
        # *.atlassian.net, api.notion.com -- and the BROWSER never contacted
        # a single one of them. Verified two ways: a source scan for
        # fetch()/XHR/WebSocket to an absolute external URL returns nothing
        # (the only occurrences of these hostnames in frontend/ are link
        # hrefs and help text), and a Chromium run across every pane recorded
        # zero external requests.
        #
        # Every one of those integrations is called SERVER-side with httpx,
        # where CSP does not apply at all. So the allowances bought nothing
        # and cost real security: connect-src is the directive that limits
        # where injected script can exfiltrate data to, and each extra origin
        # is another channel out. api.github.com and the Google endpoints in
        # particular accept arbitrary query strings that an attacker controls.
        #
        # Kept: 'self' for the app's own API, blob:/ws:/wss: for streaming and
        # live updates, and the loopback origins for a locally running Ollama.
        "connect-src 'self' blob: ws: wss: http://127.0.0.1:* http://localhost:*; "
        "worker-src 'self' blob:; "
        "frame-src 'self' blob: data:; "
    ),
}


# ── CSP phase 3: report-only ───────────────────────────────────────────────────
# The enforcing policy above still carries script-src 'unsafe-inline' because
# 859 inline event handlers and 5 inline <script> blocks depend on it. Removing
# it before those are migrated would break the product, and a CSP that breaks
# the product gets reverted within a day — which is worse than not shipping it,
# because it burns the option.
#
# This is the intermediate step: send the STRICT policy in Report-Only mode
# alongside the permissive enforcing one. Browsers evaluate both, enforce the
# first and only report on the second. Nothing breaks, and every violation the
# strict policy WOULD have caused is posted to /api/security/csp-report.
#
# That turns "we think 313 handlers still need work" into a measured list taken
# from real usage, which is the evidence needed to decide when the switch is
# safe. Enabled by default precisely because it cannot break anything; set
# AGENTIC_CSP_REPORT_ONLY=0 to silence it.
_CSP_REPORT_ONLY_ENABLED = os.getenv('AGENTIC_CSP_REPORT_ONLY', '1').strip().lower() not in (
    '0', 'false', 'no', 'off',
)

CSP_REPORT_ONLY = (
    "default-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'self'; "
    # The whole point: no 'unsafe-inline' on script-src.
    "script-src 'self'; "
    # REPORT-ONLY RATCHET. This header exists to measure the NEXT tightening
    # before enforcing it, which is the job it stopped doing the moment the
    # enforcing policy caught up: after 461ba07 the two were byte-identical
    # except for report-uri, so it reported on rules already in force and
    # collected nothing actionable.
    #
    # It now drops 'unsafe-inline' from style-src, the last major weakness.
    # Browsers keep enforcing the permissive policy, so nothing breaks; every
    # style that WOULD be refused is reported to /api/security/csp-report
    # instead. That converts an estimate into a measurement.
    "style-src 'self'; "
    "font-src 'self' data:; "
    "img-src 'self' data: blob: https:; "
    "connect-src 'self' blob: ws: wss: http://127.0.0.1:* http://localhost:*; "
    "worker-src 'self' blob:; "
    "frame-src 'self' blob: data:; "
    "report-uri /api/security/csp-report"
)

# Paths exempt from rate limiting (static files, health checks)
_RATE_LIMIT_EXEMPT = {'/api/system/stats', '/api/system/health', '/manifest.json', '/sw.js'}


@app.middleware('http')
async def _security_middleware(request: Request, call_next):
    """Combined security middleware: rate limiting, request ID tracing, CSRF checks, and security headers."""
    # Request ID tracing
    request_id = request.headers.get('X-Request-ID') or uuid.uuid4().hex
    request.state.request_id = request_id

    client_ip = request.client.host if request.client else 'unknown'
    path = request.url.path
    now = _time.time()

    # Secure deployment mode: keep health probes public, require a bearer
    # token for every other API route. Static frontend delivery remains public
    # so the application shell can load and then authenticate its API calls.
    if _SECURE_MODE and path.startswith('/api/') and path not in _PUBLIC_SECURE_PATHS:
        authorization = request.headers.get('Authorization', '')
        expected = f'Bearer {_AUTH_TOKEN}'
        if not hmac.compare_digest(authorization, expected):
            from fastapi.responses import JSONResponse

            return JSONResponse(
                {'ok': False, 'error': 'Authentication required'},
                status_code=401,
                headers={'WWW-Authenticate': 'Bearer', 'X-Request-ID': request_id},
            )

    # Rate limiting (skip exempt paths and static files during normal traffic, bypass in automated tests)
    if not path.startswith('/static/') and not path.startswith('/preview/') and path not in _RATE_LIMIT_EXEMPT and not os.environ.get('PYTEST_CURRENT_TEST'):
        # Clean old entries
        _sweep_rate_limit_store(now)
        _rate_limit_store[client_ip] = [t for t in _rate_limit_store[client_ip] if now - t < _RATE_LIMIT_WINDOW]

        if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_MAX:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                {'ok': False, 'error': 'Rate limit exceeded. Try again later.'},
                status_code=429,
                headers={'Retry-After': str(_RATE_LIMIT_WINDOW), 'X-Request-ID': request_id},
            )

        _rate_limit_store[client_ip].append(now)

    # CSRF validation.
    #
    # This read `if csrf_token and csrf_token not in _CSRF_TOKENS`, so a request
    # that OMITTED the header skipped validation entirely. Verified against the
    # running server:
    #     POST /api/tasks (no header)            -> 200
    #     POST /api/tasks (X-CSRF-Token: bogus)  -> 403
    # An attacker's forged cross-site request simply does not send the header,
    # so the control rejected only honest mistakes.
    #
    # It was written that way for a reason: the frontend never sent a token
    # across any of its 282 POST call sites, so requiring one would have broken
    # the whole app. frontend/js/00-csrf.js now attaches it in a fetch wrapper,
    # which is why this can be tightened in the same commit.
    #
    # ROLLOUT: enforcement is opt-in via AGENTIC_CSRF_STRICT so an existing
    # deployment with scripted API clients is not broken by an upgrade. When
    # off, a missing token is allowed but LOGGED, giving operators a way to see
    # what would break before switching it on. A bad token is always rejected.
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and not os.environ.get('PYTEST_CURRENT_TEST'):
        # Stateless validation: verifies an HMAC signature rather than looking
        # the token up in a per-process dict, so every worker accepts every
        # worker's tokens. See services/csrf_secret.py.
        from .routers.security import csrf_token_is_valid

        csrf_token = request.headers.get('X-CSRF-Token')
        csrf_exempt = path in _CSRF_EXEMPT or path.startswith('/api/webhooks/')

        if not csrf_exempt:
            if csrf_token:
                if not csrf_token_is_valid(csrf_token):
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        {'ok': False, 'error': 'Invalid CSRF token provided.'},
                        status_code=403,
                        headers={'X-Request-ID': request_id},
                    )
            elif _CSRF_STRICT:
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    {
                        'ok': False,
                        'error': 'CSRF token required.',
                        'hint': 'GET /api/security/csrf-token and send it as X-CSRF-Token.',
                    },
                    status_code=403,
                    headers={'X-Request-ID': request_id},
                )
            else:
                log.warning(
                    'CSRF: %s %s accepted WITHOUT a token (set AGENTIC_CSRF_STRICT=1 to enforce)',
                    request.method, path,
                )

    # Process request
    response = await call_next(request)

    # Attach request ID trace header
    response.headers['X-Request-ID'] = str(request_id).strip()

    # Add security headers
    if _CSP_REPORT_ONLY_ENABLED and not path.startswith('/preview/'):
        # Not on /preview/: that route serves user- and agent-generated pages
        # which legitimately carry inline script, and reporting on them would
        # bury the signal from the application's own violations.
        response.headers['Content-Security-Policy-Report-Only'] = CSP_REPORT_ONLY

    for header, value in SECURITY_HEADERS.items():
        response.headers[str(header).strip()] = str(value).strip()

    # Preview documents get their own policy, applied AFTER the loop above so
    # it replaces the application policy rather than being replaced by it.
    # See PREVIEW_CSP for why: without this, inline script in a generated page
    # is blocked and Live Preview does not work at all.
    if path.startswith('/preview/'):
        response.headers['Content-Security-Policy'] = PREVIEW_CSP

    # SVG served from our own origin is executable XML, not an inert image: a
    # <script> inside one runs with full same-origin privileges under the
    # app's 'unsafe-inline' CSP. Uploaded and generated SVGs are sanitised at
    # write time (imagegen.sanitize_svg); this is the second layer, for any
    # SVG that reached the preview directory by another route.
    if path.startswith('/preview/') and path.lower().endswith('.svg'):
        response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
        response.headers['Content-Disposition'] = 'inline; filename="image.svg"'

    # Prevent aggressive caching of HTML/JS/CSS during development and updates
    if path == '/' or path.endswith(('.html', '.js', '.css')):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    return response


# ── Static files ───────────────────────────────────────────────────────────────
_possible_frontends = [
    _ROOT / 'frontend',
    _ROOT,
    _ROOT / 'Resources' / 'frontend',
    _ROOT / 'Resources',
    Path(__file__).resolve().parent.parent / 'frontend',
]
FRONTEND_DIR = _ROOT / 'frontend'
for _candidate in _possible_frontends:
    if (_candidate / 'index.html').exists():
        FRONTEND_DIR = _candidate
        break

from backend.config import get_data_dir

_data_root = get_data_dir()
PREVIEW_DIR = _data_root / 'preview'
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
if not (PREVIEW_DIR / 'index.html').exists():
    (PREVIEW_DIR / 'index.html').write_text('<!DOCTYPE html><html><head><meta charset="utf-8"><title>Agentic OS Preview</title></head><body style="background:#07080f;color:#64748b;font-family:sans-serif;padding:30px;text-align:center"><h3>⚡ Agentic OS Live Preview</h3><p>Open Studio or run scaffold to view your app here.</p></body></html>', encoding='utf-8')

app.mount('/static', StaticFiles(directory=str(FRONTEND_DIR)), name='static')
app.mount('/preview', StaticFiles(directory=str(PREVIEW_DIR), html=True), name='preview')

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(chat_router)
app.include_router(swarm_router)
app.include_router(memory_router)
app.include_router(agents_router)
app.include_router(secrets_router)
app.include_router(builder_router)
app.include_router(mcp_router)
app.include_router(connect_hub_router)
app.include_router(loops_router)
app.include_router(ws_router)
app.include_router(tts_router)
app.include_router(deploy_router)
app.include_router(e2e_router)
app.include_router(skills_router)
app.include_router(analytics_router)
app.include_router(pipeline_router)
app.include_router(obsidian_router)
app.include_router(system_router)
app.include_router(plugins_router)
app.include_router(plugin_hub_router)
app.include_router(onboarding_router)
app.include_router(collab_router)
app.include_router(github_router)
app.include_router(database_router)
app.include_router(composer_router)
app.include_router(sessions_router)
app.include_router(templates_router)
app.include_router(tasks_router)
app.include_router(control_tower_router)
app.include_router(workspaces_router)
app.include_router(webhooks_router)
app.include_router(testgen_router)
app.include_router(terminal_router)
app.include_router(imagegen_router)
app.include_router(integrations_router)
app.include_router(prompts_router)
app.include_router(codesearch_router)
app.include_router(workflow_router)
app.include_router(profiler_router)

# ── No-AI-provider handling ───────────────────────────────────────────────────
# llm.complete() raises LLMUnavailableError rather than returning placeholder help
# text that ~40 call sites were free to mistake for a real model reply (Chat,
# Supervisor and Browser Agent each shipped that exact bug). Any endpoint that
# doesn't explicitly opt into stubs now degrades to an honest 503 instead of
# reporting fabricated success.
from .services.llm import LLMUnavailableError as _LLMUnavailableError


@app.exception_handler(_LLMUnavailableError)
async def _llm_unavailable_handler(request: Request, exc: _LLMUnavailableError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        {
            'ok': False,
            'error': exc.message,
            'code': 'llm_unavailable',
            'model': exc.model,
            'setup_url': 'https://openrouter.ai/keys',
        },
        status_code=503,
    )


# ── Terminal access refusals ──────────────────────────────────────────────────
# The terminal router gates every one of its endpoints with a dependency. A
# dependency can only raise, so it raises TerminalAccessDeniedError and this renders
# it in the same {ok, error, code} shape as every other refusal in the platform
# instead of FastAPI's default {"detail": ...}.
from .routers.terminal import TerminalAccessDeniedError as _TerminalAccessDeniedError


@app.exception_handler(_TerminalAccessDeniedError)
async def _terminal_access_denied_handler(request: Request, exc: _TerminalAccessDeniedError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        {'ok': False, 'error': exc.error, 'code': exc.code},
        status_code=exc.status,
    )


# FIX 1: Timing middleware to populate _endpoint_stats for the profiler
from .routers.profiler import record_endpoint_latency as _record_latency


@app.middleware('http')
async def _latency_middleware(request, call_next):
    t0 = _time.perf_counter()
    response = await call_next(request)
    ms = (_time.perf_counter() - t0) * 1000
    _record_latency(request.url.path, ms)
    return response


app.include_router(pluginsdk_router)
app.include_router(multitab_router)
app.include_router(tauri_router)
app.include_router(replay_router)
app.include_router(crdt_router)
app.include_router(marketplace_router)
app.include_router(specs_router)
app.include_router(hooks_router)
app.include_router(codeindex_router)
app.include_router(arena_router)
app.include_router(voice_router)
app.include_router(steering_router)
app.include_router(bugbot_router)
app.include_router(ambient_router)
app.include_router(gitai_router)
app.include_router(fusion_router)
app.include_router(hitl_router)
app.include_router(browser_router)
app.include_router(websearch_router)
app.include_router(leaderboard_router)
app.include_router(evals_router)
app.include_router(observability_router)
app.include_router(knowledge_graph_router)
app.include_router(rag_router)
app.include_router(license_router)
app.include_router(userprofile_router)
app.include_router(docs_router)
app.include_router(documents_router)
# Sprint A
app.include_router(audit_log_router)
app.include_router(compliance_router)
app.include_router(drift_router)
app.include_router(a2a_router)
app.include_router(agent_identity_router)
# Sprint B
from .routers.goal_manager import router as goal_manager_router
from .routers.supervisor import router as supervisor_router

app.include_router(supervisor_router)
app.include_router(goal_manager_router)
# Sprint C
from .routers.connectors import router as connectors_router
from .routers.mcp_gateway import router as mcp_gateway_router

app.include_router(mcp_gateway_router)
app.include_router(connectors_router)
# Sprint D
from .routers.agent_monitor import router as agent_monitor_router
from .routers.eval_framework import router as eval_framework_router
from .routers.finops import router as finops_router

app.include_router(agent_monitor_router)
app.include_router(finops_router)
app.include_router(eval_framework_router)
app.include_router(security_router)
app.include_router(notifications_router)
app.include_router(search_router)
app.include_router(hierarchy_router)
app.include_router(mobile_router)
app.include_router(sync_router)
app.include_router(rbac_router)
app.include_router(cluster_router)
app.include_router(finetune_router)
app.include_router(bounty_hunter_router)
app.include_router(pqc_router)
app.include_router(workspace_export_router)
app.include_router(auth_router)
app.include_router(engine_router)

# ── WebSocket endpoint registered directly on app (include_router may not work for WS in FastAPI 0.139+) ──
from .routers.websocket import _get_agent_statuses, _get_memory_stats
from .routers.websocket import _handle_message as _ws_handle_msg
from .routers.websocket import _send_init as _ws_send_init
from .routers.websocket import manager as _ws_manager


@app.websocket('/ws')
async def websocket_endpoint_direct(ws: WebSocket):
    """Primary WebSocket endpoint for real-time updates."""
    if not await require_websocket_auth(ws):
        return
    await _ws_manager.connect(ws)
    tasks = []
    try:
        await _ws_send_init(ws)

        async def heartbeat():
            """Execute or process heartbeat operation."""
            import time

            while True:
                await asyncio.sleep(5)
                try:
                    await _ws_manager.send_to(ws, {'type': 'ping', 'ts': time.time()})
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                    break

        async def status_updates():
            """Execute or process status updates operation."""
            while True:
                await asyncio.sleep(8)
                try:
                    agents = await _get_agent_statuses()
                    await _ws_manager.send_to(ws, {'type': 'agent_status', 'agents': agents})
                    stats = await _get_memory_stats()
                    await _ws_manager.send_to(ws, {'type': 'memory_stats', **stats})
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                    break

        tasks = [
            asyncio.create_task(heartbeat()),
            asyncio.create_task(status_updates()),
        ]

        while True:
            try:
                data = await ws.receive_text()
                msg = json.loads(data)
                await _ws_handle_msg(ws, msg)
            except WebSocketDisconnect:
                break
            except Exception as e:
                logging.getLogger('agentic.ws').warning('WS msg error: %s', e)
                break

    except WebSocketDisconnect:
        pass
    finally:
        _ws_manager.disconnect(ws)
        for t in tasks:
            t.cancel()


# ── HITL WebSocket endpoint ────────────────────────────────────────────────────
@app.websocket('/api/ws')
async def hitl_ws_endpoint(ws: WebSocket):
    """Secondary WebSocket for HITL interrupts (frontend at /api/ws)."""
    if not await require_websocket_auth(ws):
        return
    await _ws_manager.connect(ws)
    try:
        await _ws_send_init(ws)
        while True:
            try:
                data = await ws.receive_text()
                msg = json.loads(data)
                await _ws_handle_msg(ws, msg)
            except WebSocketDisconnect:
                break
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                break
    except WebSocketDisconnect:
        pass
    finally:
        _ws_manager.disconnect(ws)


# ── Core routes ────────────────────────────────────────────────────────────────
@app.get('/')
def index():
    """Execute or process index operation."""
    return FileResponse(FRONTEND_DIR / 'index.html', headers={'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0', 'Pragma': 'no-cache', 'Expires': '0'})


@app.get('/manifest.json')
def manifest():
    """Execute or process manifest operation."""
    return FileResponse(FRONTEND_DIR / 'manifest.json', media_type='application/manifest+json')


@app.get('/sw.js')
def service_worker():
    """Execute or process service worker operation."""
    return FileResponse(FRONTEND_DIR / 'sw.js', media_type='application/javascript')


@app.get('/api/goals')
def goals():
    """Execute or process goals operation."""
    con = get_conn()
    try:
        rows = con.execute('SELECT * FROM goals ORDER BY id').fetchall()
    finally:
        con.close()
    result = [dict(r) for r in rows]
    if not result:
        result = [
            {'id': 1, 'title': 'Wire OpenRouter chat (streaming)', 'layer': 'Goals', 'progress': 100, 'status': 'done'},
            {'id': 2, 'title': 'Multi-agent swarm + AI judge', 'layer': 'Execution', 'progress': 100, 'status': 'done'},
            {'id': 3, 'title': 'Memory Galaxy 3D', 'layer': 'Memory', 'progress': 100, 'status': 'done'},
            {'id': 4, 'title': 'MCP Tool Router', 'layer': 'Ship', 'progress': 100, 'status': 'done'},
            {'id': 5, 'title': 'Autonomous scheduler loops', 'layer': 'Execution', 'progress': 100, 'status': 'done'},
            {'id': 6, 'title': 'WebSocket real-time updates', 'layer': 'Goals', 'progress': 100, 'status': 'done'},
            {'id': 7, 'title': 'Tauri desktop app', 'layer': 'Ship', 'progress': 65, 'status': 'active'},
            {'id': 8, 'title': 'Voice agent (Whisper + TTS)', 'layer': 'Execution', 'progress': 20, 'status': 'active'},
        ]
    return result


@app.get('/api/cost')
def cost():
    """Execute or process cost operation."""
    con = get_conn()
    try:
        rows = con.execute('SELECT agent, SUM(tokens) as t, SUM(cost) as c FROM chat_log GROUP BY agent').fetchall()
        by_agent = [dict(r) for r in rows]
        total_tokens = sum(r['t'] or 0 for r in by_agent)
        total_cost = sum(r['c'] or 0.0 for r in by_agent)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        by_agent, total_tokens, total_cost = [], 0, 0.0
    finally:
        con.close()
    return {
        'total_tokens': total_tokens,
        'total_cost_usd': round(total_cost, 6),
        'saved_vs_saas': round(max(0, 350 - total_cost * 100), 2),
        'by_agent': by_agent,
    }


@app.get('/api/audit')
def audit(limit: int = 100):
    """Execute or process audit operation."""
    # A negative LIMIT means UNLIMITED in SQLite, so ?limit=-1 returned the
    # entire audit log in one response -- 1398 rows against 2 for ?limit=2,
    # measured on the running server. The audit log is the largest table in
    # the platform and the one most likely to grow without bound.
    return audit_list(max(1, min(limit, 500)))


# /api/skills and /api/skills/run now handled by skills_router


@app.post('/api/backup')
def backup():
    """Create a database backup with automatic rotation (keeps last 10)."""
    import datetime
    import shutil

    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = _ROOT / 'memory'
    dest = backup_dir / f'backup_{ts}.db'
    try:
        shutil.copy2(backup_dir / 'agentic.db', dest)

        # Rotate: keep only the 10 most recent backups
        backups = sorted(backup_dir.glob('backup_*.db'), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[10:]:
            old.unlink(missing_ok=True)

        return {'ok': True, 'path': str(dest), 'filename': dest.name, 'total_backups': min(len(backups), 10)}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# Kanban / Tasks endpoints now live in backend/routers/tasks.py (tasks_router).

# Pipeline now handled by pipeline_router (/api/pipeline/run)
