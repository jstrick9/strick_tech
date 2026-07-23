"""
Agentic OS v6.0 — Backend Entry Point
Local-first Agentic AI Operating System
"""

from __future__ import annotations

import contextlib
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
from .routers.browser_agent import router as browser_router
from .routers.bugbot import router as bugbot_router
from .routers.builder import router as builder_router

# ── Routers ────────────────────────────────────────────────────────────────────
from .routers.chat import router as chat_router
from .routers.codeindex import router as codeindex_router
from .routers.codesearch import router as codesearch_router
from .routers.collab import router as collab_router
from .routers.compliance import router as compliance_router
from .routers.control_tower import router as control_tower_router
from .routers.crdt import router as crdt_router
from .routers.database import router as database_router
from .routers.deploy import router as deploy_router
from .routers.docs_center import router as docs_router
from .routers.documents import router as documents_router
from .routers.drift import router as drift_router
from .routers.e2e import router as e2e_router
from .routers.evals import router as evals_router
from .routers.fusion import router as fusion_router
from .routers.gitai import router as gitai_router
from .routers.github import router as github_router
from .routers.hierarchy import router as hierarchy_router
from .routers.hitl import router as hitl_router
from .routers.rbac import router as rbac_router
from .routers.telephony import router as telephony_router
from .routers.cluster import router as cluster_router
from .routers.finetune import router as finetune_router
from .routers.bounty_hunter import router as bounty_hunter_router
from .routers.p2p_sharding import router as p2p_sharding_router
from .routers.pqc import router as pqc_router
from .routers.robotics import router as robotics_router
from .routers.bci import router as bci_router
from .routers.compiler import router as compiler_router
from .routers.digital_twin import router as digital_twin_router
from .routers.satellite import router as satellite_router
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
from .routers.plugins import router as plugins_router
from .routers.pluginsdk import router as pluginsdk_router
from .routers.profiler import router as profiler_router
from .routers.prompts import router as prompts_router
from .routers.rag import router as rag_router
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
from .routers.workspaces import router as workspaces_router
from .services import scheduler as sched_svc
from .version import VERSION
from .services.memory_db import (
    agents_seed_defaults,
    audit_list,
    ensure_schema,
    get_conn,
)


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
    # Start autonomous scheduler
    try:
        sched_svc.start()
        log.info('Autonomous scheduler started')
    except Exception as e:
        log.warning('Scheduler failed: %s', e)
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
        {'name': 'telephony', 'description': 'Autonomous voice-to-voice telephony streaming (WebRTC / Twilio)'},
        {'name': 'cluster', 'description': 'Distributed multi-node edge device compute grid & task dispatch'},
        {'name': 'finetune', 'description': 'Local zero-shot LoRA fine-tuning engine (MLX / CUDA)'},
        {'name': 'bounty-hunter', 'description': 'Autonomous zero-day security scanner & self-patching loop'},
        {'name': 'p2p-sharding', 'description': 'Decentralized P2P encrypted model checkpoint sharding (IPFS/BitTorrent)'},
        {'name': 'pqc', 'description': 'Lattice-based post-quantum cryptography (ML-KEM-1024 / Kyber / Dilithium)'},
        {'name': 'robotics', 'description': 'Hardware robotics actuators & IoT sensor telemetry control (ROS 2 / MQTT)'},
        {'name': 'bci', 'description': 'Real-time EEG brain-computer interface telemetry & neural intent decoding'},
        {'name': 'compiler', 'description': 'Self-replicating native binary compilation & zero-downtime hot-swap kernel patching'},
        {'name': 'digital-twin', 'description': 'Physical-digital reality twin synchronization (Apple Vision Pro / OpenXR spatial computing)'},
        {'name': 'satellite', 'description': 'Multi-planetary offline satellite edge mesh networking (DTN / RFC 9171 Bundle Protocol)'},
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
# Keep middleware behavior aligned with the validated configuration surface so
# local deployments and test environments can tune the limit without changing
# application code. Invalid values fall back to the documented defaults.
try:
    _RATE_LIMIT_WINDOW = max(10, int(os.getenv('RATE_LIMIT_WINDOW', '60')))
except (TypeError, ValueError):
    _RATE_LIMIT_WINDOW = 60
try:
    _RATE_LIMIT_MAX = max(10, int(os.getenv('RATE_LIMIT_MAX', '300')))
except (TypeError, ValueError):
    _RATE_LIMIT_MAX = 300
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
SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'SAMEORIGIN',
    'X-XSS-Protection': '1; mode=block',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    'Content-Security-Policy': (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://cdn.tailwindcss.com https://unpkg.com https://cdn.monaco-editor.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com data:; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self' ws: wss: http: https:; "
        "worker-src 'self' blob:; "
        "frame-src 'self' blob: data:; "
    ),
}

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
        _rate_limit_store[client_ip] = [t for t in _rate_limit_store[client_ip] if now - t < _RATE_LIMIT_WINDOW]

        if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_MAX:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                {'ok': False, 'error': 'Rate limit exceeded. Try again later.'},
                status_code=429,
                headers={'Retry-After': str(_RATE_LIMIT_WINDOW), 'X-Request-ID': request_id},
            )

        _rate_limit_store[client_ip].append(now)

    # CSRF Token validation check when strictly enforced or provided via headers
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and not os.environ.get('PYTEST_CURRENT_TEST'):
        from .routers.security import _CSRF_TOKENS

        csrf_token = request.headers.get('X-CSRF-Token')
        if csrf_token and csrf_token not in _CSRF_TOKENS:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                {'ok': False, 'error': 'Invalid CSRF token provided.'},
                status_code=403,
                headers={'X-Request-ID': request_id},
            )

    # Process request
    response = await call_next(request)

    # Attach request ID trace header
    response.headers['X-Request-ID'] = str(request_id).strip()

    # Add security headers
    for header, value in SECURITY_HEADERS.items():
        response.headers[str(header).strip()] = str(value).strip()

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
app.include_router(onboarding_router)
app.include_router(collab_router)
app.include_router(github_router)
app.include_router(database_router)
app.include_router(composer_router)
app.include_router(sessions_router)
app.include_router(templates_router)
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
app.include_router(telephony_router)
app.include_router(cluster_router)
app.include_router(finetune_router)
app.include_router(bounty_hunter_router)
app.include_router(p2p_sharding_router)
app.include_router(pqc_router)
app.include_router(robotics_router)
app.include_router(bci_router)
app.include_router(compiler_router)
app.include_router(digital_twin_router)
app.include_router(satellite_router)

# ── WebSocket endpoint registered directly on app (include_router may not work for WS in FastAPI 0.139+) ──
from .routers.websocket import _get_agent_statuses, _get_memory_stats
from .routers.websocket import _handle_message as _ws_handle_msg
from .routers.websocket import _send_init as _ws_send_init
from .routers.websocket import manager as _ws_manager


@app.websocket('/ws')
async def websocket_endpoint_direct(ws: WebSocket):
    """Primary WebSocket endpoint for real-time updates."""
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
    return audit_list(limit)


# /api/skills and /api/skills/run now handled by skills_router


@app.post('/api/backup')
def backup():
    """Execute or process backup operation."""
    import datetime
    import shutil

    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = _ROOT / 'memory' / f'backup_{ts}.db'
    try:
        shutil.copy2(_ROOT / 'memory' / 'agentic.db', dest)
        return {'ok': True, 'path': str(dest), 'filename': dest.name}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ── Kanban / Tasks ─────────────────────────────────────────────────────────────
def _task_dict(r) -> dict:
    d = dict(r)
    d['status'] = d.get('status', 'todo') if d.get('status') in ('todo', 'doing', 'blocked', 'done') else 'todo'
    d['priority'] = d.get('priority', 'medium') if d.get('priority') in ('high', 'medium', 'low') else 'medium'
    d['agent'] = d.get('agent') or 'builder'
    d['layer'] = d.get('layer') or 'Tasks'
    d['description'] = d.get('description') or ''
    d['sort_order'] = d.get('sort_order') or d.get('id') or 0
    return d


@app.get('/api/kanban')
def kanban():
    """Execute or process kanban operation."""
    con = get_conn()
    try:
        rows = con.execute("""
            SELECT id, title, status, priority, agent,
                   COALESCE(layer,'Tasks') as layer,
                   COALESCE(description,'') as description,
                   created_at,
                   COALESCE(updated_at, created_at) as updated_at,
                   COALESCE(sort_order, id) as sort_order
            FROM tasks
            ORDER BY CASE status WHEN 'doing' THEN 0 WHEN 'todo' THEN 1
                                 WHEN 'blocked' THEN 2 WHEN 'done' THEN 3 ELSE 4 END,
                     sort_order ASC, id DESC
        """).fetchall()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        rows = con.execute('SELECT id,title,status,priority,agent,created_at FROM tasks ORDER BY id DESC').fetchall()
    con.close()
    cols = {'todo': [], 'doing': [], 'blocked': [], 'done': []}
    for r in rows:
        t = _task_dict(r)
        cols.get(t['status'], cols['todo']).append(t)
    return cols


@app.get('/api/tasks')
def tasks_list(status: str = '', agent: str = '', limit: int = 200, q: str = ''):
    """Execute or process tasks list operation."""
    con = get_conn()
    where, params = [], []
    if status:
        where.append('status=?')
        params.append(status)
    if agent:
        where.append('agent=?')
        params.append(agent)
    if q:
        where.append('title LIKE ?')
        params.append(f'%{q}%')
    sql = (
        "SELECT id,title,status,priority,agent,COALESCE(layer,'Tasks') as layer,"
        "COALESCE(description,'') as description,created_at,COALESCE(sort_order,id) as sort_order FROM tasks"
    )
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY sort_order ASC, id DESC LIMIT ?'
    params.append(min(limit, 500))
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [_task_dict(r) for r in rows]


@app.post('/api/tasks')
async def tasks_create(req: Request):
    """Execute or process tasks create operation."""
    try:
        d = await req.json()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return {'ok': False, 'error': 'Invalid JSON body'}
    title = (d.get('title') or '').strip()[:240]
    if not title:
        return {'ok': False, 'error': 'title required'}
    status = d.get('status', 'todo')
    priority = d.get('priority', 'medium')
    agent = (d.get('agent', 'builder') or 'builder')[:32]
    layer = (d.get('layer', 'Tasks') or 'Tasks')[:48]
    desc = (d.get('description', '') or '')[:2000]
    if status not in ('todo', 'doing', 'blocked', 'done'):
        status = 'todo'
    if priority not in ('high', 'medium', 'low'):
        priority = 'medium'
    con = get_conn()
    cur = con.execute(
        'INSERT INTO tasks(title,status,priority,agent,layer,description,sort_order,updated_at) VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)',
        (title, status, priority, agent, layer, desc, d.get('sort_order', 0)),
    )
    tid = cur.lastrowid
    con.execute("INSERT INTO audit(action,detail) VALUES ('task_create',?)", (f'{tid}:{title[:80]}',))
    con.commit()
    con.close()
    # broadcast via WS
    try:
        import asyncio

        from .routers.websocket import broadcast_task_update

        asyncio.create_task(broadcast_task_update({'id': tid, 'title': title, 'status': status, 'action': 'created'}))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass
    return {'ok': True, 'id': tid, 'title': title, 'status': status}


@app.post('/api/tasks/bulk_update')
async def tasks_bulk_update(req: Request):
    """Execute or process tasks bulk update operation."""
    try:
        d = await req.json()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return {'ok': False, 'error': 'Invalid JSON body'}
    updates = d.get('updates', [])
    if not isinstance(updates, list):
        return {'ok': False, 'error': 'updates[] required'}
    con = get_conn()
    ok = 0
    for u in updates[:200]:
        tid = u.get('id')
        if not tid:
            continue
        sets, vals = [], []
        if 'status' in u and u['status'] in ('todo', 'doing', 'blocked', 'done'):
            sets.append('status=?')
            vals.append(u['status'])
        if 'sort_order' in u:
            try:
                sets.append('sort_order=?')
                vals.append(int(u['sort_order']))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass
        if sets:
            sets.append('updated_at=CURRENT_TIMESTAMP')
            vals.append(tid)
            con.execute(f'UPDATE tasks SET {", ".join(sets)} WHERE id=?', vals)
            ok += 1
    con.commit()
    con.close()
    return {'ok': True, 'updated': ok}


@app.patch('/api/tasks/{task_id}')
async def tasks_update(task_id: int, req: Request):
    """Execute or process tasks update operation."""
    try:
        d = await req.json()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return {'ok': False, 'error': 'Invalid JSON body'}
    allowed = {'title', 'status', 'priority', 'agent', 'layer', 'description', 'sort_order'}
    sets, vals = [], []
    for k in allowed:
        if k not in d:
            continue
        v = d[k]
        if k == 'status' and v not in ('todo', 'doing', 'blocked', 'done'):
            continue
        if k == 'priority' and v not in ('high', 'medium', 'low'):
            continue
        if k == 'title':
            v = str(v)[:240]
        if k == 'agent':
            v = str(v)[:32]
        if k == 'layer':
            v = str(v)[:48]
        if k == 'description':
            v = str(v)[:2000]
        sets.append(f'{k}=?')
        vals.append(v)
    if not sets:
        return {'ok': False, 'error': 'no valid fields'}
    sets.append('updated_at=CURRENT_TIMESTAMP')
    vals.append(task_id)
    con = get_conn()
    con.execute(f'UPDATE tasks SET {", ".join(sets)} WHERE id=?', vals)
    con.execute("INSERT INTO audit(action,detail) VALUES ('task_update',?)", (str(task_id),))
    con.commit()
    row = con.execute(
        "SELECT id,title,status,priority,agent,COALESCE(layer,'Tasks') as layer FROM tasks WHERE id=?", (task_id,)
    ).fetchone()
    con.close()
    return {'ok': True, 'task': _task_dict(row) if row else {}}


@app.post('/api/tasks/{task_id}')
async def tasks_update_post(task_id: int, req: Request):
    """Execute or process tasks update post operation."""
    return await tasks_update(task_id, req)


@app.delete('/api/tasks/{task_id}')
def tasks_delete(task_id: int):
    """Execute or process tasks delete operation."""
    con = get_conn()
    cur = con.execute('DELETE FROM tasks WHERE id=?', (task_id,))
    con.execute("INSERT INTO audit(action,detail) VALUES ('task_delete',?)", (str(task_id),))
    con.commit()
    con.close()
    return {'ok': True, 'deleted': task_id}


@app.post('/api/kanban/move')
async def kanban_move(req: Request):
    """Execute or process kanban move operation."""
    try:
        d = await req.json()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return {'ok': False, 'error': 'Invalid JSON body'}
    tid = d.get('id') or d.get('task_id')
    to = d.get('to_status') or d.get('status')
    if not tid or to not in ('todo', 'doing', 'blocked', 'done'):
        return {'ok': False, 'error': 'id + to_status required'}
    con = get_conn()
    con.execute('UPDATE tasks SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (to, int(tid)))
    con.commit()
    con.close()
    return {'ok': True}


# Pipeline now handled by pipeline_router (/api/pipeline/run)
