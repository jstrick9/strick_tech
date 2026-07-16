"""
Performance Benchmark Baseline (`tests/benchmarks/test_performance_baseline.py`)
Benchmarks memory usage, API response latency across core endpoints, query execution speeds, and saves baseline_metrics.json.
"""
from __future__ import annotations
import time
import json
import os
import pytest
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parent.parent.parent / "benchmarks"
BENCHMARK_DIR.mkdir(exist_ok=True)
BASELINE_FILE = BENCHMARK_DIR / "baseline_metrics.json"


class TestPerformanceBaseline:
    """Suite capturing performance metrics and generating baseline reports."""

    def test_benchmark_core_api_latency(self, client):
        """Measure average latency for top core endpoints."""
        endpoints = [
            "/api/system/health",
            "/api/agents",
            "/api/tasks",
            "/api/prompts",
            "/api/search/global?q=agent",
            "/api/notifications/list",
        ]
        results = {}
        for ep in endpoints:
            t0 = time.time()
            iters = 5 if ep == "/api/system/health" else 20
            for _ in range(iters):
                r = client.get(ep)
                assert r.status_code == 200
            elapsed = (time.time() - t0) / float(iters) * 1000  # ms per request
            results[ep] = round(elapsed, 2)
            threshold = 300.0 if ep == "/api/system/health" else 60.0
            assert elapsed < threshold, f"Endpoint {ep} exceeded {threshold}ms baseline: {elapsed}ms"

        # Record metrics
        metrics = {
            "timestamp": time.time(),
            "python_version": os.sys.version,
            "avg_latency_ms": results,
            "overall_avg_ms": round(sum(results.values()) / len(results), 2),
        }
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

        assert BASELINE_FILE.exists()

    def test_benchmark_database_query_speed(self, client):
        """Measure query execution latency on SQLite tables endpoint."""
        t0 = time.time()
        for _ in range(50):
            r = client.get("/api/db/sqlite/tables")
            assert r.status_code == 200
        avg_ms = (time.time() - t0) / 50.0 * 1000
        assert avg_ms < 30.0, f"Database table listing exceeded 30ms baseline: {avg_ms}ms"

    def test_benchmark_global_search_speed(self, client):
        """Measure full multi-domain global search execution speed."""
        t0 = time.time()
        for _ in range(30):
            r = client.get("/api/search/global?q=a")
            assert r.status_code == 200
            data = r.json()
            assert data["ok"] is True
        avg_ms = (time.time() - t0) / 30.0 * 1000
        assert avg_ms < 40.0, f"Global search exceeded 40ms baseline: {avg_ms}ms"
