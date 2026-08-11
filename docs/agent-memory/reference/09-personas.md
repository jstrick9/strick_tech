# 09 — User Personas

> Three users, one product. The design failure is building for the middle and
> serving nobody well.

---

## Novice

**Who:** has used ChatGPT. Has not built an agent. Does not know what a vector
store is and should not need to.

**Goal:** get one useful outcome today without learning a taxonomy first.

**What they need**
- A **first success within five minutes**, on their own data.
- Templates and presets that are genuinely one click — not a form with eleven
  required fields.
- Plain language. "Give your agent a memory" not "configure the semantic tier".
- Safe defaults: bounded loops, human approval on anything destructive,
  conservative spend caps, sandboxed execution — all *on* by default.
- Recoverability. Every action undoable or clearly marked as not.
- Errors that say what to do next, with a link that does it.

**What breaks them**
- Empty states with no path forward. An empty screen is a dead end.
- Jargon in the primary flow.
- Silent failure — they cannot tell "broken" from "I did it wrong", and they
  assume the latter and leave.
- Configuration before value.
- A wall of 60 modules.

**Design rule:** the novice path must be the *default* path, not a "simple mode"
bolted on beside the real product.

## Intermediate

**Who:** developer or technical operator. Has shipped something with an LLM.
Knows RAG exists, has opinions about prompts, has not run agents unattended at
scale.

**Goal:** compose a reliable workflow and understand it well enough to debug.

**What they need**
- **Visible mechanism.** Which model ran, what it cost, what the tool returned,
  why the router chose that path.
- Editable defaults rather than hidden ones.
- Real error surfaces: status codes, stack traces on request, trace IDs.
- Composition — chain steps, add a tool, branch on a condition.
- Test and preview before committing: dry-run, diff, "what would this do".
- Docs with runnable examples, not concept essays.

**What breaks them**
- Magic they cannot inspect. If the router picks a model and won't say why,
  they stop trusting the router.
- Defaults they cannot override.
- Errors flattened to "something went wrong".
- Fake progress. A spinner that is not tied to real state.

**Design rule:** everything the novice gets by default, the intermediate must be
able to see, override, and test.

## Advanced

**Who:** platform engineer, architect, or AI engineer. Runs this in production
with real money and real consequences.

**Goal:** operate a fleet safely — extend it, monitor it, prove it is behaving.

**What they need**
- **API and file parity.** Anything the UI can do, a script can do.
  Configuration as code, in git, reviewable.
- Observability: traces, spans, token and cost attribution per agent, per run.
- Evals wired into CI with a gate that fails the build.
- Governance surfaces: audit export, RBAC, retention policy, budget enforcement,
  a tested kill switch.
- Extension points: custom tools, custom retrievers, custom scorers — without
  forking.
- Escape hatches, documented: how to disable a guard deliberately (environment
  variable, not a request parameter), and what it costs.
- Honest limits. Tell them the rate cap, the context ceiling, the failure
  behaviour under load.

**What breaks them**
- UI-only capability.
- Unversioned prompts and policies.
- Missing or partial audit coverage.
- Per-request kill switches — anything an attacker or a stray agent can flip.
- Silent truncation, silent retry, silent fallback. Advanced users can handle
  bad news; they cannot handle not being told.

**Design rule:** the advanced user's escape hatches must be *process-level* and
*logged*, never per-request.

## Designing for all three at once

**Progressive disclosure is the resolution** — the same mechanism as agent
memory and agent UI, applied to product surface:

| Layer | Novice | Intermediate | Advanced |
|---|---|---|---|
| Default | One click, safe | Sensible, visible | Sensible, overridable |
| Second layer | Not shown | Settings, dry-run, traces | Config file, API |
| Third layer | Not shown | On request | Always available |

**Rules that hold:**
1. **One product, three depths.** Not three products. A "simple mode" that is a
   different app splits the roadmap and rots.
2. **Defaults are the novice's UI.** Choose them as carefully as you design a
   screen.
3. **Never lie to any tier.** The novice needs less detail, not false comfort.
   "Deployed with 2 files omitted" is understandable by everyone.
4. **Advanced capability must not degrade the novice path.** Put power behind
   a door, not in the doorway.
5. **Let users move up.** A visible "show details" that teaches the next
   concept is how an intermediate becomes advanced inside your product.

## Persona-specific failure modes

- **Novice:** builds something on defaults, gets a confident wrong answer,
  never learns it was wrong. This is why honest status matters most for the
  least sophisticated user — they have the least ability to detect the lie.
- **Intermediate:** builds a workflow that works in demo, has no evals, ships
  it, and cannot explain a regression three weeks later.
- **Advanced:** hits a UI-only capability, forks or scripts the browser, and now
  runs an unsupported configuration you cannot help them with.
