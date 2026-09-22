"""Cluster node registry: stale workers must not live forever.

A worker that joined once stayed in _CLUSTER_NODES forever — nothing removed
an entry. GET /api/cluster/status counted node_count as total-ever-joined and
GET /api/cluster/nodes listed dead workers with live-looking status
indefinitely; a flood of distinct node_ids grew the registry without bound
(the same registry-leak class as collab #217 and crdt #227).

Workers whose heartbeat is stale past the TTL (600s — dispatch already treats
>120s as dead, so this is 5x grace) are evicted on join/status/list; a join
flood beyond the cap evicts the oldest workers first. The local master never
heartbeats (it IS this process) and is never evicted. All ageing is done by
manipulating last_heartbeat directly — no sleeps.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import cluster as cluster_module
from backend.routers.cluster import router as cluster_router


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(cluster_router)
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def registry():
    """A pristine registry with only the local master for every test."""
    saved = dict(cluster_module._CLUSTER_NODES)
    cluster_module._CLUSTER_NODES.clear()
    cluster_module._CLUSTER_NODES.update(saved)
    yield cluster_module._CLUSTER_NODES
    # drop test workers, keep the master
    for nid in [n for n, v in cluster_module._CLUSTER_NODES.items() if v.get("role") != "master"]:
        cluster_module._CLUSTER_NODES.pop(nid, None)


def _join(client, node_id, **caps):
    r = client.post("/api/cluster/nodes/join", json={
        "node_id": node_id, "name": node_id, "host_url": "http://127.0.0.1:1",
        "capabilities": {"gpu": "none", "vram_gb": 8, **caps},
    })
    assert r.status_code == 200, r.text
    return r.json()


def _age(registry, node_id, seconds=None):
    registry[node_id]["last_heartbeat"] -= (
        cluster_module._NODE_STALE_SECONDS + 60
    ) if seconds is None else seconds


class TestStaleNodeEviction:
    def test_stale_worker_is_evicted_on_status(self, client, registry):
        _join(client, "w1")
        _age(registry, "w1")
        r = client.get("/api/cluster/status")
        assert r.json()["node_count"] == 1  # master only
        assert "w1" not in registry

    def test_stale_worker_is_evicted_on_list_and_join(self, client, registry):
        _join(client, "w1")
        _age(registry, "w1")
        client.get("/api/cluster/nodes")
        assert "w1" not in registry
        _join(client, "w2")
        _age(registry, "w2")
        _join(client, "w3")  # join triggers the sweep too
        assert "w2" not in registry

    def test_master_is_never_evicted(self, client, registry):
        _age(registry, "node_master_local", seconds=cluster_module._NODE_STALE_SECONDS * 100)
        client.get("/api/cluster/nodes")
        assert "node_master_local" in registry, "the local master never heartbeats by design"

    def test_fresh_worker_survives(self, client, registry):
        _join(client, "w1")
        _age(registry, "w1", seconds=cluster_module._NODE_STALE_SECONDS - 1)
        client.get("/api/cluster/status")
        assert "w1" in registry

    def test_heartbeat_refresh_keeps_a_worker_alive(self, client, registry):
        _join(client, "w1")
        _age(registry, "w1")
        r = client.post("/api/cluster/nodes/w1/heartbeat",
                        json={"cpu_pct": 10, "vram_pct": 20, "active_tasks": 0, "status": "busy"})
        assert r.status_code == 200
        client.get("/api/cluster/status")
        assert "w1" in registry, "a node that still heartbeats is alive"

    def test_heartbeat_to_an_evicted_node_404s(self, client, registry):
        _join(client, "w1")
        registry.pop("w1")
        r = client.post("/api/cluster/nodes/w1/heartbeat",
                        json={"cpu_pct": 1, "vram_pct": 1, "active_tasks": 0, "status": "idle"})
        assert r.status_code == 404

    def test_rejoin_with_same_id_overwrites(self, client, registry):
        _join(client, "w1")
        _join(client, "w1")
        assert len(registry) == 2  # master + w1, no duplicate growth
        assert registry["w1"]["capabilities"]["vram_gb"] == 8

    def test_cap_evicts_oldest_workers_first(self, client, registry, monkeypatch):
        # join FIRST with the real cap, patch after — otherwise the join-time
        # sweep fires mid-setup with unordered registered_at values
        for i in range(4):
            _join(client, f"w{i}")
        monkeypatch.setattr(cluster_module, "_MAX_CLUSTER_NODES", 3)
        for i in range(4):
            registry[f"w{i}"]["registered_at"] = 1000.0 + i  # w0 oldest
        client.get("/api/cluster/nodes")
        # master + 4 workers at cap 3 -> the two oldest workers go
        assert "w0" not in registry and "w1" not in registry
        assert all(w in registry for w in ("w2", "w3"))
        assert "node_master_local" in registry

    def test_dispatch_still_finds_fresh_nodes(self, client, registry):
        _join(client, "w1")
        r = client.post("/api/cluster/dispatch", json={
            "task_prompt": "run inference", "required_vram_gb": 4,
        })
        assert r.status_code == 200
        assert r.json()["dispatched_to_node"] == "w1"
