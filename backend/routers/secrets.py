"""
Agentic OS — Secrets Vault Router
Fernet AES-256 encrypted secrets. Never in git. Auto-injected to os.environ.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import os
import sqlite3

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..services.memory_db import audit_log, ensure_schema, get_conn

log = logging.getLogger('agentic.secrets')

router = APIRouter(prefix='/api/secrets', tags=['secrets'])
from backend.config import get_data_dir

ROOT = get_data_dir()
KEY_PATH = ROOT / 'memory' / '.vault_key'


def _get_fernet():
    try:
        from cryptography.fernet import Fernet

        KEY_PATH.parent.mkdir(exist_ok=True)
        if not KEY_PATH.exists():
            KEY_PATH.write_bytes(Fernet.generate_key())
            KEY_PATH.chmod(0o600)
        else:
            # Tighten permissions on an EXISTING key too. chmod ran only in the
            # creation branch, so any vault created before that line was added
            # kept whatever the umask gave it -- and stayed that way forever.
            # Found in this repo: memory/.vault_key was mode 644, world-readable.
            #
            # That key decrypts every stored credential, so its file mode is the
            # whole of the vault's at-rest protection. Module 17 refused to let
            # Database Studio read the secrets table for exactly this reason;
            # leaving the master key readable by any local process undoes it.
            try:
                mode = KEY_PATH.stat().st_mode & 0o777
                if mode & 0o077:
                    KEY_PATH.chmod(0o600)
                    log.warning(
                        'Vault key %s was mode %o (group/other readable) — tightened to 600',
                        KEY_PATH, mode,
                    )
            except OSError as e:  # pragma: no cover - non-POSIX or permission denied
                log.error('Could not secure vault key permissions: %s', e)
        key = KEY_PATH.read_bytes()
        return Fernet(key)
    except ImportError:
        return None


def _encrypt(value: str) -> tuple[str, bool]:
    f = _get_fernet()
    if f:
        return f.encrypt(value.encode()).decode(), True
    # Never silently downgrade secrets to reversible base64. The cryptography
    # dependency is required for a functioning vault.
    return '', False


def _decrypt(enc: str, is_fernet: bool = True) -> str:
    f = _get_fernet()
    if f and is_fernet:
        with contextlib.suppress(Exception):
            return f.decrypt(enc.encode()).decode()
    try:
        return base64.b64decode(enc).decode()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return ''


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def _inject_to_env():
    """Load all vault secrets into os.environ on startup."""
    try:
        ensure_schema()
    except Exception:
        # Intentionally ignored — non-critical operation
        pass
    con = get_conn()
    try:
        rows = con.execute("SELECT key, value_enc FROM secrets WHERE scope='global'").fetchall()
    finally:
        con.close()
    for r in rows:
        try:
            val = _decrypt(r['value_enc'])
            if val:
                os.environ.setdefault(r['key'], val)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError, sqlite3.Error):
            pass


# Call on import to inject secrets into env
try:
    _inject_to_env()
except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError, sqlite3.Error, Exception):
    pass


@router.get('/list')
def list_secrets(masked: bool = True):
    """Retrieve and return list secrets."""
    con = get_conn()
    try:
        rows = con.execute(
            "SELECT id, key, scope, agent, fingerprint, length, datetime(updated_at,'localtime') as updated_at FROM secrets ORDER BY key"
        ).fetchall()
    finally:
        con.close()
    f = _get_fernet()
    items = []
    for r in rows:
        d = dict(r)
        d['masked'] = '••••••••' if masked else None
        items.append(d)
    return {
        'ok': True,
        'count': len(items),
        'items': items,
        'encrypted': f is not None,
        'engine': 'Fernet AES-256' if f else 'Base64 (install cryptography for encryption)',
        'vault_path': str(KEY_PATH),  # FIX 13: actual vault key file
        'warning': None if f else "Install 'cryptography' for real encryption: pip install cryptography",
    }


@router.post('/set')
async def set_secret(req: Request):
    """Execute or process set secret operation."""
    try:
        ensure_schema()
    except Exception:
        # Intentionally ignored — non-critical operation
        pass
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    key = (body.get('key') or '').strip().upper()
    value = body.get('value') or ''
    scope = body.get('scope') or 'global'
    agent = body.get('agent') or ''

    if not key:
        return JSONResponse({'ok': False, 'error': 'key required'}, status_code=400)
    # FIX 6: validate key format — must be safe env-var name
    import re as _re

    if not _re.match(r'^[A-Z][A-Z0-9_]{0,127}$', key):
        return {
            'ok': False,
            'error': 'key must be uppercase letters, digits, underscores, max 128 chars, start with a letter',
        }
    if not value:
        return JSONResponse({'ok': False, 'error': 'value required'}, status_code=400)

    enc, is_fernet = _encrypt(value)
    if not is_fernet:
        return JSONResponse(
            {'ok': False, 'error': 'Encrypted vault unavailable: install cryptography before storing secrets'},
            status_code=503,
        )
    fp = _fingerprint(value)
    length = len(value)

    con = get_conn()
    try:
        con.execute(
            """INSERT INTO secrets(key, value_enc, scope, agent, fingerprint, length, updated_at)
               VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(key) DO UPDATE SET
                 value_enc=excluded.value_enc, scope=excluded.scope, agent=excluded.agent,
                 fingerprint=excluded.fingerprint, length=excluded.length, updated_at=CURRENT_TIMESTAMP""",
            (key, enc, scope, agent, fp, length),
        )
        con.commit()
    finally:
        con.close()

    # inject to env immediately
    os.environ[key] = value
    try:
        audit_log('vault_set', f'{key} scope={scope} agent={agent}')
    except Exception:
        # Intentionally ignored — non-critical operation
        pass

    return {'ok': True, 'key': key, 'fingerprint': fp, 'scope': scope, 'agent': agent, 'encrypted': is_fernet}


@router.post('/test-connection')
async def test_secret_connection(req: Request):
    """Verify live API connection for OpenRouter, Ollama, or custom provider keys."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    provider = body.get('provider') or 'openrouter'
    key = body.get('key') or os.environ.get('OPENROUTER_API_KEY') or ''

    import httpx
    if provider == 'openrouter':
        if not key:
            return {'ok': False, 'error': 'No OpenRouter API key provided or found in vault.'}
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                # BUG FIX: this used to call GET /api/v1/models, which is a
                # PUBLIC endpoint on OpenRouter — it returns HTTP 200 with the
                # full catalogue for an invalid key, a garbage string, or no
                # Authorization header at all. So "Test Connection" reported
                # "✅ Verified OpenRouter connection! 338 models available" for
                # literally any input. A user who pasted a typo'd or revoked
                # key got a green check here and then had every single chat
                # request fail with no idea why.
                #
                # /api/v1/auth/key is the authenticated endpoint: it returns
                # 401 for a bad or missing key and echoes the key's own
                # metadata (label, usage, limit) when the key is real.
                # Verified against the live API: bad key -> 401, absent -> 401.
                auth = await client.get(
                    'https://openrouter.ai/api/v1/auth/key',
                    headers={'Authorization': f'Bearer {key}'},
                )
                if auth.status_code in (401, 403):
                    return {
                        'ok': False,
                        'error': f'OpenRouter rejected this key (HTTP {auth.status_code}). '
                        'Check that it is correct and still active.',
                    }
                if auth.status_code != 200:
                    return {'ok': False, 'error': f'OpenRouter returned HTTP {auth.status_code} while verifying the key.'}

                key_info = {}
                try:
                    key_info = (auth.json() or {}).get('data', {}) or {}
                except (ValueError, AttributeError):
                    key_info = {}

                # The key is valid — now report how many models it can reach.
                models_count = 0
                try:
                    r = await client.get(
                        'https://openrouter.ai/api/v1/models', headers={'Authorization': f'Bearer {key}'}
                    )
                    if r.status_code == 200:
                        models_count = len((r.json() or {}).get('data', []) or [])
                except (httpx.RequestError, ValueError):
                    pass  # key is verified; the catalogue is a nice-to-have

                message = f'✅ Verified OpenRouter key! {models_count} models available.'
                limit = key_info.get('limit')
                usage = key_info.get('usage')
                if limit is not None:
                    remaining = round(float(limit) - float(usage or 0), 4)
                    message += f' Credit remaining: ${remaining}.'
                elif usage is not None:
                    message += f' Usage to date: ${usage}.'

                return {
                    'ok': True,
                    'provider': 'openrouter',
                    'models_count': models_count,
                    'label': key_info.get('label', ''),
                    'usage': usage,
                    'limit': limit,
                    'is_free_tier': key_info.get('is_free_tier'),
                    'message': message,
                }
        except Exception as e:
            return {'ok': False, 'error': f'Network verification error: {e}'}
    elif provider == 'ollama':
        raw_url = body.get('url') or os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
        url = raw_url.rstrip('/').removesuffix('/v1').rstrip('/')
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                try:
                    r = await client.get(f'{url}/api/tags')
                    if r.status_code == 404:
                        raise httpx.HTTPStatusError('404 Not Found', request=r.request, response=r)
                    if r.status_code == 200:
                        data = r.json()
                        models = data.get('models', [])
                        os.environ['OLLAMA_BASE_URL'] = url
                        import sys
                        if 'backend.services.llm' in sys.modules:
                            sys.modules['backend.services.llm'].OLLAMA_BASE = url
                        return {'ok': True, 'provider': 'ollama', 'models_count': len(models), 'message': f'✅ Verified Ollama connection on {url}! {len(models)} local models found.'}
                    else:
                        return {'ok': False, 'error': f'Ollama returned HTTP {r.status_code}'}
                except (httpx.HTTPStatusError, httpx.RequestError) as e:
                    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code != 404:
                        raise
                    r2 = await client.get(f'{url}/v1/models')
                    if r2.status_code == 200:
                        data2 = r2.json()
                        models2 = data2.get('data', [])
                        os.environ['OLLAMA_BASE_URL'] = url
                        import sys
                        if 'backend.services.llm' in sys.modules:
                            sys.modules['backend.services.llm'].OLLAMA_BASE = url
                        return {'ok': True, 'provider': 'ollama', 'models_count': len(models2), 'message': f'✅ Verified Ollama connection on {url} (/v1/models)! {len(models2)} local models found.'}
                    else:
                        return {'ok': False, 'error': f'Ollama returned HTTP {r2.status_code}'}
        except Exception as e:
            return {'ok': False, 'error': f'Could not connect to local Ollama at {url}: {e}'}
    return {'ok': False, 'error': f'Unknown provider: {provider}'}


@router.get('/get')
async def get_secret(key: str, reveal: bool = False):
    """Retrieve and return get secret."""
    key = key.strip().upper()
    con = get_conn()
    try:
        row = con.execute('SELECT value_enc, scope, agent, fingerprint FROM secrets WHERE key=?', (key,)).fetchone()
    finally:
        con.close()
    if not row:
        return JSONResponse({'ok': False, 'error': 'not found'}, status_code=404)
    if reveal:
        audit_log('vault_reveal', key)
        val = _decrypt(row['value_enc'])
        return {'ok': True, 'key': key, 'value': val, 'revealed': True}
    return {'ok': True, 'key': key, 'fingerprint': row['fingerprint'], 'scope': row['scope'], 'revealed': False}


# NOTE: /api/secrets/delete (body-based) removed — Starlette routes /{key} first.
# Use DELETE /api/secrets/{KEY_NAME} for all deletes.


@router.delete('/{key}')
def delete_secret_by_path(key: str):
    """Delete a secret by key in path (e.g. DELETE /api/secrets/MY_KEY)."""
    key = key.strip().upper()
    con = get_conn()
    try:
        cur = con.execute('DELETE FROM secrets WHERE key=?', (key,))
        con.commit()
    finally:
        con.close()
    # BUG FIX: returned HTTP 200 with {'ok': false, 'deleted': <key>} for a key
    # that never existed — reporting a deletion that did not happen, with a
    # success status code.
    if cur.rowcount == 0:
        return JSONResponse({'ok': False, 'error': f"Secret '{key}' not found"}, status_code=404)
    os.environ.pop(key, None)
    audit_log('vault_delete', key)
    return {'ok': True, 'deleted': key}
