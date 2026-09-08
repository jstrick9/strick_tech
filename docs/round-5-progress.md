# Agentic OS — Round 5 Progress

**Focus:** Consistent UI states + cohesive density/hierarchy + bug/UX hunting.
**Ship style:** incremental — fix + regression test + commit + push each item.
**Frontend suite:** 111 → **175 passing** · bundle rebuilt & reproducible · live app on port 8787.

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
15. **#048 — Every pane's loading state routes through the `.data-state` component (~48 sites).** Added `stateFeedback.loadingElement(label)` (embed-in-template AND imperative, identical markup). Converted ~48 hand-rolled inline-styled `Loading…` divs across ~32 panes plus dynamic-label loaders and the `showInlineLoading` helper to the shared spinner + `role=status` + `aria-live` component. (data-state-loading 3)
16. **#049 — Pane-body error states route through the `.data-state` error component (~22 sites).** Added `stateFeedback.errorElement(opts)` (with optional Retry). Converted full-pane `humanError` loads and data-container load failures (history, shortcuts, entity, leaderboard, agent detail, ICM, plugin/connect-hub, galaxy, quick-start, dashboard) and the ad-hoc error+manual-Retry blocks to the `role=alert` component; dashboard fixed to use guarded `setError`. Small inline form/result status spans intentionally left. (data-state-error 4)
17. **#050 — Data-area empty states route through the `.data-state` empty component (~25 sites).** Added `stateFeedback.emptyElement(opts)` (icon/title/message/action). Converted ~25 hand-rolled inline empty divs across ~17 panes (evals, quality, replay/collab, hierarchy, prompt-library search, fusion, websearch, leaderboard, supervisor, goals, chat history, ICM, template gallery, galaxy, loops, hooks, battles, flamegraph, console), each preserving its next-action CTA. Compact list notes / table rows / per-op statuses / success lines intentionally left. (data-state-empty 4)
18. **#051 — Empty-state CTAs + unify bespoke pane empties.** `emptyState()`-factory audit: control-tower 'No runs yet' + its error state gained CTAs (all other factory sites already had them). Unified the id'd bespoke empties — workflow canvas 'No Workflow Selected', code-insights 'Codebase Index' (+Index Now CTA) and replay 'No Run Selected' (+Open Workflows CTA, replacing an inline clickable span with a real button) — to the shared `state-empty` component. `docs-search-empty` is a contextual in-search empty, intentionally left. (data-state-empty now 4)

### The parked "bold redesign" branch — shared component primitives
19. **#052 — Consolidated ~110 per-pane widgets onto bold shared primitives.** Audited programmatically and confirmed: every bespoke pane widget (buttons, badges, tags, chips, tabs, toggles, fields, tables, modals across A2A, compliance, agent-monitor, goals, supervisor, MCP-gateway, replay/collab, evals, quality, account-settings, workflow-specs, marketplace, prompt-library, ICM…) was styled ONLY in `frontend/styles.css`, which index.html does NOT link — the same "rule exists but never loads" defect that took down `.ce-*`. Each rendered as a bare browser control. Unified them onto a small token-driven set of bold primitives in the authoritative `styles-system.css` (`wg-btn`/`wg-ibtn`, `wg-tabs`/`wg-tab`, `wg-badge`, `wg-tag`, `wg-chip`, `wg-toggle`, `wg-field`, `wg-table`, `wg-modal`), with `.primary`/`.danger`/`.active` variants and AA status tints (pass/fail, low/medium/high/critical, running/done/pending). Purely additive; honours `prefers-reduced-motion`; carries a `:focus-visible` ring. (widget-primitives 7)
20. **#053 — Shared fixed modal scrim for bespoke dialogs.** `a2a-modal-overlay`, `dag-modal-overlay` and `gm-modal-overlay` were appended via `overlay.className='…'` with no inline style and no CSS in any loaded sheet, so their dialog content dropped into the document flow instead of centering over a full-screen scrim. Added a `wg-modal-overlay` primitive (fixed inset scrim, blurred backdrop, centered flex) applied to all three. (widget-primitives 8)
21. **#054 — Escape dismisses the bespoke overlay-modals (item #3).** `gm-create-modal`, `dag-launch-modal`, `a2a-delegate-modal`, `a2a-register-modal` were added to the global master Escape handler (discovery by id) and given a `remove()` branch — they must be removed, not `display:none`, or a stale scrim keeps catching clicks. (escape-overlay-modals 2)
22. **#055 — Badge/tag cluster + modal-example layout.** Follow-up to the primitive sweep: the now-styled badges/tags/examples sit in plain unstyled block wrappers, so their pills stacked vertically. Gave the cluster wrappers a wrap-only row and the DAG modal examples a stacked list. (widget-primitives 9)

---

## Live preview
App running at **port 8787**. Refresh to see the density/elevation/state changes and the four UX improvements.

---

## Live preview
App running at **port 8787**. Refresh to see the density/elevation/state changes and the four UX improvements.

## Verification
- Frontend suite **186 passing**; bundle served live as head+chunks+app (3 requests, not 88).
- axe-core scan of the static app shell: **0 violations** (critical/serious and all impacts).
- Every change ships with a jsdom regression test; onboarding-enter & composer verified **red on pre-fix**.
