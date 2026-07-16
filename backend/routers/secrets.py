"""
Agentic OS — Secrets Vault Router
Fernet AES-256 encrypted secrets. Never in git. Auto-injected to os.environ.
"""

from __future__ import annotations

import contextlib

import base64
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Request

from ..services.memory_db import audit_log, ensure_schema, get_conn

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
        key = KEY_PATH.read_bytes()
        return Fernet(key)
    except ImportError:
        return None


def _encrypt(value: str) -> tuple[str, bool]:
    f = _get_fernet()
    if f:
        return f.encrypt(value.encode()).decode(), True
    # fallback: base64 (not secure, just obfuscation)
    return base64.b64encode(value.encode()).decode(), False


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
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    key = (body.get('key') or '').strip().upper()
    value = body.get('value') or ''
    scope = body.get('scope') or 'global'
    agent = body.get('agent') or ''

    if not key:
        return {'ok': False, 'error': 'key required'}
    # FIX 6: validate key format — must be safe env-var name
    import re as _re

    if not _re.match(r'^[A-Z][A-Z0-9_]{0,127}$', key):
        return {
            'ok': False,
            'error': 'key must be uppercase letters, digits, underscores, max 128 chars, start with a letter',
        }
    if not value:
        return {'ok': False, 'error': 'value required'}

    enc, is_fernet = _encrypt(value)
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
    audit_log('vault_set', f'{key} scope={scope} agent={agent}')

    return {'ok': True, 'key': key, 'fingerprint': fp, 'scope': scope, 'agent': agent, 'encrypted': is_fernet}


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
        return {'ok': False, 'error': 'not found'}
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
    os.environ.pop(key, None)
    audit_log('vault_delete', key)
    return {'ok': cur.rowcount > 0, 'deleted': key}
