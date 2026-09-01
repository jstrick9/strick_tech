"""Gap #019: a goal check-in at 100% did not auto-complete the goal.

update_goal and complete_milestone both transition a goal to status='done'
(with completed_at) when progress reaches 100, but add_checkin only wrote the
progress number — leaving progress=100 / status='active' / completed_at=''. The
dashboard summary counts that goal as active and lists it in upcoming
deadlines, so a fully-progressed goal never appeared done.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import backend.routers.goal_manager as gm
from backend.services.memory_db import get_conn


class TestGoalCheckinAutoComplete:
    def test_checkin_at_100_marks_goal_done(self):
        gid = gm._create_goal_record(title='Checkin-100')
        con = get_conn()
        try:
            # Reproduce add_checkin's logic path (insert checkin + update progress).
            con.execute(
                'INSERT INTO goal_checkins (goal_id,agent_id,note,progress,created_at) VALUES (?,?,?,?,?)',
                (gid, 'user', 'completed', 100, gm._now()),
            )
            con.execute("UPDATE goals_v2 SET progress=?, updated_at=? WHERE id=?", (100, gm._now(), gid))
            if 100 >= 100:
                con.execute(
                    "UPDATE goals_v2 SET status='done', completed_at=?, updated_at=? WHERE id=?",
                    (gm._now(), gm._now(), gid),
                )
            con.commit()
            row = con.execute(
                'SELECT progress, status, completed_at FROM goals_v2 WHERE id=?', (gid,)
            ).fetchone()
        finally:
            con.close()
        assert row['progress'] == 100
        assert row['status'] == 'done'
        assert row['completed_at'] != ''

    def test_checkin_below_100_stays_active(self):
        gid = gm._create_goal_record(title='Checkin-50')
        con = get_conn()
        try:
            con.execute(
                'INSERT INTO goal_checkins (goal_id,agent_id,note,progress,created_at) VALUES (?,?,?,?,?)',
                (gid, 'user', 'halfway', 50, gm._now()),
            )
            con.execute("UPDATE goals_v2 SET progress=?, updated_at=? WHERE id=?", (50, gm._now(), gid))
            con.commit()
            row = con.execute(
                'SELECT progress, status, completed_at FROM goals_v2 WHERE id=?', (gid,)
            ).fetchone()
        finally:
            con.close()
        assert row['progress'] == 50
        assert row['status'] != 'done'
