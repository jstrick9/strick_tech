# 54 — Offline and reconnect

**Seam:** *offline / reconnect*
**Audit:** `scripts/audit/offline_reconnect.py` · **key:** `offline-reconnect` ·
**baseline:** 1 → **0**
**Tests:** `tests/unit/test_125_offline_reconnect.py` (10) — 5 fail on revert.

---

## Why offline is its own seam

`failure_honesty.py` covers *the server answers 500*. `session_expiry.py`
covers *the server refuses you*. Offline is a third thing: the request never
reaches anyone, `fetch` **rejects** rather than resolving, and — the part that
matters — **the condition ends**. Every other failure audit measures a steady
state. This one measures a transition, and recovery is where the bugs live.

---

## The defect: three modules, three contradictory answers

Measured in real Chromium with `context.set_offline(True)`, all on screen
**simultaneously**:

| Source | Message |
|---|---|
| `01-app-core.js` | ⚠️ You are offline — **local features still work** |
| `00-connection-status.js` | Some data couldn't load. **Your work is safe** — this looks like a connection problem. |
| `00-net-feedback.js` | ⚠ You are offline — **changes will not be saved** until the connection returns. |

"Your work is safe" and "changes will not be saved" are **opposite advice about
the same event**, presented at the same moment with equal authority. A user
with unsaved work cannot act on that — and the reassuring message is the one
that reads as authoritative, so the likely outcome is the worst one: they
believe their work is stored and close the tab.

Each handler was individually reasonable. Nobody wrote a contradiction; three
people wrote one sensible message each. This is recurring pattern **#4** — *a
behaviour implemented at one call site while identical sites go unprotected* —
in its mirror form: the same behaviour implemented at **three** sites, none
aware of the others.

---

## Fix: one owner

`00-net-feedback.js` keeps the banner, because its message is the accurate one.

- **`01-app-core.js`** — toast removed. Its handler now does only the job
  nothing else does: colour the status dot red.
- **`00-connection-status.js`** — actively **stands down** while the browser
  reports no network. Going offline now *hides* this banner and suppresses it;
  going online re-enables it. The guard lives in `record()`, not only in the
  listener, because failures keep arriving while offline and would otherwise
  cross the threshold on their own.

The stand-down is deliberately temporary. Leaving it suppressed would mean a
genuine post-reconnect outage went unreported for the rest of the session —
which is why `test_going_back_online_re_enables_the_connection_banner` exists.

---

## What the audit verified as already correct

Worth recording, because two of the three checks found nothing:

- **A write attempted while offline is reported.** The probe fires a real
  `POST /api/tasks` through the app's own stack (not a bare `fetch`, which
  would bypass the UI's handling and measure the transport instead of the
  product). It rejects, and the screen says so. A silently-dropped write would
  have been the most serious finding available in this seam.
- **Recovery needs no reload.** After `set_offline(False)`, content returns on
  normal navigation. The probe reloads only as a *control*: if a pane recovers
  on reload but not without one, "reload fixes it" is not recovery — it is the
  user doing the work.

---

## The probe's own two bugs, both found before the app's

1. **Whole-document text search.** `/offline/` matched
   `Private • Ollama • Offline` — a product feature label about a local LLM
   running without a network. It produced a false `RECONNECT` finding, and,
   far more dangerous, **the same prose would have satisfied the
   `GOING-OFFLINE` check**, so a total absence of offline reporting would have
   reported clean. Now scoped to status surfaces.

2. **The redundancy hid the breakage.** Disabling one offline handler left the
   audit at **0**, because two others still spoke. Three overlapping owners
   meant no single one could be proven necessary. Only after consolidating to
   one owner could the probe be shown to fail when that owner was removed
   (`GOING-OFFLINE  no status surface says the connection is gone`) — which is
   the only evidence that it measures anything at all.

The second point is the general lesson, now in the register: **redundancy makes
every individual owner unprovable.**

---

## Verification

| Check | Result |
|---|---|
| `scripts/audit/offline_reconnect.py` | 1 → **0** |
| Disable the surviving banner | audit correctly reports `GOING-OFFLINE` |
| Revert the frontend fix | **5 of 10** tests fail |
| `ruff`, `lint_globals`, `build_bundle --check` | clean |
