"""Endpoint tests. Run with: pytest -q"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_create_and_fetch_item():
    r = client.post("/items", json={"name": "Write docs"})
    assert r.status_code == 201
    item = r.json()
    assert item["name"] == "Write docs"
    assert item["done"] is False

    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == item["id"]


def test_partial_update():
    item = client.post("/items", json={"name": "Ship it"}).json()
    r = client.patch(f"/items/{item['id']}", json={"done": True})
    assert r.status_code == 200
    assert r.json()["done"] is True
    # Unspecified fields are preserved.
    assert r.json()["name"] == "Ship it"


def test_filter_by_done():
    client.post("/items", json={"name": "open task"})
    done = client.post("/items", json={"name": "closed task"}).json()
    client.patch(f"/items/{done['id']}", json={"done": True})

    open_items = client.get("/items", params={"done": False}).json()
    assert all(i["done"] is False for i in open_items)


def test_missing_item_returns_404():
    assert client.get("/items/999999").status_code == 404
    assert client.delete("/items/999999").status_code == 404


def test_delete_removes_item():
    item = client.post("/items", json={"name": "temporary"}).json()
    assert client.delete(f"/items/{item['id']}").status_code == 204
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_validation_rejects_empty_name():
    assert client.post("/items", json={"name": ""}).status_code == 422
