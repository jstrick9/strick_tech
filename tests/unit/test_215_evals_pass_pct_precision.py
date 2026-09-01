"""Gap #020: platform_eval_stats pass_pct used SQLite integer division.

SUM(...)*100/COUNT(*) in SQLite performs INTEGER division, so a 33.33% rate
was reported as 33 and 87.5% as 87 — percentages always under-reported (and
inconsistent with the same query's float avg_score). CAST to REAL first.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.routers import eval_framework as ef
from backend.services.memory_db import get_conn


class TestEvalPassPctPrecision:
    def test_pass_pct_is_not_truncated(self):
        con = get_conn()
        try:
            for pf, sc in [('pass', 0.7), ('fail', 0.3), ('fail', 0.2)]:
                con.execute(
                    "INSERT INTO eval_results(agent_id,pass_fail,overall_score,safety_score,task_completion,created_at)"
                    " VALUES (?,?,?,?,?,datetime('now'))",
                    ('pct_agent', pf, sc, 0.9, 0.8),
                )
            con.commit()
        finally:
            con.close()
        d = ef.platform_eval_stats()
        row = next((a for a in d.get('by_agent', []) if a['agent_id'] == 'pct_agent'), None)
        assert row is not None
        assert row['n'] == 3
        # 1/3 = 33.333% — must not truncate to 33.
        assert abs(row['pass_pct'] - (100.0 / 3.0)) < 1e-6
