"""
Tests for the Agent Execution Engine: loop engineering, harness engineering,
retry, circuit breaker, DAG execution, fan-out, map-reduce.
"""
import asyncio
import time
import pytest
import pytest_asyncio


class TestExecutionEngine:
    """Test the core execution engine."""

    def test_engine_status_endpoint(self, client):
        r = client.get('/api/engine/status')
        d = r.json()
        assert d.get('ok') is True
        assert 'circuit_breakers' in d

    def test_traces_endpoint(self, client):
        r = client.get('/api/engine/traces')
        d = r.json()
        assert d.get('ok') is True
        assert 'traces' in d

    def test_circuit_breakers_endpoint(self, client):
        r = client.get('/api/engine/circuit-breakers')
        d = r.json()
        assert d.get('ok') is True


class TestRetryEngine:
    def test_exponential_backoff(self):
        from backend.services.agent_engine import RetryEngine, RetryConfig, RetryStrategy
        engine = RetryEngine(RetryConfig(strategy=RetryStrategy.EXPONENTIAL, base_delay_ms=100, backoff_factor=2.0, jitter=False))
        d0 = engine.get_delay(0)
        d1 = engine.get_delay(1)
        d2 = engine.get_delay(2)
        assert d0 < d1 < d2
        assert abs(d0 - 0.1) < 0.01
        assert abs(d1 - 0.2) < 0.01
        assert abs(d2 - 0.4) < 0.01

    def test_fixed_backoff(self):
        from backend.services.agent_engine import RetryEngine, RetryConfig, RetryStrategy
        engine = RetryEngine(RetryConfig(strategy=RetryStrategy.FIXED, base_delay_ms=500, jitter=False))
        assert abs(engine.get_delay(0) - 0.5) < 0.01
        assert abs(engine.get_delay(5) - 0.5) < 0.01

    def test_max_retries_limit(self):
        from backend.services.agent_engine import RetryEngine, RetryConfig
        engine = RetryEngine(RetryConfig(max_retries=3))
        assert engine.should_retry(0) is True
        assert engine.should_retry(2) is True
        assert engine.should_retry(3) is False

    def test_retry_on_specific_errors(self):
        from backend.services.agent_engine import RetryEngine, RetryConfig
        engine = RetryEngine(RetryConfig(max_retries=3, retry_on=["timeout", "rate_limit"]))
        assert engine.should_retry(0, "timeout") is True
        assert engine.should_retry(0, "auth_error") is False

    def test_max_delay_cap(self):
        from backend.services.agent_engine import RetryEngine, RetryConfig, RetryStrategy
        engine = RetryEngine(RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL, base_delay_ms=1000,
            max_delay_ms=5000, backoff_factor=10, jitter=False,
        ))
        assert engine.get_delay(10) <= 5.0


class TestCircuitBreaker:
    def test_starts_closed(self):
        from backend.services.agent_engine import CircuitBreaker
        cb = CircuitBreaker()
        assert cb.can_execute() is True
        assert cb.state.value == "closed"

    def test_opens_after_threshold(self):
        from backend.services.agent_engine import CircuitBreaker, CircuitBreakerConfig
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        for _ in range(3):
            cb.record_failure()
        assert cb.can_execute() is False
        assert cb.state.value == "open"

    def test_recovers_after_timeout(self):
        from backend.services.agent_engine import CircuitBreaker, CircuitBreakerConfig
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, recovery_timeout_s=0.1))
        cb.record_failure()
        cb.record_failure()
        assert cb.can_execute() is False
        time.sleep(0.15)
        assert cb.can_execute() is True
        assert cb.state.value == "half_open"

    def test_success_resets_failure_count(self):
        from backend.services.agent_engine import CircuitBreaker, CircuitBreakerConfig
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0

    def test_half_open_to_closed_on_success(self):
        from backend.services.agent_engine import CircuitBreaker, CircuitBreakerConfig, CircuitState
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, recovery_timeout_s=0.05, success_threshold=2))
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.1)
        assert cb.can_execute() is True
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestLoopEngine:
    def test_create_loop(self):
        from backend.services.agent_engine import LoopEngine
        engine = LoopEngine()
        result = engine.create_loop("test_loop", "Test", lambda: None)
        assert result["ok"] is True
        assert result["loop_id"] == "test_loop"

    def test_list_loops(self):
        from backend.services.agent_engine import LoopEngine
        engine = LoopEngine()
        engine.create_loop("l1", "Loop 1", lambda: None)
        engine.create_loop("l2", "Loop 2", lambda: None)
        loops = engine.list_loops()
        assert len(loops) == 2

    def test_loop_status(self):
        from backend.services.agent_engine import LoopEngine
        engine = LoopEngine()
        engine.create_loop("test", "Test", lambda: None)
        status = engine.get_loop_status("test")
        assert status is not None
        assert status["run_count"] == 0
        assert status["state"] == "idle"

    @pytest.mark.asyncio
    async def test_run_loop_iteration_success(self):
        from backend.services.agent_engine import LoopEngine
        engine = LoopEngine()
        async def success_fn():
            return {"ok": True}
        engine.create_loop("test", "Test", success_fn)
        result = await engine.run_loop_iteration("test")
        assert result["ok"] is True
        assert result["run_count"] == 1

    @pytest.mark.asyncio
    async def test_run_loop_iteration_error_increments_count(self):
        from backend.services.agent_engine import LoopEngine
        engine = LoopEngine()
        async def error_fn():
            raise ValueError("test error")
        engine.create_loop("test", "Test", error_fn)
        result = await engine.run_loop_iteration("test")
        assert result["ok"] is False
        assert result["consecutive_errors"] == 1

    @pytest.mark.asyncio
    async def test_loop_pause_after_max_errors(self):
        from backend.services.agent_engine import LoopEngine, LoopConfig
        engine = LoopEngine()
        async def error_fn():
            raise ValueError("fail")
        config = LoopConfig(max_consecutive_errors=2)
        engine.create_loop("test", "Test", error_fn, config)
        await engine.run_loop_iteration("test")
        result = await engine.run_loop_iteration("test")
        assert result.get("paused") is True

    @pytest.mark.asyncio
    async def test_nonexistent_loop(self):
        from backend.services.agent_engine import LoopEngine
        engine = LoopEngine()
        result = await engine.run_loop_iteration("nonexistent")
        assert result["ok"] is False


class TestHarnessEngine:
    @pytest.mark.asyncio
    async def test_test_harness_pass(self):
        from backend.services.agent_engine import HarnessEngine
        engine = HarnessEngine()
        async def agent_fn(tc):
            return "hello"
        test_cases = [{"id": "tc1", "input": "hi", "assertions": ["hello"]}]
        result = await engine.run_test_harness("test1", agent_fn, test_cases)
        assert result["ok"] is True
        assert result["passed"] == 1
        assert result["pass_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_test_harness_fail(self):
        from backend.services.agent_engine import HarnessEngine
        engine = HarnessEngine()
        async def agent_fn(tc):
            return "wrong"
        test_cases = [{"id": "tc1", "input": "hi", "assertions": ["expected"]}]
        result = await engine.run_test_harness("test2", agent_fn, test_cases)
        assert result["ok"] is True
        assert result["failed"] == 1
        assert result["pass_rate"] == 0.0

    def test_regression_report_not_enough_history(self):
        from backend.services.agent_engine import HarnessEngine
        engine = HarnessEngine()
        report = engine.get_regression_report("nonexistent")
        assert report["ok"] is True
        assert "Not enough" in report["message"]


class TestGuardEngine:
    def test_validate_safe_output(self):
        from backend.services.agent_engine import GuardEngine
        engine = GuardEngine()
        result = engine.validate("Hello, how can I help you today?")
        assert result["ok"] is True
        assert result["blocked"] == 0

    def test_validate_blocks_api_key(self):
        from backend.services.agent_engine import GuardEngine
        engine = GuardEngine()
        result = engine.validate("Use this key: sk-or-v1-abc123")
        assert result["ok"] is False
        assert result["blocked"] >= 1

    def test_validate_blocks_system_prompt_leak(self):
        from backend.services.agent_engine import GuardEngine
        engine = GuardEngine()
        result = engine.validate("My system prompt says to be helpful")
        assert result["ok"] is False

    def test_validate_max_length_warns(self):
        from backend.services.agent_engine import GuardEngine, GuardRule
        engine = GuardEngine()
        engine.add_rule("test", GuardRule("short", "max_length", "10", "warn"))
        result = engine.validate("This is a very long string that exceeds ten characters", "test")
        assert result["ok"] is True  # warn, not block
        assert result["warnings"] >= 1

    def test_validate_json_valid(self):
        from backend.services.agent_engine import GuardEngine, GuardRule
        engine = GuardEngine()
        engine.add_rule("test", GuardRule("json", "json_valid", "", "block"))
        result = engine.validate('{"ok": true}', "test")
        assert result["ok"] is True

    def test_validate_json_invalid(self):
        from backend.services.agent_engine import GuardEngine, GuardRule
        engine = GuardEngine()
        engine.add_rule("test", GuardRule("json", "json_valid", "", "block"))
        result = engine.validate("not json", "test")
        assert result["ok"] is False


class TestCostEngine:
    def test_set_budget_and_record(self):
        from backend.services.agent_engine import CostEngine, ResourceBudget
        engine = CostEngine()
        engine.set_budget("agent1", ResourceBudget(max_tokens=1000, max_cost_usd=0.1))
        result = engine.record_usage("agent1", 100, 0.01)
        assert result["ok"] is True
        assert result["within_budget"] is True

    def test_budget_exceeded_warning(self):
        from backend.services.agent_engine import CostEngine, ResourceBudget
        engine = CostEngine()
        engine.set_budget("agent1", ResourceBudget(max_tokens=100, max_cost_usd=0.01))
        result = engine.record_usage("agent1", 95, 0.009)
        assert len(result["warnings"]) >= 1  # Near limit warning

    def test_get_usage(self):
        from backend.services.agent_engine import CostEngine
        engine = CostEngine()
        engine.record_usage("agent1", 50, 0.05)
        engine.record_usage("agent1", 30, 0.03)
        usage = engine.get_usage("agent1")
        assert usage["tokens"] == 80
        assert usage["calls"] == 2

    def test_reset_usage(self):
        from backend.services.agent_engine import CostEngine
        engine = CostEngine()
        engine.record_usage("agent1", 100, 0.1)
        engine.reset_usage("agent1")
        usage = engine.get_usage("agent1")
        assert usage["tokens"] == 0

    def test_recommend_model(self):
        from backend.services.agent_engine import CostEngine
        engine = CostEngine()
        assert "llama" in engine.recommend_model("simple")
        assert engine.recommend_model("complex") == "claude-opus"


class TestCheckpointEngine:
    def test_save_and_resume(self):
        from backend.services.agent_engine import CheckpointEngine
        engine = CheckpointEngine()
        result = engine.save_checkpoint("task1", "step1", {"data": "hello"})
        assert result["ok"] is True
        resumed = engine.resume_from_checkpoint("task1")
        assert resumed["ok"] is True
        assert resumed["state"]["data"] == "hello"
        assert resumed["step_name"] == "step1"

    def test_multiple_checkpoints(self):
        from backend.services.agent_engine import CheckpointEngine
        engine = CheckpointEngine()
        engine.save_checkpoint("task1", "step1", {"v": 1})
        engine.save_checkpoint("task1", "step2", {"v": 2})
        engine.save_checkpoint("task1", "step3", {"v": 3})
        resumed = engine.resume_from_checkpoint("task1")
        assert resumed["state"]["v"] == 3
        assert resumed["step_name"] == "step3"
        history = engine.get_checkpoint_history("task1")
        assert len(history) == 3

    def test_no_checkpoint(self):
        from backend.services.agent_engine import CheckpointEngine
        engine = CheckpointEngine()
        result = engine.resume_from_checkpoint("nonexistent")
        assert result["ok"] is False

    def test_clear_checkpoints(self):
        from backend.services.agent_engine import CheckpointEngine
        engine = CheckpointEngine()
        engine.save_checkpoint("task1", "step1", {"v": 1})
        engine.clear_checkpoints("task1")
        result = engine.resume_from_checkpoint("task1")
        assert result["ok"] is False


class TestPromptEngine:
    def test_register_and_render(self):
        from backend.services.agent_engine import PromptEngine
        engine = PromptEngine()
        engine.register_template("greet", "Hello {{name}}, welcome to {{platform}}!", "Greeting template", ["name", "platform"])
        result = engine.render("greet", {"name": "Joshua", "platform": "Agentic OS"})
        assert "Joshua" in result
        assert "Agentic OS" in result

    def test_chain_of_thought(self):
        from backend.services.agent_engine import PromptEngine
        engine = PromptEngine()
        result = engine.add_chain_of_thought("Solve this problem:")
        assert "step by step" in result.lower() or "Step" in result

    def test_list_templates(self):
        from backend.services.agent_engine import PromptEngine
        engine = PromptEngine()
        engine.register_template("t1", "Template 1", "First template")
        engine.register_template("t2", "Template 2", "Second template")
        templates = engine.list_templates()
        assert len(templates) == 2

    def test_few_shot_injection(self):
        from backend.services.agent_engine import PromptEngine
        engine = PromptEngine()
        engine.register_template("classify", "Classify: {{text}}", "Text classifier")
        engine.register_few_shots("classify", [
            {"input": "I love this!", "output": "positive"},
            {"input": "Terrible service", "output": "negative"},
        ])
        result = engine.render("classify", {"text": "Great product!"})
        assert "Example 1" in result
        assert "positive" in result
