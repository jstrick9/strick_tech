"""Product status surfaces must describe the state users actually receive."""
import time
from fastapi.testclient import TestClient
from backend.app import app
from backend.routers import license as license_router


def test_license_status_matches_a_real_pro_license(monkeypatch):
    monkeypatch.setattr(license_router, '_load_license', lambda: {
        'tier': 'pro', 'trial_end': 0, 'user_name': 'Joshua Strickland',
        'user_email': 'joshua@stricktech.com', 'org': 'Strick Tech',
    })
    response = TestClient(app).get('/api/license/status')
    data = response.json()
    assert response.status_code == 200
    assert data['tier'] == 'pro'
    assert data['stored_tier'] == 'pro'
    assert data['is_trial'] is False
    assert data['all_features'] is False


def test_license_status_reports_active_trial_truthfully(monkeypatch):
    monkeypatch.setattr(license_router, '_load_license', lambda: {
        'tier': 'trial', 'trial_end': time.time() + 3 * 86400,
        'user_name': 'Joshua Strickland', 'user_email': 'joshua@stricktech.com', 'org': 'Strick Tech',
    })
    data = TestClient(app).get('/api/license/status').json()
    assert data['stored_tier'] == 'trial'
    assert data['is_trial'] is True
    assert data['trial_expired'] is False
    assert data['all_features'] is True


def test_csp_allows_monaco_editor_workers_without_opening_script_origins():
    from backend.app import SECURITY_HEADERS
    csp = SECURITY_HEADERS['Content-Security-Policy']
    assert "worker-src 'self' blob:" in csp
    assert "script-src 'self'" in csp
