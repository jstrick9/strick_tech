"""
Agentic OS — Distributed Multi-Node Swarm Clustering Router (`/api/cluster`)
Manages node registration, heartbeats, and workload dispatching across local laptops and edge devices.
Created by Joshua Strickland and Strick Tech for Pro & Enterprise editions.
"""
from __future__ import annotations
import time
import uuid
from typing import Optional, Union, Any, Dict, List, Tuple, Set, Callable, AsyncGenerator
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/cluster", tags=["cluster"])

_CLUSTER_NODES: dict[str, dict[str, Any]] = {
    "node_master_local": {
        "node_id": "node_master_local",
        "name": "Local Master Node",
        "host_url": "http://127.0.0.1:8787",
        "role": "master",
        "status": "idle",
        "capabilities": {"gpu": "Local Silicon / CUDA", "vram_gb": 24, "models_loaded": ["llama3.1:8b", "qwen2.5:14b"]},
        "registered_at": time.time(),
        "last_heartbeat": time.time(),
        "tasks_completed": 0,
    }
}


class NodeJoinRequest(BaseModel):
    """Pydantic data model for NodeJoinRequest."""
    node_id: Optional[str] = None
    name: str = "Edge Worker Node"
    host_url: str = "http://192.168.1.100:8787"
    capabilities: dict[str, Any] = {"gpu": "Apple M3 Max / CUDA", "vram_gb": 16, "models_loaded": ["llama3.1:8b"]}
    auth_token: str = "stricktech_cluster_secret"


class HeartbeatRequest(BaseModel):
    """Pydantic data model for HeartbeatRequest."""
    cpu_pct: float = 15.2
    vram_pct: float = 42.0
    active_tasks: int = 0
    status: str = "idle"  # idle, busy, offline


class ClusterDispatchRequest(BaseModel):
    """Pydantic data model for ClusterDispatchRequest."""
    task_prompt: str
    target_node_id: Optional[str] = None
    required_vram_gb: int = 8
    priority: str = "normal"


@router.get("/status")
def get_cluster_status() -> dict[str, Any]:
    """Retrieve overall cluster health, compute node count, and aggregate VRAM/capabilities."""
    now = time.time()
    active_nodes = [n for n in _CLUSTER_NODES.values() if (now - n.get("last_heartbeat", 0)) < 120]
    total_vram = sum(n.get("capabilities", {}).get("vram_gb", 0) for n in active_nodes)
    return {
        "ok": True,
        "cluster_id": "stricktech_grid_01",
        "node_count": len(_CLUSTER_NODES),
        "active_nodes": len(active_nodes),
        "total_vram_gb": total_vram,
        "leader_node": "node_master_local",
        "creator": "Joshua Strickland and Strick Tech",
        "editions_supported": ["Pro", "Enterprise"],
        "timestamp": now,
    }


@router.post("/nodes/join")
def join_cluster(payload: NodeJoinRequest) -> dict[str, Any]:
    """Register and join a new edge compute node to the distributed swarm grid."""
    nid = (payload.node_id or f"node_{uuid.uuid4().hex[:8]}").strip().lower()
    _CLUSTER_NODES[nid] = {
        "node_id": nid,
        "name": payload.name,
        "host_url": payload.host_url,
        "role": "worker",
        "status": "idle",
        "capabilities": payload.capabilities,
        "registered_at": time.time(),
        "last_heartbeat": time.time(),
        "tasks_completed": 0,
    }
    return {
        "ok": True,
        "node_id": nid,
        "role": "worker",
        "message": f"Node '{nid}' successfully registered to cluster grid",
        "cluster_node_count": len(_CLUSTER_NODES),
    }


@router.get("/nodes")
def list_cluster_nodes() -> dict[str, Any]:
    """Retrieve all registered compute nodes and live status indicators."""
    return {"ok": True, "count": len(_CLUSTER_NODES), "nodes": list(_CLUSTER_NODES.values())}


@router.post("/nodes/{node_id}/heartbeat")
def node_heartbeat(node_id: str, payload: HeartbeatRequest) -> dict[str, Any]:
    """Record a heartbeat ping from an active worker node."""
    if node_id not in _CLUSTER_NODES:
        raise HTTPException(status_code=404, detail="Node not registered in cluster")
    _CLUSTER_NODES[node_id]["last_heartbeat"] = time.time()
    _CLUSTER_NODES[node_id]["cpu_pct"] = payload.cpu_pct
    _CLUSTER_NODES[node_id]["vram_pct"] = payload.vram_pct
    _CLUSTER_NODES[node_id]["active_tasks"] = payload.active_tasks
    _CLUSTER_NODES[node_id]["status"] = payload.status
    return {"ok": True, "node_id": node_id, "acknowledged": True}


@router.post("/dispatch")
def dispatch_swarm_task(payload: ClusterDispatchRequest) -> dict[str, Any]:
    """Dispatch a high-demand swarm task to the optimal available edge node."""
    now = time.time()
    active = [n for n in _CLUSTER_NODES.values() if (now - n.get("last_heartbeat", 0)) < 120 and n.get("status") == "idle"]
    if not active:
        # Fallback to local master node
        target = _CLUSTER_NODES["node_master_local"]
    else:
        # Pick node matching VRAM requirements
        suitable = [n for n in active if n.get("capabilities", {}).get("vram_gb", 0) >= payload.required_vram_gb]
        target = suitable[0] if suitable else active[0]

    task_id = f"task_{uuid.uuid4().hex[:8]}"
    target["tasks_completed"] = target.get("tasks_completed", 0) + 1
    return {
        "ok": True,
        "task_id": task_id,
        "dispatched_to_node": target["node_id"],
        "node_host": target["host_url"],
        "status": "executing",
        "message": f"Task dispatched to {target['name']} ({target['node_id']}) with {target.get('capabilities', {}).get('vram_gb', 0)}GB VRAM",
    }
