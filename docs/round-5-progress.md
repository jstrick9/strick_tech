# Agentic OS — Round 5 Progress

**Focus:** Consistent UI states + cohesive density/hierarchy + bug/UX hunting.
**Ship style:** incremental — fix + regression test + commit + push each item.
**Frontend suite:** 111 → **164 passing** · bundle rebuilt & reproducible · live app on port 8787.

---

## Work completed (all on `main`)

### Design-system foundation + consistent states + density
1. **#032** `styles-system.css` (authoritative design tokens + shared `.data-state` loading/empty/error components, loaded last) + `js/00-state-feedback.js`; Dashboard routed through it. (state-feedback 7, dashboard 2)
2. **#034** Defined the missing `.surface-z1..z4` + `.card-elevated` elevation scale (~26 panes used them with no CSS) + button press-affordance. (design-system-guard 4)

### Bug hunting (honest-state)
3. **#033/#037** Zero-fidelity: a legitimate `0` was swapped for an optimistic default in 6 places (BugBot score, KG confidence, HITL confidence, CSP count, Ollama model count, red-team attack count). `typeof === 'number'` guards. (zero-fidelity → 8)
4. **#036** Composer branch list false-empty on outage / eternal loading. (composer-branch-state 3)

### The 4-item UX batch you asked for
5. **#038 — Consistent empty/CTAs.** Routed action-less empty states through the shared `emptyState()` factory with a real next action (Image Asset Library → Generate/Upload; Deploy history → Deploy now; Chat history → Start a chat; Web search history → New search). (empty-state-cta 5)
6. **#039 — Two-phase delete confirmations.** Converted every remaining native `window.confirm/prompt/alert` to the app's `gmDanger/gmPrompt/gmAlert` modals (Tauri-unreliable; inconsistent): inbox, ICM (4), prompt-library, hierarchy fallback. Added a repo-wide native-dialog regression guard. (delete-confirm 2)
7. **#040 — Keyboard-dismissable modals + focus restore.** Locked the gm-modal contract (Escape dismiss, focus-restore to opener, prompt focuses its input) with a behavioral test; made the Skills run-modal Escape-dismissable; added a shared delegated Escape handler so all ad-hoc full-screen overlays (steering/replay/evals) are keyboard-dismissable — scoped to never touch `#gmodal`. (gm-modal-a11y 3, overlay-escape 3)
8. **#041 — Settings/onboarding flow tightening.** Enter now advances the onboarding input and saves the settings API-key / custom-endpoint fields (delegated, bound once). (onboarding-enter 2, settings-enter 2)

### Accessibility pass (icon-button names + keyboard/ARIA)
9. **#042 — Goals pane a11y.** 3 filter `<select>`s get `aria-label`s; goal cards are now keyboard-operable (`role="button" tabindex="0" data-keys`) with `aria-selected`. (goals-a11y 2)
10. **#043 — Workflow property editor a11y.** 8 property `<select>`s (Node type, Agent, Trigger event, Output target, Condition method/action, Mode) get `aria-label`s.
11. **#044 — Accessible names for all icon-only buttons (33 modules).** Added `aria-label`+`title` to every icon-only button that had no accessible name — close (✕/×), delete (🗑), edit (✏), stop (🛑), revive (♻), export (📦), resolve (✓), copy-webhook. Includes a repo-wide regression guard that also catches buttons whose icon was accidentally stripped (empty `<button></button>`). (icon-button-name 3)
12. **#045 — Accessible names for unlabeled controls & images.** Workflow/node config inputs, prompt-library variable inputs, goals milestone inputs, DB-studio cell inputs, ICM stage name, marketplace/ordering + HITL delegation selects, and a screenshot `<img alt>`. (control-labels 4)
13. **#046 — Keyboard-operable mouse-only click divs (13 modules).** Leaf `data-act-click` tabs/nav/cards/rows (agent selector, SDK packs, TTD nodes/lanes, dag nodes, github/mcp/notification/leaderboard rows, onboarding theme picker, drop targets, goal decomposition tasks) got `role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1"`. (keyboard-clickable 2)

### Backend/quality
14. **#047 — Bundle cache picks up rebuilds without touching index.html.** The served index was cached against `index.html`'s mtime only; a rebuilt bundle (new content-hashed filenames) was never served until the file was touched or the server restarted, leaving the live preview pointing at removed artifacts. Cache validity now also tracks `dist/manifest.json`'s mtime. (regression test_reg_07)

---

## Live preview
App running at **port 8787**. Refresh to see the density/elevation/state changes and the four UX improvements.

## Verification
- Frontend suite **164 passing**; bundle served live as head+chunks+app (3 requests, not 88).
- axe-core scan of the static app shell: **0 violations** (critical/serious and all impacts).
- Every change ships with a jsdom regression test; onboarding-enter & composer verified **red on pre-fix**.
