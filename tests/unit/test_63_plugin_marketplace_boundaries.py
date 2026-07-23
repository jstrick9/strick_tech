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
