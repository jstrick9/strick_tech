# 40 — 662 CSP reports on every page load

Autonomous hunt, batch 27. You chose **performance**, with appetite for a
larger fix. The first measurement found something bigger than expected.

## The finding

Instrumented a real page load in Chromium:

```
total requests: 775
  api:    686
  static:  87

API endpoints called more than once:
  662x  /api/security/csp-report      <-- 86% of ALL load traffic
    4x  /api/onboarding/preferences
    3x  /api/secrets/get?key=OPENROUTER_API_KEY
    ...
```

**662 POSTs to the CSP violation endpoint on a single load.**

## Cause: a fix that fought its own measurement

Batch 22 enforced strict `style-src 'self'` and added
`frontend/js/00-style-hydrate.js`, which re-applies each refused style
attribute through the CSSOM.

The parser still **refuses the attribute first** — that is the entire
mechanism. So the browser emitted a violation report for each of ~660 style
attributes, and the hydrator then silently fixed it. The Report-Only policy was
still governing styles, so it reported a rule that was **already enforced and
already handled** — exactly the trap its own comment warns about:

> *"reported on rules already in force and collected nothing actionable"*

### Cost

- **662 requests per load**, each a full POST with a JSON body through the
  entire middleware stack — rate limiter, CSRF exemption, security headers, the
  `ok:false` re-status pass.
- The violation buffer filled with ~660 entries of a resolved issue, **burying
  anything genuinely new**. The dashboard becomes unreadable, which defeats the
  point of collecting reports at all.

## The subtlety that cost a round trip

Deleting the `style-src` line from Report-Only **changed nothing**. With no
`style-src`, `default-src 'self'` takes over as the fallback and still governs
styles. Verified against the live header — the reports kept firing.

It has to be listed **explicitly** as permissive, not merely omitted. Recorded
because the intuitive fix is the wrong one, and the header looks correct either
way.

## Measured impact

| | Before | After |
|---|---|---|
| Requests on load | **775** | **113** (−85%) |
| API requests | 686 | 24 |
| `domInteractive` | 1053ms | **543ms** |
| First contentful paint | 272ms | **98ms** |

Security posture is unchanged — verified against the live headers:

```
enforcing:    script-src 'self';  style-src 'self'
report-only:  style-src 'self' 'unsafe-inline'   (quiet)
              img-src 'self' data: blob:          (the live ratchet)
```

The measurement channel still works: a genuine `img-src` violation is recorded
and surfaces in the dashboard.

## Also added: a report ceiling

Even with `style-src` quiet, any future ratchet matching thousands of nodes
would flood the same way. The buffer already de-duplicated by signature, but
**the requests still arrived**. Past `_CSP_REPORT_CEILING` the count keeps
rising — frequency is the signal — but the per-report work stops.

## Two tests updated, and the history is the point

`test_89` has now been inverted **twice**, which is worth recording rather than
hiding:

- **v1** asserted Report-Only *kept* `style-src 'unsafe-inline'` — correct while
  it previewed the `script-src` tightening.
- **v2** asserted it *dropped* `'unsafe-inline'` — correct while strict
  `style-src` was the next ratchet.
- **v3** strict `style-src` is enforced, so previewing it collects nothing *and*
  actively harms.

The invariant that survived all three, and is what the test now asserts:
**Report-Only must differ from the enforcing policy in at least one directive,
or it measures nothing.**

## Other performance observations (not yet acted on)

- **80 separate JS files, 2.1MB.** Not bundled. The slowest individually took
  364ms. Worth considering, but bundling changes the build story and the CSP
  posture, so it deserves its own decision rather than being folded in here.
- **Median pane switch 65ms**, worst 252ms (settings). Acceptable; no long
  tasks (>50ms) observed in an idle window.
- Idle polling is modest: 5 API calls per 10s.

## Tests

`tests/unit/test_111_csp_report_flood.py` — 6 tests, including that the
enforcing policy stays locked down, that Report-Only still measures *something*,
and that the endpoint still records real violations.

**Proven to catch the bug: with both files reverted, 3 of 6 fail.**

## Regression status

| Suite | Result |
|---|---|
| `tests/unit` | **3011 passed, 2 skipped, 0 failed** |
| `regression` + `system` + `integration` + `uat` | **1044 passed, 17 skipped, 0 failed** |
| ruff · inline-handler · globals linters | pass |
