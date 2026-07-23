"""Boundary tests for marketplace and plugin package ingestion."""
import io
import zipfile


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buf.getvalue()


def test_marketplace_zip_rejects_path_traversal(client):
    data = _zip({
        'manifest.json': '{"id":"boundary-pack","name":"Boundary Pack","version":"1.0.0"}',
        '../../escaped.txt': 'must not escape',
    })
    response = client.post('/api/marketplace/upload', files={'file': ('pack.zip', data, 'application/zip')})
    assert response.status_code == 200
    assert response.json().get('ok') is False
    from backend.routers.marketplace import PACKS_DIR
    assert not (PACKS_DIR / 'boundary-pack').exists()


def test_marketplace_zip_requires_manifest(client):
    data = _zip({'README.md': 'missing manifest'})
    response = client.post('/api/marketplace/upload', files={'file': ('pack.zip', data, 'application/zip')})
    assert response.status_code == 200
    assert response.json().get('ok') is False


def test_pluginsdk_manifest_validation_rejects_missing_fields(client):
    response = client.post('/api/pluginsdk/validate', json={'id': '../escape'})
    assert response.status_code == 200
    data = response.json()
    assert data.get('ok') is False
    assert data.get('errors')


def test_pluginsdk_rejects_unknown_capabilities(client):
    response = client.post('/api/pluginsdk/validate', json={
        'id': 'capability-test', 'name': 'Capability Test', 'version': '1.0.0',
        'description': 'test', 'skills': [], 'permissions': ['chat', 'root_shell'],
    })
    assert response.status_code == 200
    data = response.json()
    assert data.get('ok') is False
    assert any('Unknown permission' in error for error in data.get('errors', []))


def test_pluginsdk_pack_records_unsigned_provenance(client):
    response = client.post('/api/pluginsdk/packs', json={'name': 'Provenance Test', 'id': 'provenance-test'})
    assert response.status_code == 200
    pack = response.json()['pack']
    assert pack['provenance']['status'] == 'unsigned'
    assert len(pack['provenance']['manifest_sha256']) == 64
