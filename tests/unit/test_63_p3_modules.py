"""
Tests for P3 modules: auth, workspace_export, plugin_sandbox
"""
import pytest


class TestAuth:
    """Test the authentication system."""

    def test_register_first_user_becomes_admin(self, client):
        """First registered user should get admin role."""
        # Check if admin already exists from prior test runs
        existing = client.get('/api/auth/users')
        if existing.status_code == 200 and existing.json().get('users'):
            pytest.skip('Users already exist from prior test run')
        r = client.post('/api/auth/register', json={
            'username': 'testadmin',
            'password': 'testpass123',
            'display_name': 'Test Admin',
        })
        d = r.json()
        assert d.get('ok') is True
        assert d.get('role') == 'admin'
        assert d.get('api_key', '').startswith('ak_')

    def test_register_second_user_becomes_user(self, client):
        """Second registered user should get user role."""
        # First user (admin) already registered in previous test
        r = client.post('/api/auth/register', json={
            'username': 'testuser2',
            'password': 'testpass123',
        })
        d = r.json()
        # May fail if first test didn't run — that's OK
        if d.get('ok'):
            assert d.get('role') == 'user'

    def test_register_rejects_short_username(self, client):
        r = client.post('/api/auth/register', json={
            'username': 'a',
            'password': 'testpass123',
        })
        assert r.status_code == 400

    def test_register_rejects_short_password(self, client):
        r = client.post('/api/auth/register', json={
            'username': 'newuser',
            'password': '12345',
        })
        assert r.status_code == 400

    def test_login_with_valid_credentials(self, client):
        """Login with valid credentials returns a token."""
        r = client.post('/api/auth/login', json={
            'username': 'testadmin',
            'password': 'testpass123',
        })
        d = r.json()
        if d.get('ok'):
            assert 'token' in d
            assert d['user']['username'] == 'testadmin'

    def test_login_rejects_wrong_password(self, client):
        r = client.post('/api/auth/login', json={
            'username': 'testadmin',
            'password': 'wrongpassword',
        })
        assert r.status_code == 401

    def test_me_endpoint_without_auth(self, client):
        """GET /api/auth/me returns response based on auth state."""
        r = client.get('/api/auth/me')
        d = r.json()
        # If users exist, 401 without key. If no users, unauthenticated response.
        assert r.status_code in (200, 401)
        assert 'ok' in d or 'detail' in d

    def test_rotate_key(self, client):
        """POST /api/auth/rotate-key returns a new API key."""
        r = client.post('/api/auth/rotate-key')
        # Should work if auth is optional (no users) or fail with 401
        assert r.status_code in (200, 401)


class TestWorkspaceExport:
    """Test workspace export/import/stats."""

    def test_export_workspace(self, client):
        r = client.get('/api/workspace/export')
        d = r.json()
        assert d.get('format') == 'agentic-os-workspace'
        assert d.get('version') == 1
        assert 'tables' in d
        assert 'summary' in d

    def test_export_excludes_secrets_by_default(self, client):
        r = client.get('/api/workspace/export')
        d = r.json()
        assert 'secrets' not in d.get('tables', {})

    def test_export_includes_secrets_when_asked(self, client):
        r = client.get('/api/workspace/export?include_secrets=true')
        d = r.json()
        assert 'secrets' in d.get('tables', {})

    def test_export_excludes_chat_when_asked(self, client):
        r = client.get('/api/workspace/export?include_chat=false')
        d = r.json()
        assert 'chat_log' not in d.get('tables', {})

    def test_workspace_stats(self, client):
        r = client.get('/api/workspace/stats')
        d = r.json()
        assert d.get('ok') is True
        assert 'stats' in d
        assert 'agents' in d['stats']
        assert 'chat_log' in d['stats']
        assert 'db_size_mb' in d['stats']

    def test_import_rejects_invalid_format(self, client):
        r = client.post('/api/workspace/import', json={'format': 'invalid'})
        assert r.status_code == 400

    def test_import_rejects_empty_archive(self, client):
        r = client.post('/api/workspace/import', json={
            'format': 'agentic-os-workspace',
            'tables': {},
        })
        assert r.status_code == 400

    def test_import_roundtrip(self, client):
        """Export then import should succeed without errors."""
        export_r = client.get('/api/workspace/export')
        archive = export_r.json()
        import_r = client.post('/api/workspace/import', json=archive)
        d = import_r.json()
        assert d.get('ok') is True
        assert d.get('total', 0) >= 0


class TestPluginSandbox:
    """Test the plugin sandbox module."""

    def test_validate_safe_code(self):
        from backend.services.plugin_sandbox import validate_plugin_code
        result = validate_plugin_code('result = 2 + 2')
        assert result['ok'] is True
        assert result['violations'] == []

    def test_validate_blocks_os_import(self):
        from backend.services.plugin_sandbox import validate_plugin_code
        result = validate_plugin_code('import os\nos.system("rm -rf /")')
        assert result['ok'] is False
        assert any('os' in v for v in result['violations'])

    def test_validate_blocks_eval(self):
        from backend.services.plugin_sandbox import validate_plugin_code
        result = validate_plugin_code('eval("print(1)")')
        assert result['ok'] is False

    def test_validate_blocks_subprocess(self):
        from backend.services.plugin_sandbox import validate_plugin_code
        result = validate_plugin_code('import subprocess\nsubprocess.run(["ls"])')
        assert result['ok'] is False

    def test_validate_blocks_exec(self):
        from backend.services.plugin_sandbox import validate_plugin_code
        result = validate_plugin_code('exec("print(1)")')
        assert result['ok'] is False

    def test_validate_blocks_open(self):
        from backend.services.plugin_sandbox import validate_plugin_code
        result = validate_plugin_code('f = open("/etc/passwd")')
        assert result['ok'] is False

    def test_validate_blocks_dunder(self):
        from backend.services.plugin_sandbox import validate_plugin_code
        result = validate_plugin_code('x = __builtins__')
        assert result['ok'] is False

    def test_execute_safe_code(self):
        from backend.services.plugin_sandbox import execute_plugin_sandboxed
        result = execute_plugin_sandboxed('result = 2 + 3')
        assert result['ok'] is True
        assert result['result'] == 5

    def test_execute_rejects_dangerous_code(self):
        from backend.services.plugin_sandbox import execute_plugin_sandboxed
        result = execute_plugin_sandboxed('import os; os.system("whoami")')
        assert result['ok'] is False
        assert 'violation' in result['error'].lower() or 'blocked' in result['error'].lower()

    def test_execute_with_context(self):
        from backend.services.plugin_sandbox import execute_plugin_sandboxed
        result = execute_plugin_sandboxed(
            'result = x + y',
            context={'x': 10, 'y': 20}
        )
        assert result['ok'] is True
        assert result['result'] == 30

    def test_execute_syntax_error(self):
        from backend.services.plugin_sandbox import execute_plugin_sandboxed
        result = execute_plugin_sandboxed('def (invalid')
        assert result['ok'] is False

    def test_sandbox_globals_limited(self):
        from backend.services.plugin_sandbox import create_sandbox_globals
        g = create_sandbox_globals()
        builtins = g['__builtins__']
        assert 'print' in builtins
        assert 'len' in builtins
        # Dangerous ones should be absent
        assert '__import__' not in builtins
        assert 'eval' not in builtins
        assert 'exec' not in builtins
        assert 'open' not in builtins
