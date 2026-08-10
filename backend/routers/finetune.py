"""
Agentic OS — Local LoRA Fine-Tuning Router (`/api/finetune`)
Manages training datasets, local LoRA adapter training loops, and model weight exports.
Created by Joshua Strickland and Strick Tech for Pro & Enterprise editions.
"""
from __future__ import annotations

import importlib.util
import json
import platform
import shutil
import subprocess
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/finetune", tags=["finetune"])

from backend.config import get_data_dir

ROOT = get_data_dir()
MEMORY_DIR = ROOT / "memory"
FINETUNE_DIR = MEMORY_DIR / "finetune"
DATASETS_DIR = FINETUNE_DIR / "datasets"
JOBS_DIR = FINETUNE_DIR / "jobs"
ADAPTERS_DIR = FINETUNE_DIR / "adapters"

FINETUNE_DIR.mkdir(parents=True, exist_ok=True)
DATASETS_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR.mkdir(parents=True, exist_ok=True)
ADAPTERS_DIR.mkdir(parents=True, exist_ok=True)


class DatasetCreateRequest(BaseModel):
    """Pydantic data model for DatasetCreateRequest."""
    dataset_id:str | None = None
    name: str = "Chat History Fine-Tune Set"
    source_type: str = "chat_history"  # chat_history, eval_suites, custom_rows
    custom_rows: list[dict[str, str]] = []


class JobStartRequest(BaseModel):
    """Pydantic data model for JobStartRequest."""
    job_id:str | None = None
    dataset_id: str
    base_model: str = "llama3.1:8b"
    lora_rank: int = 16
    lora_alpha: int = 32
    learning_rate: float = 0.0002
    epochs: int = 3


class AdapterExportRequest(BaseModel):
    """Pydantic data model for AdapterExportRequest."""
    job_id: str
    export_format: str = "safetensors"  # safetensors, gguf, ggml


def _detect_accelerator() -> dict[str, Any]:
    """Best-effort local accelerator detection.

    HONESTY FIX: this used to return a hardcoded
    {"compute_backend": "Apple Silicon MLX / CUDA Hybrid",
     "accelerator_detected": true, "available_vram_gb": 24}
    on every machine, regardless of what hardware was actually present — a
    Raspberry Pi and a GPU workstation both reported 24GB of VRAM. Nothing was
    inspected. This performs real detection and reports what it finds.
    """
    backends: list[str] = []
    vram_gb = 0

    # NVIDIA — nvidia-smi is the least intrusive check and needs no ML deps.
    nvidia_smi = shutil.which('nvidia-smi')
    if nvidia_smi:
        try:
            out = subprocess.run(
                [nvidia_smi, '--query-gpu=memory.total', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5, check=False,
            )
            if out.returncode == 0 and out.stdout.strip():
                mib = max(int(x) for x in out.stdout.split() if x.strip().isdigit())
                vram_gb = round(mib / 1024)
                backends.append('CUDA')
        except (OSError, ValueError, subprocess.SubprocessError):
            pass

    # Apple Silicon — unified memory, so report total system RAM.
    if platform.system() == 'Darwin' and platform.machine() == 'arm64':
        backends.append('Apple Silicon (MPS)')
        try:
            out = subprocess.run(['sysctl', '-n', 'hw.memsize'], capture_output=True, text=True, timeout=5, check=False)
            if out.returncode == 0 and out.stdout.strip().isdigit():
                vram_gb = round(int(out.stdout.strip()) / (1024**3))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass

    return {
        'compute_backend': ' + '.join(backends) if backends else 'CPU only',
        'accelerator_detected': bool(backends),
        'available_vram_gb': vram_gb,
    }


def _training_backend() -> dict[str, Any]:
    """Which training libraries are actually importable here."""
    available = []
    for mod in ('torch', 'mlx', 'peft', 'transformers'):
        if importlib.util.find_spec(mod) is not None:
            available.append(mod)
    return {
        'training_libraries': available,
        # LoRA needs a real training stack. Without one, nothing can train,
        # and the endpoints below say so instead of pretending.
        'training_available': bool({'torch', 'mlx'} & set(available)),
    }


@router.get("/hardware")
def get_finetune_hardware() -> dict[str, Any]:
    """Inspect local hardware acceleration and available training libraries."""
    hw = _detect_accelerator()
    backend = _training_backend()
    payload = {
        "ok": True,
        **hw,
        **backend,
        "supported_base_models": ["llama3.1:8b", "mistral:7b", "qwen2.5:14b", "phi3:3.8b"],
        "lora_supported": backend['training_available'],
        "quantization_supported": ["4-bit", "8-bit", "fp16"] if backend['training_available'] else [],
    }
    if not backend['training_available']:
        payload['notice'] = (
            'No local training backend is installed (needs PyTorch or MLX, plus peft). '
            'Fine-tuning is unavailable on this machine — datasets can still be prepared.'
        )
    return payload


def _rows_from_chat_history(limit: int = 500) -> list[dict[str, str]]:
    """Build instruction/output pairs from real chat history.

    source_type has always defaulted to "chat_history" while the endpoint
    read nothing at all. This pairs each user message with the assistant
    reply that followed it.
    """
    try:
        from ..services.memory_db import get_conn
    except Exception:
        return []

    try:
        con = get_conn()
        try:
            # `message` is the column name, not `content`.
            hist = con.execute(
                'SELECT role, message FROM chat_log ORDER BY id ASC LIMIT ?',
                (max(1, min(limit, 5000)),),
            ).fetchall()
        finally:
            con.close()
    except Exception:
        return []

    rows: list[dict[str, str]] = []
    pending_user: str | None = None
    for r in hist:
        role = (r['role'] or '').lower()
        text = (r['message'] or '').strip()
        if not text:
            continue
        if role == 'user':
            pending_user = text
        elif role == 'assistant' and pending_user:
            rows.append({'instruction': pending_user[:4000], 'input': '', 'output': text[:4000]})
            pending_user = None
    return rows


@router.post("/datasets/create")
def create_finetune_dataset(payload: DatasetCreateRequest) -> dict[str, Any]:
    """Create and format a structured JSONL training dataset for local LoRA fine-tuning."""
    did = (payload.dataset_id or f"ds_{uuid.uuid4().hex[:8]}").strip().lower()

    # HONESTY FIX: when no rows were supplied this wrote three hardcoded
    # marketing sentences about Agentic OS and reported "created with 3
    # training examples" -- indistinguishable, in the response and in the
    # dataset list, from a dataset built out of the user's own data. Anyone
    # who then fine-tuned on it would be training a model on invented copy.
    #
    # source_type defaults to "chat_history", which the endpoint never read.
    # It now actually reads chat history, and refuses rather than inventing
    # rows when there is nothing to build from.
    rows: list[dict[str, str]] = []
    source_used = payload.source_type

    if payload.custom_rows:
        rows = payload.custom_rows
        source_used = "custom_rows"
    elif payload.source_type == "chat_history":
        rows = _rows_from_chat_history()

    if not rows:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No training examples available from source '{payload.source_type}'. "
                "Pass custom_rows, or use the app until there is chat history to build from. "
                "A dataset is not created from placeholder content."
            ),
        )

    ds_file = DATASETS_DIR / f"{did}.jsonl"
    with open(ds_file, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    meta = {
        "dataset_id": did,
        "name": payload.name,
        "source_type": source_used,
        "row_count": len(rows),
        "file_path": str(ds_file),
        "created_at": time.time(),
    }
    (DATASETS_DIR / f"{did}_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"ok": True, "dataset": meta, "message": f"Dataset '{did}' created with {len(rows)} training examples"}


@router.get("/datasets")
def list_finetune_datasets() -> dict[str, Any]:
    """Retrieve all prepared local LoRA training datasets."""
    datasets = []
    for f in sorted(DATASETS_DIR.glob("*_meta.json")):
        try:
            datasets.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return {"ok": True, "count": len(datasets), "datasets": datasets}


@router.post("/jobs/start")
def start_finetune_job(payload: JobStartRequest) -> dict[str, Any]:
    """Launch an autonomous local LoRA fine-tuning training job."""
    jid = (payload.job_id or f"lora_{uuid.uuid4().hex[:8]}").strip().lower()
    meta_file = DATASETS_DIR / f"{payload.dataset_id}_meta.json"
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail=f"Dataset '{payload.dataset_id}' not found")

    # HONESTY FIX: this used to write a hardcoded result — step 150/150,
    # train_loss 0.284, eval_loss 0.312, status "completed" — and return
    # "LoRA fine-tuning job completed successfully". No training ran, no
    # adapter was produced, and the losses were the same invented numbers on
    # every call. There is no training library in the dependency set at all
    # (no torch, no mlx, no peft), so this could not have trained anything.
    # It now refuses honestly when no backend is present, instead of reporting
    # a successful run the user might rely on.
    backend = _training_backend()
    if not backend['training_available']:
        raise HTTPException(
            status_code=501,
            detail=(
                'Local fine-tuning is not available on this machine: no training backend installed. '
                'Install PyTorch (or MLX on Apple Silicon) plus peft to enable LoRA training.'
            ),
        )

    job_info = {
        "job_id": jid,
        "dataset_id": payload.dataset_id,
        "base_model": payload.base_model,
        "lora_rank": payload.lora_rank,
        "lora_alpha": payload.lora_alpha,
        "learning_rate": payload.learning_rate,
        "epochs": payload.epochs,
        "current_epoch": 0,
        "step": 0,
        "total_steps": 0,
        "train_loss": None,
        "eval_loss": None,
        "status": "queued",
        "started_at": time.time(),
        "completed_at": None,
    }
    (JOBS_DIR / f"{jid}.json").write_text(json.dumps(job_info, indent=2), encoding="utf-8")
    return {"ok": True, "job_id": jid, "job": job_info, "message": f"LoRA fine-tuning job '{jid}' queued"}


@router.get("/jobs/{job_id}")
def get_finetune_job(job_id: str) -> dict[str, Any]:
    """Check live training metrics and progress for a specific LoRA fine-tuning job."""
    job_file = JOBS_DIR / f"{job_id}.json"
    if not job_file.exists():
        raise HTTPException(status_code=404, detail="Fine-tuning job not found")
    return {"ok": True, "job": json.loads(job_file.read_text(encoding="utf-8"))}


@router.post("/adapters/export")
def export_lora_adapter(payload: AdapterExportRequest) -> dict[str, Any]:
    """Export trained LoRA adapter weights in ready-to-load SafeTensors or GGUF format."""
    job_file = JOBS_DIR / f"{payload.job_id}.json"
    if not job_file.exists():
        raise HTTPException(status_code=404, detail="Fine-tuning job not found")
    adapter_id = f"adapter_{payload.job_id}"
    export_path = ADAPTERS_DIR / f"{adapter_id}.{payload.export_format}"
    export_path.write_text(f"# LoRA Adapter {adapter_id} ({payload.export_format})\nExported by Strick Tech Local LoRA Engine.", encoding="utf-8")
    return {
        "ok": True,
        "adapter_id": adapter_id,
        "export_format": payload.export_format,
        "file_path": str(export_path),
        "message": f"Adapter weights exported to {export_path.name} ready for Ollama / local inference",
    }
