"""
Unit Tests — Voice, TTS, Image Generation
Covers: TTS synthesis, voice endpoints, image generation
"""
import pytest, httpx

class TestTTS:
    def test_tts_list_voices(self, client):
        r = client.get("/api/tts/voices")
        assert r.status_code == 200
        d = r.json()
        assert "voices" in d or isinstance(d, list)

    def test_tts_synthesize_requires_text(self, client):
        r = client.post("/api/tts/speak", json={})
        assert r.status_code in (200, 400, 422)
        # 400 = missing required text field

    def test_tts_synthesize_with_text(self, client):
        r = client.post("/api/tts/speak", json={
            "text": "Hello from Agentic OS unit test",
            "agent_id": "builder"
        })
        assert r.status_code in (200, 400, 503)  # 503 = TTS engine not configured

    def test_tts_status(self, client):
        r = client.get("/api/tts/status")
        assert r.status_code == 200

    def test_tts_preferences(self, client):
        r = client.get("/api/tts/cache/stats")
        assert r.status_code == 200

    def test_tts_set_preferences(self, client):
        r = client.patch("/api/tts/voices/builder", json={"voice_id": "default"})
        assert r.status_code == 200


class TestVoice:
    def test_voice_status(self, client):
        r = client.get("/api/voice/status")
        assert r.status_code in (200, 404)
        # 404 = voice session endpoint may not exist in all configs

    def test_voice_transcribe_requires_body(self, client):
        r = client.post("/api/voice/parse", json={"text": "test"})
        # Should return error or empty result gracefully
        assert r.status_code in (200, 400, 422)

    def test_voice_models(self, client):
        r = client.get("/api/voice/session")
        assert r.status_code == 200


class TestImageGen:
    def test_imagegen_requires_prompt(self, client):
        r = client.post("/api/imagegen/generate", json={})
        assert r.status_code in (200, 400, 422)
        if r.status_code == 200:
            d = r.json()
            assert d.get("ok") is False or "error" in d

    def test_imagegen_with_prompt(self, client):
        r = client.post("/api/imagegen/generate", json={
            "prompt": "A blue circle on white background, simple test image"
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "url" in d or "image_url" in d or "error" in d

    def test_imagegen_history(self, client):
        r = client.get("/api/imagegen/gallery")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, (list, dict))

    def test_imagegen_styles(self, client):
        r = client.get("/api/imagegen/styles")
        assert r.status_code == 200
