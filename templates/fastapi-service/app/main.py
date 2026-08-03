"""FastAPI service entry point.

Run locally:
    pip install -r requirements.txt
    uvicorn app.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI

from .routes import router

app = FastAPI(
    title="FastAPI Service",
    description="A multi-file Python REST API scaffolded by Agentic OS.",
    version="0.1.0",
)

app.include_router(router)


@app.get("/health", tags=["system"])
def health() -> dict:
    """Liveness probe."""
    return {"ok": True, "service": "fastapi-service", "version": app.version}
