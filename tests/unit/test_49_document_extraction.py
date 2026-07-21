"""Local document extraction makes PDF and Word attachments honest and usable."""
from io import BytesIO
from zipfile import ZipFile
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_extracts_plain_text_without_persisting_upload():
    response = client.post('/api/documents/extract', files={'file': ('notes.md', b'# Notes\nImportant next step', 'text/markdown')})
    assert response.status_code == 200
    payload = response.json()
    assert payload['ok'] is True
    assert 'Important next step' in payload['text']


def test_extracts_word_document_text():
    raw = BytesIO()
    with ZipFile(raw, 'w') as archive:
        archive.writestr('word/document.xml', '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hello Word document</w:t></w:r></w:p></w:body></w:document>''')
    response = client.post('/api/documents/extract', files={'file': ('brief.docx', raw.getvalue(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
    assert response.status_code == 200
    assert 'Hello Word document' in response.json()['text']


def test_images_receive_honest_next_step_not_fake_analysis():
    response = client.post('/api/documents/extract', files={'file': ('photo.png', b'not-a-real-png', 'image/png')})
    assert response.status_code == 415
    assert 'Image understanding is not active' in response.json()['detail']
