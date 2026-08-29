# Bug sweep: plan, process, and finish line

Written in response to four bugs reported from a real macOS desktop build:

1. A **Pro-features popup** on a build that should be fully unlocked
2. **Glitchy clicking** — trouble interacting with different modules
3. **Kanban drag-and-drop does not work**
4. **Ollama on localhost did not auto-connect**

You asked for a process that runs *"without stopping until there are no more
issues."* I will not promise zero bugs — nobody can, and a promise I cannot
keep is worse than a plan I can. What I will promise is a **defined finish
line**, which is stated at the bottom and is falsifiable.

---

## What is already established

Investigated before writing this, against a live server and a real browser.

### Bug 1 — Pro popup: **cause identified, not yet reproduced**

The backend is correctly unlocked here:

```
license.tier = enterprise   unlocked = True   is_trial = False
ui-config.unlocked = True   AGENTIC_ENFORCE_LICENSE = <unset>
```

No upgrade element renders in my browser. So the fault is almost certainly
**stale frontend JS**, and the mechanism is now understood:

`backend/app.py` rewrites `index.html` at serve time to load **content-hashed
bundles from `frontend/dist`**. Nothing in `build_macos_desktop.sh` regenerates
that bundle. A `git pull` that changes JS but leaves `dist` untouched therefore
ships **the old JS**, paywall included, while `index.html` on disk looks
perfectly current.

`scripts/diagnose_desktop.py` now detects exactly this and names the fix.

### Bug 2 — glitchy clicking: **reproduced**

A full-screen `#onboarding-modal` at **z-index 29000** with
`pointer-events: auto` covers the viewport. `document.elementFromPoint()` at
the screen centre returns `#ob-subtitle` — the modal's own text, not the app.
Every click in that region hits the overlay.

### Bug 3 — Kanban drag-and-drop: **reproduced, with the exact fault**

Dragging a card does nothing. Task status is unchanged before and after, and
the console shows:

```
kanbanOnDragOver  TypeError: Cannot read properties of undefined (reading 'add')
kanbanOnDrop      TypeError: Cannot read properties of undefined (reading 'remove')
```

**Root cause:** the four Kanban drag handlers read `event.currentTarget`. The
delegated dispatcher (`00-delegate.js`) listens in the **capture phase on
`document`**, so by the time a handler runs, `currentTarget` is `document` —
never the drop zone. The dispatcher already exposes a `$this` placeholder that
resolves to the matched element, which is the correct fix.

`19-composer.js` uses the same pattern and is presumed broken the same way.

> **A correction worth recording:** I first claimed the dispatcher did not bind
> drag events at all, based on `grep -oE "data-act-[a-z]+"` over the source.
> That was wrong — the events are bound from a runtime list at line 54. The
> probe could not see a constructed string. I state it because the same mistake
> made in a fix rather than a diagnosis is how regressions ship.

### Bug 4 — Ollama auto-connect: **cause identified**

Detection code exists but there is **no standalone detect endpoint**. Probing
only happens inside `POST /api/onboarding/quick-setup`, and the frontend only
calls it from manual buttons in Settings. Nothing runs at launch, so a running
local Ollama is invisible until you go looking for it.

---

## The process

Four phases. Each phase ends in something checkable, and nothing is claimed
without evidence from a running system.

### Phase 0 — evidence (you, once)

Run `python3 scripts/diagnose_desktop.py` with the desktop app open and paste
the output. It reports repo state, whether the served frontend matches the
checkout, the real licence/unlock values, and whether Ollama is visible.

This settles Bug 1 definitively rather than by inference. Everything else can
proceed in parallel.

### Phase 1 — fix the four reported bugs

| Bug | Fix | Proof it worked |
|---|---|---|
| 1 Pro popup | Build script regenerates the bundle and **refuses to package** if `dist` is stale | Canaries in the diagnostic report `present` on a fresh build |
| 2 Overlay | Onboarding dismissible, remembers dismissal, Escape closes it, self-disables if it fails to initialise | `elementFromPoint()` at centre returns app content, not the modal |
| 3 Kanban | Replace `event.currentTarget` with the dispatcher's `$this` | A scripted drag moves a task between columns and the change persists |
| 4 Ollama | Probe `localhost:11434` at startup; auto-select a model if found; silent if absent | With Ollama up, models appear with no clicks; with it down, no error surfaces |

Each fix gets a test that **fails before and passes after**, and each is
revert-proved: I break the fix deliberately and confirm the test catches it.

### Phase 2 — sweep for the same *classes* of defect

Your four bugs are instances of four general classes. The value is in hunting
every other occurrence, not just the reported one.

| Class | Sweep |
|---|---|
| **Dead handler contract** — markup calling a handler whose expectations the dispatcher does not meet | Every `data-act-*` attribute in the codebase: does the named function exist on `window`, and does it use anything the dispatcher cannot supply? |
| **Blocking overlay** — a fixed element that intercepts clicks | Every pane: after navigation, is the element at the centre of the viewport part of that pane? |
| **Stale build artefact** — shipped output diverging from source | Does every packaging path regenerate what it ships, and fail loudly if it cannot? |
| **Capability present but never triggered** — code that works only if you find the button | Every integration with a detectable local service: is it probed automatically? |

Each sweep is a script that can be re-run, so a regression is caught rather
than rediscovered.

### Phase 3 — regression guard

Every defect found becomes a test. The suite currently stands at **4,649 unit +
664 integration**; each fix adds to it. Nothing ships without the full suite
green and every new test revert-proved.

---

## Status

_Updated as work lands. Every claim here is checkable by running the command._

### Phase 1 — the four reported bugs: **COMPLETE**

| Bug | Status | Proof |
|---|---|---|
| 1 Pro popup | Fixed | Build regenerates + verifies `dist`, 7 hard `exit 1` gates. Backend confirmed unlocked on the user's machine. |
| 2 Glitchy clicking | Fixed | Root cause was NOT the overlay. `data-self-click` synthesised clicks on all 16 non-click events, so hovering ran click actions. Now keyboard-only (b99dc0a). |
| 3 Kanban drag-drop | Fixed | Handlers take `$this`; 0 live `currentTarget` reads remain (5c2a93f). |
| 4 Ollama auto-connect | Fixed | Endpoint existed with no caller; startup probe wired (6a02312). Verified in Chromium against a 17-model list. |

Four build-chain defects were found *between* those fixes and the user's
machine, each of which silently shipped stale code: unrunnable build script
(5e0d178), non-reproducible bundle blocking `git pull` (03ee7d7), the packager
selecting the *previous* build's `.app` (d481a30), and no warning when behind
origin (e8bd391). Phase 1's fixes were correct for three sessions before any
of them reached the user.

**10 test files, 91 tests, every one revert-proved.**

### Phase 2 — sweep the classes: **1 of 4 complete**

| # | Class | Script | Findings |
|---|---|---|---|
| 1 | Dead handler contract | `scripts/sweep_dead_handlers.py` | **0** ✅ |
| 2 | Blocking overlay | not yet written | — |
| 3 | Stale build artefact | not yet written | — |
| 4 | Capability never triggered | not yet written | — |

```bash
python3 scripts/sweep_dead_handlers.py    # exit 0 = zero findings
```

Sweep 1 found one real defect (`data-act-select` was never bound, so the
collab editor never shared cursor position) and 69 false positives caused by
the probe itself. All 69 are documented in `efafc7a`; the correction ratio is
the reason each sweep is committed only after its own output is trustworthy.

---

## The finish line

This is the falsifiable part.

**Phase 2 is complete when each of the four sweep scripts reports zero
findings, and the full suite is green.**

That is a real, checkable end state. What it does *not* claim:

- It does not mean the app is bug-free. It means **no remaining instance of any
  defect class we know how to detect**.
- Classes we have not thought of will not be found by scripts written for the
  classes we have. New symptoms from you are the highest-value input there is —
  the four you reported took ten minutes to investigate and produced two
  reproduced faults and two identified causes. That is a far better rate than I
  achieve reading code.

**So the honest process is: sweep to zero on known classes, then treat every
new report as a new class and extend the sweep.** That converges. "Fix
everything" does not, because it has no observable end.

---

## Standing rules for this work

Carried from the review series, because they are what made it productive:

- **Verify against a running system**, never by reading alone.
- **Every fix gets a test proven to fail first.**
- **Revert-prove every test** by breaking the fix deliberately.
- **When a probe disagrees with the app, suspect the probe.** In this
  investigation alone the probe was wrong three times: a grep that could not
  see runtime-constructed strings, a diagnostic that reported a dead server as
  a stale build, and five separate shell-quoting artefacts.
- **A skip is not a pass.**
- **Correct mistakes prominently**, in the commit message, where the next
  person will see them.
