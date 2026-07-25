"""
Agentic OS — Agent Execution Engine
═══════════════════════════════════
The core execution runtime for all AI agent operations. Provides:

- Loop Engineering: retry, backoff, circuit breaker, adaptive intervals
- Harness Engineering: test harnesses, evaluation harnesses, benchmark harnesses
- Execution Patterns: DAG, fan-out/fan-in, map-reduce, sequential, parallel
- State Machine: agent lifecycle management (spawn → configure → run → observe → retire)
- Resource Management: token budgets, rate limiting, cost tracking per agent
- Error Recovery: automatic retry with exponential backoff, fallback strategies
- Observability: structured execution traces, metrics, timing
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Awaitable, Optional

log = logging.getLogger('agentic.engine')


# ═══════════════════════════════════════════════════════════════════════════
#  ENUMS & CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

class AgentState(str, Enum):
    IDLE = "idle"
    CONFIGURING = "configuring"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING = "waiting"
    ERROR = "error"
    COMPLETED = "completed"
    RETIRED = "retired"


class ExecutionStrategy(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    DAG = "dag"
    FAN_OUT = "fan_out"
    FAN_IN = "fan_in"
    MAP_REDUCE = "map_reduce"
    LOOP = "loop"
    CONDITIONAL = "conditional"


class RetryStrategy(str, Enum):
    NONE = "none"
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIBONACCI = "fibonacci"


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject requests
    HALF_OPEN = "half_open" # Testing if recovered


# ═══════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    max_retries: int = 3
    base_delay_ms: float = 1000
    max_delay_ms: float = 30000
    backoff_factor: float = 2.0
    jitter: bool = True
    retry_on: list[str] = field(default_factory=lambda: ["timeout", "rate_limit", "server_error"])


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5
    recovery_timeout_s: float = 30.0
    half_open_max_calls: int = 3
    success_threshold: int = 2


@dataclass
class ResourceBudget:
    """Resource budget for agent execution."""
    max_tokens: int = 100000
    max_cost_usd: float = 1.0
    max_duration_s: float = 300.0
    max_iterations: int = 50
    max_parallel: int = 10


@dataclass
class LoopConfig:
    """Configuration for autonomous loop execution."""
    interval_s: float = 60.0
    adaptive: bool = False          # Adjust interval based on activity
    min_interval_s: float = 10.0
    max_interval_s: float = 3600.0
    backoff_on_error: bool = True
    max_consecutive_errors: int = 5
    cooldown_after_error_s: float = 60.0
    jitter_pct: float = 0.1         # ±10% randomization
    skip_if_still_running: bool = True


@dataclass
class HarnessConfig:
    """Configuration for agent test/evaluation harness."""
    name: str = ""
    test_cases: list[dict] = field(default_factory=list)
    timeout_per_case_s: float = 30.0
    parallel_cases: int = 1
    pass_threshold: float = 0.8     # 80% pass rate required
    retry_failed: bool = True
    max_retries_per_case: int = 2
    collect_metrics: bool = True
    output_format: str = "json"     # json, markdown, csv


# ═══════════════════════════════════════════════════════════════════════════
#  EXECUTION TRACE & METRICS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ExecutionStep:
    """A single step in an execution trace."""
    step_id: str
    name: str
    agent_id: str
    started_at: float
    completed_at: float = 0.0
    status: str = "running"
    input_summary: str = ""
    output_summary: str = ""
    tokens_used: int = 0
    cost_usd: float = 0.0
    error: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        end = self.completed_at or time.time()
        return (end - self.started_at) * 1000


@dataclass
class ExecutionTrace:
    """Full trace of an agent execution."""
    trace_id: str
    agent_id: str
    strategy: ExecutionStrategy
    started_at: float
    completed_at: float = 0.0
    status: str = "running"
    steps: list[ExecutionStep] = field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    error: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        end = self.completed_at or time.time()
        return (end - self.started_at) * 1000

    def add_step(self, name: str, agent_id: str, input_summary: str = "") -> ExecutionStep:
        step = ExecutionStep(
            step_id=f"step_{uuid.uuid4().hex[:8]}",
            name=name,
            agent_id=agent_id,
            started_at=time.time(),
            input_summary=input_summary[:200],
        )
        self.steps.append(step)
        return step

    def complete_step(self, step: ExecutionStep, output: str = "", tokens: int = 0, cost: float = 0.0, error: str = ""):
        step.completed_at = time.time()
        step.output_summary = output[:200] if output else ""
        step.tokens_used = tokens
        step.cost_usd = cost
        step.error = error
        step.status = "failed" if error else "completed"
        self.total_tokens += tokens
        self.total_cost_usd += cost

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "agent_id": self.agent_id,
            "strategy": self.strategy.value,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 1),
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "step_count": len(self.steps),
            "steps": [{
                "step_id": s.step_id,
                "name": s.name,
                "agent_id": s.agent_id,
                "status": s.status,
                "duration_ms": round(s.duration_ms, 1),
                "tokens_used": s.tokens_used,
                "cost_usd": round(s.cost_usd, 6),
                "error": s.error,
            } for s in self.steps],
            "error": self.error,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════════════════════════════════════
#  CIRCUIT BREAKER
# ═══════════════════════════════════════════════════════════════════════════

class CircuitBreaker:
    """Circuit breaker for LLM provider calls."""

    def __init__(self, config: CircuitBreakerConfig = None):
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.half_open_calls = 0

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.config.recovery_timeout_s:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.config.half_open_max_calls
        return False

    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        else:
            self.failure_count = 0

    def record_failure(self):
        self.last_failure_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.success_count = 0
        else:
            self.failure_count += 1
            if self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN

    @property
    def status(self) -> dict:
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "can_execute": self.can_execute(),
        }


# ═══════════════════════════════════════════════════════════════════════════
#  RETRY ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class RetryEngine:
    """Configurable retry engine with multiple backoff strategies."""

    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number (0-indexed)."""
        import random

        cfg = self.config
        if cfg.strategy == RetryStrategy.NONE:
            return 0
        elif cfg.strategy == RetryStrategy.FIXED:
            delay = cfg.base_delay_ms
        elif cfg.strategy == RetryStrategy.EXPONENTIAL:
            delay = cfg.base_delay_ms * (cfg.backoff_factor ** attempt)
        elif cfg.strategy == RetryStrategy.LINEAR:
            delay = cfg.base_delay_ms * (attempt + 1)
        elif cfg.strategy == RetryStrategy.FIBONACCI:
            a, b = cfg.base_delay_ms, cfg.base_delay_ms
            for _ in range(attempt):
                a, b = b, a + b
            delay = b
        else:
            delay = cfg.base_delay_ms

        delay = min(delay, cfg.max_delay_ms)
        if cfg.jitter:
            delay *= (0.5 + random.random())
        return delay / 1000  # Convert to seconds

    def should_retry(self, attempt: int, error_type: str = "") -> bool:
        """Check if we should retry for this attempt and error type."""
        if attempt >= self.config.max_retries:
            return False
        if self.config.retry_on and error_type:
            return error_type in self.config.retry_on
        return True


# ═══════════════════════════════════════════════════════════════════════════
#  EXECUTION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class ExecutionEngine:
    """Core execution engine for agent operations.

    Provides:
    - Retry with configurable backoff
    - Circuit breaker for provider calls
    - Resource budget enforcement
    - Execution tracing
    - Multiple execution strategies
    """

    def __init__(self):
        self.circuit_breakers: dict[str, CircuitBreaker] = {}
        self.active_traces: dict[str, ExecutionTrace] = {}
        self.resource_usage: dict[str, dict] = {}

    def get_circuit_breaker(self, provider: str) -> CircuitBreaker:
        if provider not in self.circuit_breakers:
            self.circuit_breakers[provider] = CircuitBreaker()
        return self.circuit_breakers[provider]

    async def execute_with_retry(
        self,
        fn: Callable[..., Awaitable[Any]],
        *args,
        agent_id: str = "default",
        retry_config: RetryConfig = None,
        circuit_breaker_key: str = "",
        trace: ExecutionTrace = None,
        step_name: str = "execute",
        **kwargs,
    ) -> dict:
        """Execute a function with retry logic and circuit breaker.

        Args:
            fn: Async function to execute
            retry_config: Retry configuration
            circuit_breaker_key: Key for circuit breaker (e.g., 'openrouter', 'ollama')
            trace: Execution trace to record steps
            step_name: Name for the trace step

        Returns:
            {'ok': True, 'result': ..., 'attempts': N, 'trace_step': ...} or
            {'ok': False, 'error': ..., 'attempts': N}
        """
        retry = RetryEngine(retry_config or RetryConfig())
        cb = self.get_circuit_breaker(circuit_breaker_key) if circuit_breaker_key else None

        step = trace.add_step(step_name, agent_id) if trace else None
        last_error = ""
        attempts = 0

        for attempt in range(retry.config.max_retries + 1):
            attempts = attempt + 1

            # Check circuit breaker
            if cb and not cb.can_execute():
                last_error = f"Circuit breaker open for {circuit_breaker_key}"
                break

            try:
                result = await fn(*args, **kwargs)
                if cb:
                    cb.record_success()
                if trace and step:
                    output = str(result)[:200] if result else ""
                    tokens = result.get("tokens", 0) if isinstance(result, dict) else 0
                    cost = result.get("cost", 0) if isinstance(result, dict) else 0
                    trace.complete_step(step, output=output, tokens=tokens, cost=cost)
                return {
                    "ok": True,
                    "result": result,
                    "attempts": attempts,
                    "circuit_breaker": cb.status if cb else None,
                }
            except Exception as e:
                last_error = str(e)
                error_type = self._classify_error(e)
                if cb:
                    cb.record_failure()
                if trace and step:
                    trace.complete_step(step, error=last_error)

                if not retry.should_retry(attempt, error_type):
                    break

                delay = retry.get_delay(attempt)
                log.warning(
                    "Retry %d/%d for %s after %s (%.1fs delay): %s",
                    attempt + 1, retry.config.max_retries, step_name,
                    error_type, delay, last_error[:100],
                )
                await asyncio.sleep(delay)

        return {
            "ok": False,
            "error": last_error,
            "attempts": attempts,
            "circuit_breaker": cb.status if cb else None,
        }

    async def execute_dag(
        self,
        nodes: list[dict],
        edges: list[tuple[str, str]],
        executor: Callable[[dict], Awaitable[Any]],
        agent_id: str = "default",
        max_parallel: int = 5,
    ) -> dict:
        """Execute a DAG (Directed Acyclic Graph) of tasks.

        Args:
            nodes: List of {'id': str, 'name': str, 'config': dict}
            edges: List of (from_id, to_id) dependencies
            executor: Async function that executes a node
            max_parallel: Max concurrent node executions

        Returns:
            {'ok': True, 'results': {node_id: result}, 'duration_ms': float}
        """
        import asyncio

        trace = ExecutionTrace(
            trace_id=f"dag_{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            strategy=ExecutionStrategy.DAG,
            started_at=time.time(),
        )

        # Build adjacency and in-degree
        node_map = {n["id"]: n for n in nodes}
        in_degree = {n["id"]: 0 for n in nodes}
        children = {n["id"]: [] for n in nodes}
        for src, dst in edges:
            in_degree[dst] += 1
            children[src].append(dst)

        # Find root nodes (no dependencies)
        ready = [nid for nid, deg in in_degree.items() if deg == 0]
        results = {}
        semaphore = asyncio.Semaphore(max_parallel)
        completed = set()

        async def run_node(nid: str):
            async with semaphore:
                node = node_map[nid]
                step = trace.add_step(node.get("name", nid), agent_id)
                try:
                    result = await executor(node)
                    results[nid] = result
                    trace.complete_step(step, output=str(result)[:200])
                except Exception as e:
                    results[nid] = {"ok": False, "error": str(e)}
                    trace.complete_step(step, error=str(e))
                completed.add(nid)

        # Execute in topological order with parallelism
        while ready:
            batch = ready[:]
            ready = []
            await asyncio.gather(*[run_node(nid) for nid in batch])
            # Check which nodes are now ready
            for nid in batch:
                for child in children[nid]:
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        ready.append(child)

        trace.completed_at = time.time()
        trace.status = "completed"
        self.active_traces[trace.trace_id] = trace

        return {
            "ok": True,
            "results": results,
            "trace": trace.to_dict(),
            "duration_ms": round(trace.duration_ms, 1),
        }

    async def execute_fan_out(
        self,
        prompt: str,
        agents: list[dict],
        llm_fn: Callable,
        judge_fn: Callable = None,
    ) -> dict:
        """Fan-out execution: send same prompt to multiple agents in parallel.

        Args:
            prompt: The prompt to send to all agents
            agents: List of agent configs
            llm_fn: Async function(agent_config, prompt) -> result
            judge_fn: Optional async function to judge/select best result

        Returns:
            {'ok': True, 'results': [...], 'winner': ..., 'duration_ms': float}
        """
        trace = ExecutionTrace(
            trace_id=f"fanout_{uuid.uuid4().hex[:8]}",
            agent_id="orchestrator",
            strategy=ExecutionStrategy.FAN_OUT,
            started_at=time.time(),
        )

        async def run_agent(agent):
            step = trace.add_step(f"fan_out:{agent.get('id', 'unknown')}", agent.get("id", "unknown"))
            try:
                result = await llm_fn(agent, prompt)
                tokens = result.get("tokens", 0) if isinstance(result, dict) else 0
                cost = result.get("cost", 0) if isinstance(result, dict) else 0
                trace.complete_step(step, output=str(result)[:200], tokens=tokens, cost=cost)
                return {"agent_id": agent.get("id"), "result": result, "ok": True}
            except Exception as e:
                trace.complete_step(step, error=str(e))
                return {"agent_id": agent.get("id"), "error": str(e), "ok": False}

        results = await asyncio.gather(*[run_agent(a) for a in agents])

        # Judge winner if judge function provided
        winner = None
        if judge_fn:
            try:
                winner = await judge_fn(results)
            except Exception as e:
                log.warning("Judge function failed: %s", e)

        trace.completed_at = time.time()
        trace.status = "completed"
        self.active_traces[trace.trace_id] = trace

        return {
            "ok": True,
            "results": results,
            "winner": winner,
            "trace": trace.to_dict(),
            "duration_ms": round(trace.duration_ms, 1),
        }

    async def execute_map_reduce(
        self,
        items: list[Any],
        map_fn: Callable[[Any], Awaitable[Any]],
        reduce_fn: Callable[[list], Awaitable[Any]],
        max_parallel: int = 10,
    ) -> dict:
        """Map-reduce execution pattern.

        Args:
            items: Items to process
            map_fn: Async function to process each item
            reduce_fn: Async function to combine results
            max_parallel: Max concurrent map operations
        """
        trace = ExecutionTrace(
            trace_id=f"mr_{uuid.uuid4().hex[:8]}",
            agent_id="orchestrator",
            strategy=ExecutionStrategy.MAP_REDUCE,
            started_at=time.time(),
        )

        semaphore = asyncio.Semaphore(max_parallel)

        async def map_item(item):
            async with semaphore:
                step = trace.add_step("map", "orchestrator")
                try:
                    result = await map_fn(item)
                    trace.complete_step(step, output=str(result)[:200])
                    return result
                except Exception as e:
                    trace.complete_step(step, error=str(e))
                    return {"ok": False, "error": str(e)}

        # Map phase
        mapped = await asyncio.gather(*[map_item(item) for item in items])

        # Reduce phase
        step = trace.add_step("reduce", "orchestrator")
        try:
            reduced = await reduce_fn(list(mapped))
            trace.complete_step(step, output=str(reduced)[:200])
        except Exception as e:
            trace.complete_step(step, error=str(e))
            reduced = {"ok": False, "error": str(e)}

        trace.completed_at = time.time()
        trace.status = "completed"
        self.active_traces[trace.trace_id] = trace

        return {
            "ok": True,
            "mapped": mapped,
            "reduced": reduced,
            "trace": trace.to_dict(),
            "duration_ms": round(trace.duration_ms, 1),
        }

    def _classify_error(self, error: Exception) -> str:
        """Classify an error for retry decision making."""
        err_str = str(error).lower()
        if "timeout" in err_str or "timed out" in err_str:
            return "timeout"
        if "rate" in err_str and "limit" in err_str:
            return "rate_limit"
        if "429" in err_str:
            return "rate_limit"
        if "500" in err_str or "502" in err_str or "503" in err_str:
            return "server_error"
        if "connection" in err_str:
            return "connection_error"
        if "auth" in err_str or "401" in err_str or "403" in err_str:
            return "auth_error"
        return "unknown"

    def get_all_circuit_breakers(self) -> dict:
        """Get status of all circuit breakers."""
        return {k: v.status for k, v in self.circuit_breakers.items()}

    def get_trace(self, trace_id: str) -> Optional[dict]:
        """Get a trace by ID."""
        trace = self.active_traces.get(trace_id)
        return trace.to_dict() if trace else None

    def list_traces(self, limit: int = 50) -> list[dict]:
        """List recent traces."""
        traces = sorted(self.active_traces.values(), key=lambda t: t.started_at, reverse=True)
        return [t.to_dict() for t in traces[:limit]]


# ═══════════════════════════════════════════════════════════════════════════
#  LOOP ENGINEERING
# ═══════════════════════════════════════════════════════════════════════════

class LoopEngine:
    """Advanced loop execution with adaptive intervals, backoff, and health tracking."""

    def __init__(self):
        self.loops: dict[str, dict] = {}
        self.loop_health: dict[str, dict] = {}

    def create_loop(
        self,
        loop_id: str,
        name: str,
        fn: Callable,
        config: LoopConfig = None,
        agent_id: str = "default",
    ) -> dict:
        """Create a new autonomous loop."""
        config = config or LoopConfig()
        self.loops[loop_id] = {
            "id": loop_id,
            "name": name,
            "fn": fn,
            "config": config,
            "agent_id": agent_id,
            "state": AgentState.IDLE,
            "created_at": time.time(),
            "run_count": 0,
            "error_count": 0,
            "consecutive_errors": 0,
            "last_run_at": 0,
            "last_error": "",
            "current_interval_s": config.interval_s,
        }
        self.loop_health[loop_id] = {
            "avg_duration_ms": 0,
            "success_rate": 100.0,
            "token_usage": [],
            "cost_history": [],
        }
        return {"ok": True, "loop_id": loop_id, "interval_s": config.interval_s}

    async def run_loop_iteration(self, loop_id: str) -> dict:
        """Execute a single iteration of a loop with error handling."""
        loop = self.loops.get(loop_id)
        if not loop:
            return {"ok": False, "error": f"Loop {loop_id} not found"}

        config = loop["config"]
        if config.skip_if_still_running and loop["state"] == AgentState.RUNNING:
            return {"ok": True, "skipped": True, "reason": "still running"}

        loop["state"] = AgentState.RUNNING
        t0 = time.time()

        try:
            result = await loop["fn"]()
            duration_ms = (time.time() - t0) * 1000

            loop["state"] = AgentState.IDLE
            loop["run_count"] += 1
            loop["consecutive_errors"] = 0
            loop["last_run_at"] = time.time()

            # Adaptive interval: decrease if fast, increase if slow
            if config.adaptive:
                if duration_ms < 1000:
                    loop["current_interval_s"] = max(
                        config.min_interval_s,
                        loop["current_interval_s"] * 0.9
                    )
                elif duration_ms > 10000:
                    loop["current_interval_s"] = min(
                        config.max_interval_s,
                        loop["current_interval_s"] * 1.1
                    )

            # Update health
            health = self.loop_health[loop_id]
            health["avg_duration_ms"] = (
                health["avg_duration_ms"] * 0.9 + duration_ms * 0.1
            )
            total = loop["run_count"]
            health["success_rate"] = (
                (total - loop["error_count"]) / total * 100 if total else 100
            )

            return {
                "ok": True,
                "loop_id": loop_id,
                "duration_ms": round(duration_ms, 1),
                "run_count": loop["run_count"],
                "current_interval_s": loop["current_interval_s"],
            }

        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            loop["state"] = AgentState.ERROR
            loop["error_count"] += 1
            loop["consecutive_errors"] += 1
            loop["last_error"] = str(e)[:200]

            # Backoff on error
            if config.backoff_on_error:
                backoff_multiplier = min(loop["consecutive_errors"], 10)
                loop["current_interval_s"] = min(
                    config.max_interval_s,
                    config.cooldown_after_error_s * backoff_multiplier
                )

            # Circuit breaker: pause if too many consecutive errors
            if loop["consecutive_errors"] >= config.max_consecutive_errors:
                loop["state"] = AgentState.PAUSED
                log.warning(
                    "Loop %s paused after %d consecutive errors",
                    loop_id, loop["consecutive_errors"]
                )
                return {
                    "ok": False,
                    "loop_id": loop_id,
                    "error": str(e)[:200],
                    "paused": True,
                    "reason": f"Paused after {loop['consecutive_errors']} consecutive errors",
                }

            return {
                "ok": False,
                "loop_id": loop_id,
                "error": str(e)[:200],
                "duration_ms": round(duration_ms, 1),
                "consecutive_errors": loop["consecutive_errors"],
            }

    def get_loop_status(self, loop_id: str) -> Optional[dict]:
        """Get detailed loop status including health metrics."""
        loop = self.loops.get(loop_id)
        if not loop:
            return None
        health = self.loop_health.get(loop_id, {})
        return {
            "id": loop["id"],
            "name": loop["name"],
            "state": loop["state"].value if isinstance(loop["state"], AgentState) else loop["state"],
            "agent_id": loop["agent_id"],
            "run_count": loop["run_count"],
            "error_count": loop["error_count"],
            "consecutive_errors": loop["consecutive_errors"],
            "current_interval_s": loop["current_interval_s"],
            "last_run_at": loop["last_run_at"],
            "last_error": loop["last_error"],
            "health": health,
            "config": {
                "interval_s": loop["config"].interval_s,
                "adaptive": loop["config"].adaptive,
                "backoff_on_error": loop["config"].backoff_on_error,
                "max_consecutive_errors": loop["config"].max_consecutive_errors,
            },
        }

    def list_loops(self) -> list[dict]:
        """List all loops with their status."""
        return [self.get_loop_status(lid) for lid in self.loops]


# ═══════════════════════════════════════════════════════════════════════════
#  HARNESS ENGINEERING
# ═══════════════════════════════════════════════════════════════════════════

class HarnessEngine:
    """Test and evaluation harnesses for agents.

    Provides:
    - Test harness: run agents against test cases with assertions
    - Eval harness: score agent outputs against expected outputs
    - Benchmark harness: measure latency, throughput, cost
    - Regression harness: detect quality regressions over time
    """

    def __init__(self, execution_engine: ExecutionEngine = None):
        self.engine = execution_engine or ExecutionEngine()
        self.results: dict[str, list] = {}

    async def run_test_harness(
        self,
        harness_id: str,
        agent_fn: Callable[[dict], Awaitable[Any]],
        test_cases: list[dict],
        config: HarnessConfig = None,
    ) -> dict:
        """Run an agent against test cases and collect results.

        Args:
            harness_id: Unique ID for this harness run
            agent_fn: Async function(test_case) -> agent response
            test_cases: List of {'id', 'input', 'expected', 'assertions'}
            config: Harness configuration

        Returns:
            {'ok': True, 'passed': N, 'failed': N, 'pass_rate': float, 'results': [...]}
        """
        config = config or HarnessConfig()
        results = []
        passed = 0
        failed = 0

        trace = ExecutionTrace(
            trace_id=f"harness_{harness_id}_{uuid.uuid4().hex[:8]}",
            agent_id="harness",
            strategy=ExecutionStrategy.SEQUENTIAL,
            started_at=time.time(),
        )

        for tc in test_cases:
            tc_id = tc.get("id", f"tc_{uuid.uuid4().hex[:6]}")
            step = trace.add_step(f"test:{tc_id}", "harness")

            t0 = time.time()
            try:
                # Execute with timeout
                response = await asyncio.wait_for(
                    agent_fn(tc),
                    timeout=config.timeout_per_case_s,
                )
                duration_ms = (time.time() - t0) * 1000

                # Run assertions
                assertions_passed = True
                assertion_errors = []
                for assertion in tc.get("assertions", []):
                    try:
                        if isinstance(assertion, str):
                            # Simple string contains check
                            if assertion not in str(response):
                                assertions_passed = False
                                assertion_errors.append(f"Missing: {assertion}")
                        elif callable(assertion):
                            result = assertion(response)
                            if not result:
                                assertions_passed = False
                                assertion_errors.append(f"Assertion failed: {assertion.__name__}")
                    except Exception as ae:
                        assertions_passed = False
                        assertion_errors.append(str(ae))

                tc_passed = assertions_passed
                if tc_passed:
                    passed += 1
                else:
                    failed += 1

                results.append({
                    "id": tc_id,
                    "passed": tc_passed,
                    "duration_ms": round(duration_ms, 1),
                    "response_summary": str(response)[:200],
                    "assertion_errors": assertion_errors,
                })
                trace.complete_step(
                    step,
                    output=str(response)[:200],
                    error="; ".join(assertion_errors) if assertion_errors else "",
                )

            except asyncio.TimeoutError:
                failed += 1
                duration_ms = (time.time() - t0) * 1000
                results.append({
                    "id": tc_id,
                    "passed": False,
                    "duration_ms": round(duration_ms, 1),
                    "error": f"Timeout after {config.timeout_per_case_s}s",
                })
                trace.complete_step(step, error=f"Timeout after {config.timeout_per_case_s}s")

            except Exception as e:
                failed += 1
                duration_ms = (time.time() - t0) * 1000
                results.append({
                    "id": tc_id,
                    "passed": False,
                    "duration_ms": round(duration_ms, 1),
                    "error": str(e)[:200],
                })
                trace.complete_step(step, error=str(e)[:200])

        trace.completed_at = time.time()
        trace.status = "completed"
        self.engine.active_traces[trace.trace_id] = trace

        total = passed + failed
        pass_rate = (passed / total * 100) if total else 0

        # Store results for regression comparison
        self.results[harness_id] = self.results.get(harness_id, [])
        self.results[harness_id].append({
            "timestamp": time.time(),
            "pass_rate": pass_rate,
            "passed": passed,
            "failed": failed,
            "total": total,
        })

        return {
            "ok": True,
            "harness_id": harness_id,
            "passed": passed,
            "failed": failed,
            "total": total,
            "pass_rate": round(pass_rate, 1),
            "meets_threshold": pass_rate >= config.pass_threshold * 100,
            "threshold": config.pass_threshold * 100,
            "results": results,
            "trace": trace.to_dict(),
            "duration_ms": round(trace.duration_ms, 1),
        }

    async def run_benchmark_harness(
        self,
        harness_id: str,
        agent_fn: Callable,
        iterations: int = 100,
        concurrency: int = 1,
    ) -> dict:
        """Benchmark agent performance: latency, throughput, consistency.

        Args:
            harness_id: Unique ID
            agent_fn: Async function to benchmark
            iterations: Number of iterations
            concurrency: Concurrent callers
        """
        import statistics

        latencies = []
        errors = 0
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(i: int):
            async with semaphore:
                t0 = time.time()
                try:
                    await agent_fn()
                    latencies.append((time.time() - t0) * 1000)
                except Exception:
                    errors += 1

        t_start = time.time()
        await asyncio.gather(*[run_one(i) for i in range(iterations)])
        total_time = time.time() - t_start

        if not latencies:
            return {"ok": False, "error": "All iterations failed"}

        latencies.sort()
        return {
            "ok": True,
            "harness_id": harness_id,
            "iterations": iterations,
            "concurrency": concurrency,
            "errors": errors,
            "total_time_s": round(total_time, 2),
            "rps": round(iterations / total_time, 1) if total_time > 0 else 0,
            "latency": {
                "p50": round(latencies[len(latencies) // 2], 1),
                "p95": round(latencies[int(len(latencies) * 0.95)], 1),
                "p99": round(latencies[int(len(latencies) * 0.99)], 1),
                "avg": round(statistics.mean(latencies), 1),
                "min": round(min(latencies), 1),
                "max": round(max(latencies), 1),
            },
        }

    def get_regression_report(self, harness_id: str) -> dict:
        """Compare latest run against historical runs to detect regressions."""
        history = self.results.get(harness_id, [])
        if len(history) < 2:
            return {"ok": True, "message": "Not enough history for regression analysis", "runs": len(history)}

        latest = history[-1]
        previous = history[-2]
        delta = latest["pass_rate"] - previous["pass_rate"]

        return {
            "ok": True,
            "harness_id": harness_id,
            "latest_pass_rate": latest["pass_rate"],
            "previous_pass_rate": previous["pass_rate"],
            "delta": round(delta, 1),
            "regression_detected": delta < -5,  # >5% drop is a regression
            "total_runs": len(history),
        }


# ═══════════════════════════════════════════════════════════════════════════
#  SINGLETON INSTANCES
# ═══════════════════════════════════════════════════════════════════════════

_engine: Optional[ExecutionEngine] = None
_loop_engine: Optional[LoopEngine] = None
_harness_engine: Optional[HarnessEngine] = None


def get_engine() -> ExecutionEngine:
    global _engine
    if _engine is None:
        _engine = ExecutionEngine()
    return _engine


def get_loop_engine() -> LoopEngine:
    global _loop_engine
    if _loop_engine is None:
        _loop_engine = LoopEngine()
    return _loop_engine


def get_harness_engine() -> HarnessEngine:
    global _harness_engine
    if _harness_engine is None:
        _harness_engine = HarnessEngine(get_engine())
    return _harness_engine
