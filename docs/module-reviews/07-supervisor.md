# Module Review 07 — Supervisor workstation

**Reviewed:** 2026-08-03 · **Commit:** `b9da4cd` · **Sidebar position:** Supervisor (AI TOOLS)

**Scope:** the largest workstation in the platform — the orchestrator plus the seven tabs
folded into it by the consolidation:

| Router | Lines | Endpoints |
|---|---|---|
| `supervisor.py` | 1,051 | 8 |
| `a2a.py` | 1,561 | 16 |
| `goal_manager.py` | 1,282 | 17 |
| `agent_identity.py` | 691 | 14 |
| `fusion.py` | 632 | 9 |
| `hitl.py` | 505 | 10 |
| `swarm.py` | 271 | 3 |
| `finetune.py` | 171 | 6 |
| **Total** | **~6,100** | **83** |

Verified live, including against a real local model (Ollama + qwen2.5:0.5b).

---

## Findings

### 🔴 1. Runs orphaned by a restart stayed "running" forever

Supervisor runs execute as in-process `asyncio` tasks. Nothing owns them across a restart,
and there was **no startup reconciliation** — so anything in flight when the server stopped
stayed `running` in the database permanently.

I found **4 such runs stranded on this machine**, the oldest for hours:

```
srun_3b2172d7b0 | running      | 16:03
srun_446a96c2ff | synthesizing | 16:05
srun_b92c8c4149 | running      | 16:08
srun_f1227d72c5 | decomposing  | 16:10
```

All still advertised as active in the UI and counted by `/api/supervisor/stats`. A user
watching one would wait indefinitely for a run that no longer exists.

**Fixed** — `reconcile_orphaned_runs()` runs from the app lifespan, marking in-flight runs
(and their in-flight tasks) failed with an honest reason. Verified by restarting with 4
orphans present: all cleared, completed runs untouched, and the pass is idempotent.

### 🔴 2. Runs where no model executed reported complete success

`llm.complete()` returns a placeholder tagged `provider='stub'`/`ok=False` when no provider
is configured. **The supervisor ignored that flag entirely.**

A 3-task run with no API key produced:

```
status: done | done_count: 3 | failed_count: 0 | eval_score: 0.7
output: "⚠️ No OPENROUTER_API_KEY set. To enable real AI responses…"
```

A passing grade, three "completed" tasks, and the API-key notice as the work product.

Three compounding bugs made this worse:
- run status was **hardcoded** to `'done'` regardless of failures
- `failed_count` was **never written** — always 0, even when every task errored
- the audit log recorded `outcome='success'` unconditionally

**Fixed** — stub results fail the task; status resolves to `done`/`partial`/`failed` from
real counts; `failed_count` is persisted; the score is 0.0 when nothing completed; the audit
outcome follows. Verified both directions against a live model:

| Scenario | Before | After |
|---|---|---|
| No provider | `done`, 0 failed, score 0.7 | `failed`, 3 failed, score 0.0 |
| Real model | `done`, score 0.7 | `done`, 0 failed, score 1.0 |

### 🔴 3. Fine-tuning was entirely fabricated

`/jobs/start` wrote hardcoded metrics — `step: 150/150`, `train_loss: 0.284`,
`eval_loss: 0.312`, `status: "completed"` — and returned *"LoRA fine-tuning job completed
successfully"* **without training anything**. The same invented losses on every call.

`/hardware` claimed `"Apple Silicon MLX / CUDA Hybrid"` with **24GB VRAM on every machine**
— a Raspberry Pi and a GPU workstation reported identically. Nothing was inspected.

There is **no training library in the dependency set at all** (no torch, no mlx, no peft),
so this could never have trained a model.

**Fixed** — `/hardware` does real detection (`nvidia-smi`, Darwin+arm64 check, `importlib`
probe) and reports CPU-only honestly. `/jobs/start` returns **501 with instructions** when
no backend is present rather than a fabricated success a user might rely on. Dataset
preparation still works.

### 🟠 4. 23 error paths returned HTTP 200

Across `agent_identity`, `hitl`, `swarm` and `fusion`. Mapped by failure class: 400
validation, 403 forbidden, 404 not found, **409 conflict** (deciding an already-decided
HITL interrupt), 500 internal.

`a2a`'s two were deliberately left alone — they're proxied upstream payloads, not endpoint
responses.

---

## ⚠️ Ten tests were passing against broken behaviour

Fixing the status codes exposed a systemic testing weakness worth calling out:

**`tests/uat/conftest.py`'s `j()` helper returned `{}` for *any* non-200 response.** That
made every assertion about an error *body* silently vacuous — `d.get("ok") is False` passes
trivially against `{}`. The same pattern existed in `must()` and `ok()` in the system and
integration conftests.

So tests like *"user gets helpful error"* and *"revoked token rejected"* were asserting
nothing at all. They now assert the status directly and read the real error payload.

Also found: **two fusion tests passed `prompt=` to an endpoint that takes `q=`** — they were
exercising the error path while claiming to test classification. And `test_35` asserted the
*fabricated* fine-tuning result (`lora_supported` always true, job status `"completed"`),
so it actively locked in the lie.

---

## Verified working (no change needed)

- DAG decomposition, topological wave scheduling, parallel execution, kill switch
- HITL interrupt lifecycle — including correct rejection of double-decisions
- Agent identity: JIT token issue/validate/revoke, expiry, scope and cross-agent boundary
  enforcement (a cross-agent attempt reads as 404, which also avoids confirming the token
  exists to the wrong caller)
- Goals CRUD and scoring (fixed in the initial repo review), A2A registry, Fusion routing

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Chat** | Shares `llm.complete()`; the stub flag it already sets is now honoured here too. |
| **Observability / FinOps** | Run counts and `failed_count` are now truthful, so dashboards stop over-reporting success. |
| **Audit log** | No longer records `outcome='success'` for runs that wholly failed. |
| **All test suites** | The `j()` fix makes error-body assertions meaningful platform-wide — worth re-reading any test that inspects an error payload. |

---

## Tests added

`tests/unit/test_56_supervisor_module_review.py` — **27 contracts** covering reconciliation
(with a real orphan fixture and an idempotency check), stub-run handling, status/score/audit
correctness, honest fine-tuning, and per-class status codes.

**Suite:** 2897 backend passed / 12 skipped / **0 failed** · 75 vitest passed · ruff clean.

---

## Recommended follow-ups

1. **Supervisor runs are not durable.** Reconciliation makes restarts *honest*, but a long
   run still dies with the process. If resumability matters, run state needs to move to a
   queue or a resumable step machine — worth a product decision.
2. **Fine-tuning is now honest but still unimplemented.** Either wire a real LoRA backend
   (peft + torch/MLX) or consider retiring the tab; it currently promises a capability the
   platform doesn't have.
3. **Audit the remaining `j()`-style helpers.** I fixed the UAT one; `must()` and `ok()` in
   the system/integration conftests still return `{}` on non-200, so other error-body
   assertions elsewhere may be vacuous.
4. **`_execute_task` catches all exceptions into a generic string.** Task failures lose
   their type, which made diagnosing the stub issue harder than it needed to be.
