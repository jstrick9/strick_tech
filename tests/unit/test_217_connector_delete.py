"""
Unit Tests — Custom connector deletion (#135)

POST /api/connectors registers a custom connector into connector_registry,
but until this fix there was no inverse: DELETE /api/connectors/{id} was a
405 (no route) and the pane offered no remove control, so every registration
— including typo'd ones — was permanent clutter. These tests pin the new
DELETE route's contract:

  * built-in connectors are protected (400, never deleted)
  * custom connectors delete cleanly (200, gone from the list)
  * unknown ids 404
  * the list marks rows with `custom: true/false` so the UI can show the
    delete control on user-registered rows only
"""
import uuid


class TestConnectorDelete:
    def test_builtin_connectors_cannot_be_deleted(self, client):
        r = client.delete("/api/connectors/conn_slack")
        assert r.status_code == 400
        assert "built-in" in r.json()["error"].lower()
        # and it is still listed
        names = [c["connector_id"] for c in client.get("/api/connectors").json()["connectors"]]
        assert "conn_slack" in names

    def test_custom_connector_deletes(self, client):
        reg = client.post("/api/connectors", json={
            "name": f"del_probe_{uuid.uuid4().hex[:6]}",
            "category": "custom",
            "auth_type": "none",
            "capabilities": ["ping"],
        }).json()
        assert reg["ok"] is True
        cid = reg["connector_id"]

        r = client.delete(f"/api/connectors/{cid}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

        ids = [c["connector_id"] for c in client.get("/api/connectors").json()["connectors"]]
        assert cid not in ids

    def test_delete_unknown_connector_404s(self, client):
        r = client.delete("/api/connectors/conn_definitely_not_registered_xyz")
        assert r.status_code == 404

    def test_list_marks_custom_rows(self, client):
        reg = client.post("/api/connectors", json={
            "name": f"flag_probe_{uuid.uuid4().hex[:6]}",
            "category": "custom",
            "auth_type": "none",
        }).json()
        cid = reg["connector_id"]
        try:
            rows = {c["connector_id"]: c for c in client.get("/api/connectors").json()["connectors"]}
            assert rows[cid].get("custom") is True
            assert rows["conn_slack"].get("custom") is False
        finally:
            client.delete(f"/api/connectors/{cid}")

    def test_delete_twice_second_is_404(self, client):
        reg = client.post("/api/connectors", json={
            "name": f"twice_probe_{uuid.uuid4().hex[:6]}",
        }).json()
        cid = reg["connector_id"]
        assert client.delete(f"/api/connectors/{cid}").status_code == 200
        assert client.delete(f"/api/connectors/{cid}").status_code == 404
