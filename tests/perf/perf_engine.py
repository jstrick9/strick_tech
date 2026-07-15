"""
Agentic OS — Performance Test Engine

Provides:
  - Single-endpoint latency (P50/P95/P99)
  - Sustained throughput (RPS, concurrency)
  - Concurrent load stress tests
  - Memory/data-volume growth tests
  - Cascading multi-step scenario timing
  - SLA verification against defined thresholds
"""
from __future__ import annotations
import asyncio, json, statistics, time, uuid
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any
import httpx

BASE    = "http://127.0.0.1:8787"
TIMEOUT = 30

# ── SLA Thresholds (ms unless noted) ─────────────────────────────────────────
class SLA:
    # Latency thresholds
    HEALTH_P99      =   10   # Health endpoint must be <10ms p99
    READ_SIMPLE_P99 =   50   # Simple reads (list, get) <50ms p99
    READ_DB_P99     =  100   # DB-backed reads <100ms p99
    WRITE_P99       =  150   # Writes (create/update) <150ms p99
    COMPLEX_P99     =  500   # Complex ops (multi-join queries) <500ms p99
    
    # Throughput thresholds (RPS with 10 concurrent clients)
    HEALTH_MIN_RPS  =  500   # Health: ≥500 RPS
    READ_MIN_RPS    =  100   # Reads: ≥100 RPS
    WRITE_MIN_RPS   =   50   # Writes: ≥50 RPS
    
    # Reliability thresholds
    MIN_SUCCESS_RATE = 99.9  # ≥99.9% requests succeed (no 5xx)
    
    # Degradation thresholds
    MAX_DEGRADATION_PCT = 30  # Latency may not degrade >30% under load vs baseline


# ── Result dataclasses ────────────────────────────────────────────────────────
@dataclass
class LatencyResult:
    endpoint: str
    n:        int
    p50:      float
    p95:      float
    p99:      float
    avg:      float
    min_:     float
    max_:     float
    success:  int
    errors:   int
    
    @property
    def success_rate(self) -> float:
        total = self.success + self.errors
        return 100.0 * self.success / total if total else 0.0
    
    def check_sla(self, p99_threshold: float, label: str = "") -> tuple[bool, str]:
        ok = self.p99 <= p99_threshold and self.success_rate >= SLA.MIN_SUCCESS_RATE
        msg = (f"{'✅' if ok else '❌'} {label or self.endpoint}: "
               f"p99={self.p99:.1f}ms (≤{p99_threshold}ms), "
               f"ok={self.success_rate:.1f}%")
        return ok, msg


@dataclass
class ThroughputResult:
    endpoint:     str
    concurrency:  int
    duration_s:   float
    rps:          float
    p50:          float
    p95:          float
    total:        int
    ok_count:     int
    error_count:  int
    
    @property
    def success_rate(self) -> float:
        return 100.0 * self.ok_count / self.total if self.total else 0.0
    
    def check_sla(self, min_rps: float, label: str = "") -> tuple[bool, str]:
        ok = self.rps >= min_rps and self.success_rate >= SLA.MIN_SUCCESS_RATE
        msg = (f"{'✅' if ok else '❌'} {label or self.endpoint}: "
               f"rps={self.rps:.1f} (≥{min_rps}), "
               f"ok={self.success_rate:.1f}%")
        return ok, msg


@dataclass
class PerfReport:
    name:     str
    passed:   list[str] = field(default_factory=list)
    failed:   list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    def ok(self, msg: str):
        self.passed.append(msg)
    
    def fail(self, msg: str):
        self.failed.append(msg)
    
    def warn(self, msg: str):
        self.warnings.append(msg)
    
    def check(self, condition: bool, pass_msg: str, fail_msg: str):
        if condition:
            self.ok(pass_msg)
        else:
            self.fail(fail_msg)
    
    @property
    def total(self): return len(self.passed) + len(self.failed)
    
    @property
    def pass_rate(self): return 100.0 * len(self.passed) / self.total if self.total else 0.0
    
    def summary(self) -> str:
        lines = [
            f"\n{'═'*70}",
            f"  PERF REPORT: {self.name}",
            f"  Score: {len(self.passed)}/{self.total} ({self.pass_rate:.1f}%)",
            f"{'─'*70}",
        ]
        if self.failed:
            lines.append("  FAILURES:")
            for f in self.failed: lines.append(f"    ❌ {f}")
        if self.warnings:
            lines.append("  WARNINGS:")
            for w in self.warnings: lines.append(f"    ⚠️  {w}")
        lines.append(f"{'═'*70}")
        return "\n".join(lines)


# ── Core measurement functions ────────────────────────────────────────────────
async def measure_latency(
    path: str,
    method: str = "GET",
    body: dict | None = None,
    n: int = 30,
    warmup: int = 3,
) -> LatencyResult:
    """Measure single-endpoint latency statistics."""
    times, statuses = [], []
    
    async with httpx.AsyncClient(
        base_url=BASE, timeout=TIMEOUT,
        limits=httpx.Limits(max_connections=5, max_keepalive_connections=5)
    ) as c:
        # Warmup (not counted)
        for _ in range(warmup):
            try:
                if method == "GET": await c.get(path)
                else: await c.post(path, json=body or {})
            except Exception: pass
        
        # Measurements
        for _ in range(n):
            t0 = time.perf_counter()
            try:
                r = await (c.get(path) if method == "GET" else c.post(path, json=body or {}))
                statuses.append(r.status_code)
            except Exception:
                statuses.append(0)
            times.append((time.perf_counter() - t0) * 1000)
    
    times_sorted = sorted(times)
    ok = sum(1 for s in statuses if 200 <= s < 500)
    
    return LatencyResult(
        endpoint=f"{method} {path}",
        n=n,
        p50=times_sorted[n // 2],
        p95=times_sorted[min(int(n * 0.95), n-1)],
        p99=times_sorted[min(int(n * 0.99), n-1)],
        avg=statistics.mean(times),
        min_=min(times),
        max_=max(times),
        success=ok,
        errors=n - ok,
    )


async def measure_throughput(
    path: str,
    method: str = "GET",
    body: dict | None = None,
    duration_s: float = 5.0,
    concurrency: int = 10,
) -> ThroughputResult:
    """Measure sustained throughput under concurrent load."""
    times, statuses = [], []
    start = time.perf_counter()
    lock = asyncio.Lock()
    
    async def worker():
        async with httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:
            while time.perf_counter() - start < duration_s:
                t0 = time.perf_counter()
                try:
                    r = await (c.get(path) if method == "GET" else c.post(path, json=body or {}))
                    async with lock:
                        times.append((time.perf_counter() - t0) * 1000)
                        statuses.append(r.status_code)
                except Exception:
                    async with lock:
                        times.append(999.0)
                        statuses.append(0)
    
    await asyncio.gather(*[worker() for _ in range(concurrency)])
    
    total_s = time.perf_counter() - start
    ok = sum(1 for s in statuses if 200 <= s < 500)
    times_sorted = sorted(times)
    n = len(times)
    
    return ThroughputResult(
        endpoint=f"{method} {path}",
        concurrency=concurrency,
        duration_s=total_s,
        rps=n / total_s if total_s > 0 else 0,
        p50=times_sorted[n // 2] if n else 999,
        p95=times_sorted[min(int(n * 0.95), n-1)] if n else 999,
        total=n,
        ok_count=ok,
        error_count=n - ok,
    )


async def measure_concurrent_write(
    path: str,
    body_factory: Callable[[int], dict],
    concurrency: int = 20,
) -> dict:
    """Measure concurrency correctness: N simultaneous writes must all succeed."""
    ids, errors = [], []
    lock = asyncio.Lock()
    
    async def do_write(i: int):
        async with httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:
            try:
                r = await c.post(path, json=body_factory(i))
                if r.status_code in (200, 201):
                    d = r.json()
                    rid = d.get("id") or (d.get("agent") or d.get("workspace") or {}).get("id")
                    if rid:
                        async with lock: ids.append(rid)
                else:
                    async with lock: errors.append(r.status_code)
            except Exception as e:
                async with lock: errors.append(str(e)[:40])
    
    t0 = time.perf_counter()
    await asyncio.gather(*[do_write(i) for i in range(concurrency)])
    elapsed = (time.perf_counter() - t0) * 1000
    
    return {
        "total": concurrency,
        "succeeded": len(ids),
        "errors": len(errors),
        "unique_ids": len(set(ids)),
        "elapsed_ms": round(elapsed, 1),
        "ids": ids,
    }


async def measure_scenario(
    name: str,
    steps: list[tuple[str, str, dict | None]],
) -> dict:
    """Measure total time for a multi-step user scenario."""
    step_times = []
    step_names = []
    
    async with httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:
        for step_name, method_path, body in steps:
            parts = method_path.split(" ", 1)
            method, path = parts[0], parts[1]
            
            t0 = time.perf_counter()
            try:
                if method == "GET":
                    r = await c.get(path, params=body)
                elif method == "POST":
                    r = await c.post(path, json=body or {})
                elif method == "PATCH":
                    r = await c.patch(path, json=body or {})
                elif method == "DELETE":
                    r = await c.delete(path)
                else:
                    r = await c.get(path)
                elapsed = (time.perf_counter() - t0) * 1000
            except Exception as e:
                elapsed = 999.0
            
            step_times.append(elapsed)
            step_names.append(step_name)
    
    return {
        "scenario":   name,
        "total_ms":   round(sum(step_times), 1),
        "step_count": len(steps),
        "steps":      dict(zip(step_names, [round(t, 1) for t in step_times])),
        "slowest":    step_names[step_times.index(max(step_times))],
    }


async def GET(path: str, **params) -> httpx.Response:
    async with httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:
        return await c.get(path, params=params or None)

async def POST(path: str, body: dict = None) -> httpx.Response:
    async with httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:
        return await c.post(path, json=body or {})

async def DELETE(path: str) -> httpx.Response:
    async with httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:
        return await c.delete(path)


def uid(prefix="perf"): return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def PATCH(path: str, body: dict = None) -> httpx.Response:
    async with httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:
        return await c.patch(path, json=body or {})
