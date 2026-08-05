# Phase 3 — the Report-Only ratchet

Phase 3 as originally written was *"ship Report-Only with the strict policy,
collect for a week, then drop `unsafe-inline`."* The flip already happened in
`461ba07`, ahead of that schedule, once the real-browser suite could verify it.

That left the Report-Only header **byte-identical to the enforcing one** apart
from `report-uri`. It was reporting on rules already in force and collecting
nothing — coverage-shaped dead weight.

Phase 3 now means: **keep the header one ratchet ahead of what is enforced, and
make what it measures visible.**

---

## The bug: the measurement channel had been reading zero

`/api/security/csp-report` was not in the CSRF exemption list.

The **browser** posts violation reports itself, from its own network stack,
with no JavaScript involved. It cannot attach a CSRF token and there is no way
to make it. Every report was answered `403` and discarded.

Measured against the running app:

| | |
|---|---|
| browser console | **1740** style violations |
| endpoint reported | **0** |

A measurement channel that silently reads zero is worse than no channel,
because the zero looks like good news. This one had been reading zero since
CSRF enforcement was turned on, and the header's entire purpose is to answer
*"what would break if we enforced this?"* — a question it was answering
*"nothing."*

Exempting it is safe: the endpoint appends to a bounded in-memory ring buffer,
returns nothing to the poster, and changes no state a forged request could
exploit.

> The exemption-list guard added in `7861f54` refused the new entry until it was
> justified in the test itself. That is exactly what it was written to do, and
> it is the second time it has caught an addition.

---

## The measurement: what strict `style-src` would cost

With the pipeline fixed, Report-Only was pointed at strict `style-src` and the
app driven through **all 27 panes** in Chromium.

### Static scale

| | Count |
|---|---|
| Inline `style=` attributes | **4,759** |
| — static (could become a class) | 4,494 |
| — dynamic (interpolated value) | 257 |
| Distinct static style strings | 1,815 |
| `<style>` blocks in `index.html` | 3 (56KB) |
| `element.style` writes in JS | 735 |
| `.style.cssText` writes | 135 |

### Measured violations

| | Count |
|---|---|
| Distinct violation sites | **118** |
| Total events | 121 |
| `style-src-attr` | 109 |
| `style-src-elem` | 9 |
| From our code | 113 |
| From third-party CDN libraries | 5 |

The third-party ones are Monaco (`editor.main.js`) and `3d-force-graph`
injecting their own styles. They cannot be fixed in this codebase — they would
need a hash allowance or a local build.

### What CSP actually blocks

Verified directly in Chromium, because the three cases behave differently and
the distinction changes the size of the job:

| | Blocked by strict `style-src`? |
|---|---|
| `style="width:123px"` attribute | **yes** |
| `<style>` block | **yes** |
| `element.style.width = '55px'` | **no** |

That last row matters: the 735 `element.style` writes and 135 `cssText` writes
are **not affected**. The migration is the 4,759 attributes and 3 blocks, not
the ~5,600 total the raw counts suggest.

### Risk, for weighing against that cost

Under the **current** enforcing policy, a style injection cannot execute
script — `expression()` is long dead in every modern engine. The residual risk
is UI-redress: a full-viewport overlay is possible, and `img-src https:` allows
a CSS-driven exfiltration channel via `background: url(...)`.

That is real but materially smaller than script execution, which is what
`script-src` already blocks.

### Recommendation

**Do not enforce strict `style-src` yet.** The cost is a 4,759-site migration
plus 5 unfixable third-party sites; the benefit is closing a UI-redress vector
in a local-first desktop app. That ratio does not justify it ahead of the other
work available.

**Keep it in Report-Only.** It costs nothing, the number is now visible in the
UI, and it will only get smaller as inline styles are replaced during ordinary
work. Revisit when the count drops below roughly 20 distinct sites, or if the
platform is ever exposed to untrusted users on a shared origin.

---

## The dashboard

`frontend/js/58-csp-monitor.js`, reachable at **Settings → Security**.

The reports had been collected since the header was introduced and were
invisible to anyone who did not curl the endpoint. That is precisely how the
403 went unnoticed.

The panel shows distinct sites, total events, and — deliberately separated —
how many come from **our code** versus **third-party libraries**, because the
latter cannot be fixed here and counting them together overstates the cost.

An empty list explicitly says it may mean *"nothing has been exercised yet"*
rather than *"safe to enforce"*. That ambiguity is the bug this whole section
is about, and the panel should not reproduce it.

---

## Guards

Two tests keep the header honest:

- **Report-Only must be strictly ahead of enforcing.** If the two converge
  again it is measuring nothing, and that failure is silent.
- **The enforcing `style-src` must still allow inline styles.** Report-Only
  must never drift into enforcement by accident; that would break 4,494 static
  inline styles across the product.

## Verification

- 12 tests in `test_105_csp_report_pipeline.py`; reverting the CSRF exemption
  fails 1
- panel rendered in a real browser with live data and **zero page errors**
- full suite: **3959 passed, 19 skipped, 0 failed**
- browser suite: **53 passed**

Two existing tests were inverted deliberately: `test_89` asserted Report-Only
*keeps* `style-src 'unsafe-inline'` (correct for its old job, wrong for its new
one), and the CSRF exemption-list guard required the new entry to be justified.
