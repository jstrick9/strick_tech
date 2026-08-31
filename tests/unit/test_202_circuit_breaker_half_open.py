"""
Agent engine — circuit-breaker half-open admission limit regression.

A recovering (half-open) breaker must admit at most `half_open_max_calls`
probe requests before deciding open/closed. `half_open_calls` was set to 0 on
every transition but NEVER incremented, so the admission limit was dead:
`can_execute()` returned `0 < max` i.e. always True, letting unlimited
concurrent probes through while the breaker was still testing recovery.

Bug: after a breaker opens and the recovery timeout elapses, calling
`can_execute()` repeatedly always grants admission regardless of how many
probes have already been let in. Fix: count each admitted probe by
incrementing `half_open_calls` when a half-open execution is authorized, and
stop admitting once the configured probe budget is exhausted.
"""
from __future__ import annotations

import time

from backend.services.agent_engine import CircuitBreaker, CircuitBreakerConfig


def _make_breakers_ready() -> CircuitBreaker:
    """Return a breaker in the HALF_OPEN state (open, then recovery elapses)."""
    cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, recovery_timeout_s=0.1))
    cb.record_failure()
    cb.record_failure()
    assert cb.can_execute() is False  # still open
    time.sleep(0.15)
    return cb


class TestHalfOpenAdmission:
    def test_half_open_caps_probes(self):
        cb = _make_breakers_ready()
        # First probe after recovery is admitted and counted.
        assert cb.acquire() is True
        assert cb.state.value == "half_open"
        cb.record_success()  # a probe that succeeded

        # second probe admitted
        assert cb.acquire() is True
        cb.record_failure()  # flips back to OPEN

        cb = _make_breakers_ready()
        # Hold the breaker in half-open so the whole probe budget is exercised
        # (a low success_threshold would close it early and mask the bug).
        cb.config.success_threshold = cb.config.half_open_max_calls + 5
        admitted = 0
        for _ in range(cb.config.half_open_max_calls):
            if not cb.acquire():
                break
            cb.record_success()
            admitted += 1
        # Once the probe budget is exhausted, no more probes may be admitted
        # until a probe fails or the breaker closes.
        assert cb.acquire() is False, (
            f"half-open admitted {admitted}/{cb.config.half_open_max_calls} probes "
            "but still allowed another — the admission limit is not enforced."
        )

    def test_half_open_recovers_to_closed_after_probes(self):
        cb = _make_breakers_ready()
        for _ in range(cb.config.half_open_max_calls):
            if not cb.acquire():
                break
            cb.record_success()
            if cb.state.value == "closed":
                break
        # With a default success_threshold of 2, a couple of successful probes
        # close the breaker before the budget runs out.
        assert cb.state.value == "closed"

    def test_half_open_probe_failure_reopens(self):
        cb = _make_breakers_ready()
        assert cb.acquire() is True
        cb.record_failure()
        assert cb.state.value == "open"
        assert cb.can_execute() is False

    def test_status_reads_do_not_consume_probe_budget(self):
        """can_execute() (used by status/health reads) must be pure — it must
        not drain the half-open probe budget just by being inspected."""
        cb = _make_breakers_ready()
        # Reading status many times must not prevent actual execution.
        for _ in range(50):
            assert cb.can_execute() is True
        assert cb.acquire() is True  # still able to admit a real probe
        assert cb.half_open_calls == 1

    def test_probe_budget_respected_when_success_threshold_high(self):
        cb = _make_breakers_ready()
        cb.config.success_threshold = cb.config.half_open_max_calls + 5
        admitted = 0
        while cb.acquire():
            cb.record_success()
            admitted += 1
        assert admitted == cb.config.half_open_max_calls
