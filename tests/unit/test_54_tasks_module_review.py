"""
Unit Tests — Tasks / Kanban module review
(`tests/unit/test_54_tasks_module_review.py`)

Regression guards for real defects found during the Tasks review:

1. SECURITY (stored XSS): `task.agent` is fully user-controlled and fell
   through to the card's agent label, which was interpolated into both a
   title="" attribute and the card body WITHOUT escaping — while the title and
   description right beside it were escaped. Reproduced in jsdom: a task with
   agent='"><img src=x onerror=...>' rendered two live <img onerror> elements.
2. PATCH / DELETE / kanban-move / bulk_update all reported success for tasks
   that do not exist. The board uses response.ok to decide whether a drag was
   persisted, so a move of a stale card showed "Task moved" and silently
   reverted on the next reload.
3. The frontend never reverted optimistic updates when a save failed, and the
   delete handler never inspected the response at all.
4. Card ordering within a column was never persisted — `sort_order` existed in
   the schema and in bulk_update, but no UI code ever read or wrote it.
5. ARCHITECTURE: the endpoints lived inline in app.py rather than in a router.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_PY = (ROOT / 'backend' / 'app.py').read_text(encoding='utf-8')
TASKS_PY = (ROOT / 'backend' / 'routers' / 'tasks.py').read_text(encoding='utf-8')
KANBAN_JS = (ROOT / 'frontend' / 'js' / '28-kanban.js').read_text(encoding='utf-8')

# Assertions about REMOVED code must inspect executable lines only — the fix
# comments deliberately quote the old buggy code to explain what changed.
KANBAN_CODE = '\n'.join(
    ln for ln in KANBAN_JS.splitlines() if not ln.lstrip().startswith(('//', '*', '/*'))
)


class TestTasksExtractedToRouter:
    """Endpoints belong in a router, not inline in the app entry point."""

    def test_router_module_exists_with_all_endpoints(self):
        assert (ROOT / 'backend' / 'routers' / 'tasks.py').is_file()
        assert TASKS_PY.count('@router.') == 8

    def test_app_no_longer_defines_task_routes(self):
        for route in ("@app.get('/api/kanban')", "@app.get('/api/tasks')", "@app.post('/api/tasks')",
                      "@app.delete('/api/tasks/{task_id}')", "@app.post('/api/kanban/move')"):
            assert route not in APP_PY, f'{route} should have moved to the tasks router'

    def test_router_is_registered(self):
        assert 'from .routers.tasks import router as tasks_router' in APP_PY
        assert 'app.include_router(tasks_router)' in APP_PY

    def test_app_py_no_longer_contains_task_crud(self):
        # Was 988 lines with the task CRUD inline. The line-count proxy broke
        # when cross-cutting hardening (CSRF enforcement, rate-limit eviction)
        # legitimately ADDED lines to app.py — a size threshold measures the
        # wrong thing. Assert the actual property: the task CRUD lives in its
        # own router and is not back in app.py.
        assert "@app.get('/api/tasks')" not in APP_PY
        assert "@app.post('/api/tasks')" not in APP_PY
        assert 'tasks_router' in APP_PY, 'the extracted router must still be mounted' 

    def test_relative_import_is_correct_for_router_depth(self):
        """`from .routers.websocket` was valid in app.py but wrong one level
        deeper — it raised ModuleNotFoundError, which the surrounding broad
        except swallowed, so task creation 500'd with no clear cause."""
        assert 'from .routers.websocket import' not in TASKS_PY
        assert 'from .websocket import broadcast_task_update' in TASKS_PY

    def test_app_still_imports(self):
        import backend.app  # noqa: F401


class TestMissingTasksReportFailure:
    """Endpoints must not claim success for rows that do not exist."""

    def test_patch_checks_rowcount(self):
        assert 'if cur.rowcount == 0:' in TASKS_PY
        assert TASKS_PY.count("'Task not found'") >= 3

    def test_delete_checks_rowcount(self):
        idx = TASKS_PY.index('def tasks_delete')
        body = TASKS_PY[idx:idx + 900]
        assert 'cur.rowcount' in body
        assert 'status_code=404' in body

    def test_move_checks_rowcount(self):
        # UPDATED: this sliced a fixed 1,200 characters from the function.
        # Module review 5 lengthened the 400 error message -- explaining that
        # the endpoint accepts id/task_id and to_status/status, rather than
        # naming one spelling of each -- and pushed `cur.rowcount` past the
        # window. The behaviour was unchanged; the window was the fragile part.
        #
        # It now slices to the NEXT route, so the assertion covers the whole
        # handler however long its copy becomes.
        idx = TASKS_PY.index('def kanban_move')
        rest = TASKS_PY[idx:]
        nxt = rest.find('@router.', 1)
        body = rest[:nxt] if nxt != -1 else rest
        assert 'cur.rowcount' in body
        assert 'status_code=404' in body

    def test_move_rejects_non_integer_id(self):
        """int(tid) on a non-numeric id raised an unhandled ValueError -> 500."""
        assert "'id must be an integer'" in TASKS_PY

    def test_bulk_update_counts_rows_not_statements(self):
        assert 'if cur.rowcount:' in TASKS_PY
        assert "'missing': missing" in TASKS_PY

    def test_validation_failures_use_400(self):
        assert TASKS_PY.count('status_code=400') >= 3

    def test_connections_are_closed_on_error(self):
        """PATCH/DELETE/move had no try/finally — an exception leaked the
        SQLite connection."""
        assert TASKS_PY.count('finally:') >= 4


class TestCardEscaping:
    """Stored XSS via the agent field."""

    def test_agent_label_is_escaped_in_body_and_attribute(self):
        assert 'const agentLabel = kanbanEscapeHtml(agent.label);' in KANBAN_JS
        assert 'const agentLabelAttr = kanbanEscapeAttr(' in KANBAN_JS

    def test_raw_agent_interpolation_is_gone(self):
        assert 'title="${agent.label}">${agent.icon} ${agent.label}' not in KANBAN_CODE

    def test_unknown_agent_icon_is_also_escaped(self):
        assert 'const agentIcon = known ? agent.icon : kanbanEscapeHtml(agent.icon);' in KANBAN_JS

    def test_title_and_description_remain_escaped(self):
        assert 'kanbanEscapeHtml(task.title)' in KANBAN_JS
        assert 'kanbanEscapeHtml(task.description)' in KANBAN_JS


class TestOptimisticUpdatesRollBack:
    """A failed save must never leave the board disagreeing with the server."""

    def test_drag_and_drop_reverts_on_failure(self):
        assert 'const previousStatus = task.status;' in KANBAN_JS
        assert 'task.status = previousStatus;' in KANBAN_JS

    def test_drag_and_drop_resyncs_on_404(self):
        assert 'That task no longer exists' in KANBAN_JS

    def test_edit_reverts_on_failure(self):
        assert 'const snapshot = { ...task };' in KANBAN_JS
        assert 'Object.assign(task, snapshot);' in KANBAN_JS

    def test_delete_inspects_the_response(self):
        """`await fetch(...)` was followed unconditionally by a success toast."""
        idx = KANBAN_CODE.index('async function kanbanDeleteTask')
        body = KANBAN_CODE[idx:idx + 2200]
        assert 'response.ok' in body
        assert 'Could not delete task' in body

    def test_delete_restores_the_card_on_failure(self):
        assert 'kanbanTasks = kanbanTasks.concat(removed);' in KANBAN_JS

    def test_create_does_not_fabricate_local_only_tasks(self):
        """The catch block invented `id: Date.now()` and claimed success; those
        cards vanished on reload and could never match a real row."""
        assert 'taskData.id = Date.now();' not in KANBAN_CODE
        assert 'Task created (local)' not in KANBAN_CODE

    def test_create_checks_the_response_body_not_just_status(self):
        """POST /api/tasks used to return 200 with {"ok": false}."""
        assert 'result.ok === false' in KANBAN_JS


class TestOrderingPersists:
    """sort_order existed everywhere except the UI."""

    def test_board_sorts_by_sort_order(self):
        assert 'a.sort_order' in KANBAN_JS and 'b.sort_order' in KANBAN_JS

    def test_drop_position_is_computed(self):
        assert 'function kanbanDropIndex(' in KANBAN_JS
        assert 'box.top + box.height / 2' in KANBAN_JS

    def test_reorder_is_persisted_via_bulk_update(self):
        assert 'async function kanbanPersistOrder(' in KANBAN_JS
        assert "fetch('/api/tasks/bulk_update'" in KANBAN_JS

    def test_same_column_drop_is_no_longer_ignored(self):
        """Dropping inside the same column used to early-return."""
        assert 'Kanban: Task already in this column' not in KANBAN_CODE

    def test_failed_reorder_resyncs_from_server(self):
        assert 'Order not saved' in KANBAN_JS
