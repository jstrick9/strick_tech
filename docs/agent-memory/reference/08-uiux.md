# 08 — UI/UX for Autonomous Systems

> Agent adoption lives or dies on interface design, not model quality. The gap
> from prototype to production is mostly a UX problem.

---

## Why traditional UX breaks

Conventional interfaces assume the user initiates and the system responds.
Agents invert this: the system acts, over time, sometimes wrongly, often
invisibly. A chat box is the wrong primitive for **60%+ of agent use cases** —
it hides what happened, offers no way to intervene mid-task without aborting,
and gives the user nothing to audit.

## Progressive disclosure — the core pattern

Showing everything produces overload; showing nothing produces distrust. Three
layers:

| Layer | Content | Who reads it |
|---|---|---|
| **1 — Result** | The output + a human-readable confidence signal | Everyone |
| **2 — Summary** | Plain English: *"Found 3 invoices, cross-referenced against the PO, flagged a $200 discrepancy on line 4"* | Most users — this is the layer that gets read |
| **3 — Audit trail** | Full trace: tool calls, inputs, outputs, reasoning | Power users, compliance. Rarely opened — but knowing it exists builds trust |

One deployment moved adoption from 12% → 67% in six weeks by adding layers 1
and 2 alone.

**Confidence signals should be human-readable, not numeric.** Users do not know
what "87% confident" means in context. Green check / yellow "review this" / red
"could not complete" carries more information and fewer false implications.

## Trust calibration

Both over-trust and under-trust are failures.

- If the interface presents the agent as infallible — smooth animations,
  confident language, no visible uncertainty — operators stop applying judgment
  and approve things they should not.
- If it exposes every token and tool call, they cannot find the three decisions
  that mattered among 47 sub-actions.

**Design for calibrated trust:** surface uncertainty honestly, mark AI-generated
content, cite sources inline, and use *mindful friction* (a confirmation step)
on high-stakes actions.

**Users trust agents that acknowledge limitations more than agents that appear
omniscient.** Error states are the highest-trust moment in the product: an agent
that says "I don't know, here is who can help" outperforms one that guesses
confidently.

## Five transparency patterns

| Pattern | Best for | Example |
|---|---|---|
| Confidence badges | Classification, routing | "High confidence" / "Needs review" per output |
| Step timeline | Multi-step workflows | Pipeline showing done / running / pending |
| Source attribution | Research, analysis | Inline citations with expandable previews |
| Decision comparison | Recommendations | "Chose A over B because…" with a table |
| Boundary signals | Any scoped agent | "This is outside what I can do. Contact X." |

## Human-in-the-loop interface design

**Separate the activity panel from the conversation thread.** Long-running work
needs a dedicated audit surface. This is a structural decision affecting state
management and session architecture, not a styling choice.

**Progressive delegation.** Start conservative and expand the autonomy envelope
as trust is earned. Capture per-user approval patterns and persist them: a
category the user consistently approves can move to auto-approve. Empirically,
experienced Claude Code users auto-approve in **over 40%** of sessions — more
than double new users — *while also interrupting more often during execution*.
That combination is what calibrated trust looks like: more delegation and more
intervention, not less of either.

**Interruptibility.** The user must be able to stop, redirect, or correct
mid-run without discarding the work so far.

## Presenting honest state

This is where UI and the review discipline meet. The UI is the last place a
false claim can be caught — and the last place it can be introduced.

- **`value || 0` is a bug when `value` can be null.** "Not measured" rendered as
  `0%` is a confident lie; render `—` and say why.
- **An empty issues list is not a pass** unless something actually ran. Show
  "not analysed" distinctly from "analysed, nothing found".
- **Disable actions that cannot work.** A "Reveal" button on an undecryptable
  secret should be disabled with a reason, not fail on click.
- **Report partial outcomes as partial.** "⚠️ Deployed with omissions — 2 files
  not published" beats "✅ Deployed".
- **Say what will not happen.** If files are excluded from a deploy, name them
  and say why *before* the user clicks.
- **Never claim work you did not do.** "Reconstructed from the URL text only —
  the file was not read. This is an approximation, not an import."

## Information architecture

- **Consolidate ruthlessly.** Sixty panes is not sixty features; it is one
  feature nobody can find. Group by *task*, not by implementation module.
- **Default to few, reveal more.** A short default sidebar with collapsible
  groups beats a complete list.
- **Name for the user's goal**, not the internal component.
- **One canonical place per task.** Two entry points to the same operation is a
  second door in UX form — they will drift.

## Onboarding

Build the mental model, not a feature tour. Users need to know: what the agent
can do, what it cannot, when it will ask, and how to stop it. Demonstrate
capability on the user's own data if possible; a live first success is worth
more than any walkthrough.

## Accessibility

Non-negotiable regardless of interface novelty. Keyboard paths for every action
including approvals; ARIA state on live regions so streaming output is
announced sensibly; visible focus; contrast that survives a status colour;
`aria-current` on the control, not the container.

## Failure modes specific to this layer

- **Chat as the only surface.** No audit, no intervention, no state.
- **Dead controls.** A handler that never fires because a value was
  interpolated wrongly into an attribute — the button looks fine and does
  nothing. Always verify handlers resolve in a real browser.
- **Success toast on a failed operation.** The most common UI-layer lie.
- **Hardcoded status indicators.** Four green dots for four background jobs that
  may not be running.
- **Confidence theatre.** Precise-looking numbers with no basis.
- **Detail with no summary.** A raw trace dumped on a user who wanted a verdict.
