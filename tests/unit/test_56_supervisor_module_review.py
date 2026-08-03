"""
Unit Tests — Supervisor workstation module review
(`tests/unit/test_56_supervisor_module_review.py`)

Covers the Supervisor workstation: the orchestrator itself plus the seven tabs
folded into it by the consolidation (A2A, Agent Identity, HITL, Goals, Swarm,
Fusion, Fine-Tuning).

Regression guards for real defects found during the review:

1. Runs orphaned by a server restart stayed 'running' forever. Runs execute as
   in-process asyncio tasks with no owner across a restart and there was no
   startup reconciliation — 4 such runs were found stranded on this machine,
   still advertised as active in the UI and in /api/supervisor/stats.
2. A run in which NO model ever executed reported complete success: every task
   'done', run 'done', failed_count 0, and an outcome score of 0.7. The
   supervisor ignored the provider='stub'/ok=False flag that llm.complete()
   sets when no AI provider is configured.
3. The run status was hardcoded to 'done' regardless of failures, failed_count
   was never written at all, and the audit log recorded outcome='success'
   unconditionally.
4. Fine-tuning was entirely fabricated: /jobs/start wrote hardcoded metrics
   (step 150/150, train_loss 0.284) and reported "completed successfully"
   without training anything, and /hardware claimed 24GB of VRAM and an
   "Apple Silicon MLX / CUDA Hybrid" backend on every machine. No training
   library (torch/mlx/peft) exists in the dependency set at all.
5. 23 error paths across agent_identity/hitl/swarm/fusion returned HTTP 200.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_PY = (ROOT / 'backend' / 'routers' / 'supervisor.py').read_text(encoding='utf-8')
FINETUNE_PY = (ROOT / 'backend' / 'routers' / 'finetune.py').read_text(encoding='utf-8')
APP_PY = (ROOT / 'backend' / 'app.py').read_text(encoding='utf-8')
HITL_PY = (ROOT / 'backend' / 'routers' / 'hitl.py').read_text(encoding='utf-8')
IDENTITY_PY = (ROOT / 'backend' / 'routers' / 'agent_identity.py').read_text(encoding='utf-8')
SWARM_PY = (ROOT / 'backend' / 'routers' / 'swarm.py').read_text(encoding='utf-8')
FUSION_PY = (ROOT / 'backend' / 'routers' / 'fusion.py').read_text(encoding='utf-8')


def executable_source(src: str) -> str:
    """Strip comments AND docstrings, so assertions about REMOVED code are not
    satisfied by fix notes that deliberately quote the old values."""
    import ast
    import io
    import tokenize

    out = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        out.append(tok)
    stripped = tokenize.untokenize(out)
    tree = ast.parse(stripped)
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc_lines.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    return '\n'.join(
        ln for i, ln in enumerate(stripped.splitlines(), start=1) if i not in doc_lines
    )


class TestOrphanedRunReconciliation:
    """In-process asyncio runs cannot survive a restart — say so."""

    def test_reconcile_function_exists(self):
        from backend.routers.supervisor import reconcile_orphaned_runs

        assert callable(reconcile_orphaned_runs)

    def test_covers_every_in_flight_status(self):
        from backend.routers.supervisor import _IN_FLIGHT_STATUSES

        for status in ('decomposing', 'scheduled', 'running', 'synthesizing'):
            assert status in _IN_FLIGHT_STATUSES

    def test_runs_at_startup(self):
        assert 'reconcile_orphaned_runs' in APP_PY

    def test_marks_orphans_failed_with_a_reason(self):
        assert "status='failed'" in SUPERVISOR_PY
        assert 'Interrupted by a server restart' in SUPERVISOR_PY

    def test_also_clears_in_flight_tasks(self):
        """Otherwise the DAG view keeps showing active tasks for a dead run."""
        assert 'UPDATE supervisor_tasks' in SUPERVISOR_PY

    def test_reconciles_real_orphans(self, tmp_path, monkeypatch):
        import sqlite3

        import backend.routers.supervisor as sup

        db = tmp_path / 'probe.db'
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        con.executescript(sup._SCHEMA)
        for rid, status in [('r_run', 'running'), ('r_syn', 'synthesizing'), ('r_done', 'done')]:
            con.execute('INSERT INTO supervisor_runs(run_id,status) VALUES (?,?)', (rid, status))
        con.execute(
            "INSERT INTO supervisor_tasks(task_id,run_id,status) VALUES ('t1','r_run','running')"
        )
        con.commit()
        con.close()

        def fake_conn():
            c = sqlite3.connect(db)
            c.row_factory = sqlite3.Row
            return c

        monkeypatch.setattr(sup, '_get_conn', fake_conn)
        assert sup.reconcile_orphaned_runs() == 2

        c = fake_conn()
        rows = {r['run_id']: r['status'] for r in c.execute('SELECT run_id,status FROM supervisor_runs')}
        task = c.execute("SELECT status FROM supervisor_tasks WHERE task_id='t1'").fetchone()['status']
        c.close()
        assert rows == {'r_run': 'failed', 'r_syn': 'failed', 'r_done': 'done'}, 'completed runs must be untouched'
        assert task == 'failed'

    def test_is_idempotent(self, tmp_path, monkeypatch):
        import sqlite3

        import backend.routers.supervisor as sup

        db = tmp_path / 'probe2.db'
        con = sqlite3.connect(db)
        con.executescript(sup._SCHEMA)
        con.execute("INSERT INTO supervisor_runs(run_id,status) VALUES ('r','running')")
        con.commit()
        con.close()

        def fake_conn():
            c = sqlite3.connect(db)
            c.row_factory = sqlite3.Row
            return c

        monkeypatch.setattr(sup, '_get_conn', fake_conn)
        assert sup.reconcile_orphaned_runs() == 1
        assert sup.reconcile_orphaned_runs() == 0, 'a second pass must find nothing'


class TestStubRunsAreNotReportedAsSuccess:
    """A run where no model executed must not report a passing score."""

    def test_stub_flag_is_propagated_from_the_llm_layer(self):
        # The provider=='stub' literal now lives once, in the llm service.
        # Supervisor uses the shared llm.is_stub() helper instead of its own copy.
        assert 'llm_is_stub(result)' in SUPERVISOR_PY
        assert 'import is_stub as llm_is_stub' in SUPERVISOR_PY
        assert "'is_stub'" in SUPERVISOR_PY

    def test_a_stub_result_fails_the_task(self):
        assert "if exec_result.get('is_stub'):" in SUPERVISOR_PY
        assert 'No AI provider configured' in SUPERVISOR_PY

    def test_run_status_reflects_task_outcomes(self):
        """Was hardcoded to status='done' no matter how many tasks failed."""
        assert "final_status = 'failed'" in SUPERVISOR_PY
        assert "final_status = 'partial'" in SUPERVISOR_PY
        assert 'status=final_status' in SUPERVISOR_PY

    def test_failed_count_is_persisted(self):
        """failed_count was never written, so it was always 0."""
        assert 'failed_count=failed_count' in SUPERVISOR_PY

    def test_score_is_zero_when_nothing_completed(self):
        assert 'if done_count == 0:' in SUPERVISOR_PY
        assert 'eval_score = 0.0' in SUPERVISOR_PY

    def test_audit_outcome_is_not_hardcoded_success(self):
        assert "outcome='success' if final_status == 'done' else 'failure'" in SUPERVISOR_PY


class TestFineTuningIsHonest:
    """It reported successful training with no training library installed."""

    def test_hardware_is_actually_detected(self):
        assert 'def _detect_accelerator' in FINETUNE_PY
        assert 'nvidia-smi' in FINETUNE_PY

    def test_fabricated_hardware_claims_are_gone(self):
        code = executable_source(FINETUNE_PY)
        assert '"available_vram_gb": 24' not in code
        assert '"accelerator_detected": True' not in code

    def test_training_backend_is_probed(self):
        assert 'def _training_backend' in FINETUNE_PY
        assert 'importlib.util.find_spec' in FINETUNE_PY

    def test_job_refuses_without_a_training_backend(self):
        assert 'status_code=501' in FINETUNE_PY
        assert 'no training backend installed' in FINETUNE_PY

    def test_fabricated_metrics_are_gone(self):
        code = executable_source(FINETUNE_PY)
        assert '"train_loss": 0.284' not in code
        assert '"status": "completed"' not in code

    def test_detection_runs_without_crashing(self):
        from backend.routers.finetune import _detect_accelerator, _training_backend

        hw = _detect_accelerator()
        assert set(hw) == {'compute_backend', 'accelerator_detected', 'available_vram_gb'}
        assert isinstance(hw['accelerator_detected'], bool)
        assert isinstance(_training_backend()['training_available'], bool)


class TestTabRoutersUseRealStatusCodes:
    @pytest.mark.parametrize(
        'src,name',
        [(HITL_PY, 'hitl'), (IDENTITY_PY, 'agent_identity'), (SWARM_PY, 'swarm'), (FUSION_PY, 'fusion')],
    )
    def test_no_bare_ok_false_endpoint_returns(self, src, name):
        assert "return {'ok': False, 'error'" not in src, f'{name} still returns HTTP 200 on an error path'

    def test_hitl_uses_409_for_an_already_decided_interrupt(self):
        assert 'status_code=409' in HITL_PY

    def test_hitl_uses_403_for_traversal(self):
        assert 'status_code=403' in HITL_PY

    def test_identity_distinguishes_missing_from_forbidden(self):
        assert 'status_code=404' in IDENTITY_PY
        assert 'status_code=403' in IDENTITY_PY

    def test_validation_failures_are_400(self):
        assert 'status_code=400' in SWARM_PY
        assert 'status_code=400' in FUSION_PY
