# 11 — Quality Assurance for Agentic Systems

> Testing a non-deterministic system that spends money and takes actions.
> Conventional testing still applies; it is necessary and nowhere near
> sufficient.

---

## The five evaluation stages (conflating them is the main mistake)

| Stage | When | What it catches |
|---|---|---|
| 1. Unit tests | Every commit, milliseconds | Obvious breakage, deterministic logic |
| 2. Golden-set eval | Every PR touching prompts/models/retrieval | Quality regression |
| 3. Adversarial / red-team | Pre-release | Failures you have not seen yet |
| 4. A/B in production | Mature products | Real-user preference |
| 5. Online monitoring | Continuous | Drift, novel inputs, incidents |

Teams that start at stage 2 or 3 without stage 1 skip the fast feedback loop
that makes the slow stages tractable.

## The rule that makes tests worth having

> **A test that has never failed is unproven.**

For every fix: break the *behaviour* — not the import, not the syntax — clear
caches, run the suite, and confirm the right test fails. Then restore and
confirm green.

Do this **per fix**, not once at the end. A batch revert tells you the suite
noticed *something*.

**Corollaries learned the hard way:**

- **Removing an import only proves collection fails.** Break the logic.
- **A test that passes against both broken and fixed code should be deleted.**
  It is decoration and it costs runtime and trust.
- **Investigate the "uncaught" ones rather than assuming a weak test.** Three
  common explanations: (a) the test is genuinely weak; (b) the code is defensive
  and the bug was never reachable; (c) another layer already covers it. All
  three are worth knowing, and only (a) needs a new test. Record (b) and (c) in
  a comment so nobody hunts for a phantom.
- **Assert on the endpoint, not on your own helper.** Building the artefact in
  the test with the same helpers the code uses proves nothing about the code
  path.
- **A guarded assertion can be vacuous.** `if body.get('rows'):` around the only
  assertion means an empty response silently passes. Assert the precondition
  first: `assert body['ok'] and body['rows']`.
- **Beware passing for the wrong reason.** A test that gates on threshold X may
  pass whether or not the clause you are testing exists. Choose inputs that
  isolate the mechanism.
- **Harness artefacts masquerade as behaviour.** If a scheduler never starts in
  the test harness, every job reads as "paused" and a status assertion proves
  nothing.

## Golden datasets

Curated (input, expected behaviour) pairs. **Size:** 20–50 catches gross
regressions; 100–200 gives confidence on 3–5% differences; >500 is diminishing
returns unless sub-tasks genuinely differ.

**Coverage, not just volume.** Every class of input that ever caused an incident
belongs in the set. Include: the common case, past production failures,
adversarial inputs (a chunk with injected instructions, a question with no
answer in context), and cases the system should *refuse* or hedge on. A good set
penalises false confidence as hard as it penalises a wrong answer.

**Sources, in priority order:** real production traces (reviewed by a human —
that review is what makes an item *golden*), imported known cases, synthetic
expansion for thin areas.

**Maintenance:** version the set and pin experiments to a version; record an
added-date so you can measure age distribution; retire items for behaviours
that no longer exist; keep a **holdout partition never used in CI**. If CI and
holdout diverge, you are overfitting.

## LLM-as-judge

Use code evals for anything deterministic (schema, latency, tokens, exact
match). Use a judge only for genuinely open-ended criteria.

**Building one that works:**
1. Start from real failure modes in your traces.
2. Write an explicit rubric with unambiguous labels — not "is this good?".
3. Validate against human labels; **aim for 75–90% agreement** before scaling.
4. Read the disagreements — they tell you whether the rubric or the context is
   wrong.
5. Pin the judge model **version**, not an alias. A judge upgrade shifts every
   score; re-baseline deliberately and record it.

**The judge prompt is an injection surface.** The answer being judged is
untrusted output that may itself contain instructions. Delimit it and label it
as data.

**And the rule that matters most:**

> **An unrun judge must not produce a score.**

If the model was unavailable, returned prose, or returned unparseable output,
the result is *unmeasured*. Return `null` and an explicit `assessed: false`.
Never a default. This defect has appeared in an eval harness (malware scored
"fully safe"), a code reviewer (`eval(user_input)` scored 75/100 with zero
issues), a repo health grader (unscanned tree graded 100/A), and a risk
assessor (`rm -rf /` recommended "proceed", marked reversible). It is the single
most recurrent serious bug in agentic tooling.

## Testing non-determinism

- **Stub the model** for logic tests. Assert on control flow, not prose.
- **Test the failure shapes explicitly**: provider unavailable, prose instead of
  JSON, refusal, truncation, timeout, malformed tool call. Each is a normal
  Tuesday.
- **Property-based tests** for invariants: "never returns a score without
  `assessed: true`", "never reports more files pushed than attempted".
- **Table-driven malformed-input tests.** Wrong types, nulls, bare arrays, bare
  strings, missing keys. This catches the 500s that a happy-path suite never
  sees — and it found a real bug the first fix had missed in practice.
- **Snapshot with care.** Snapshots of model output test the model, not you.

## CI structure

| Gate | Runs | Cadence |
|---|---|---|
| Lint + type | Everything | Every commit |
| Unit | Deterministic logic | Every commit |
| Cheap evals | Faithfulness, relevance (no ground truth) | Every PR touching prompts/retrieval |
| Full evals | All metrics vs golden set | Nightly |
| Adversarial | Injection, jailbreak, traversal | Pre-release |
| Production sampling | 5% of live traffic | Continuous |

Fail the build on a real score drop past a stated tolerance. A regression that
does not fail anything does not get fixed.

## Verification against reality

**Never claim a fix works because the code looks right.**

- Probe the live endpoint with the actual payload.
- Open a real browser for UI claims: dead handlers, console errors, and
  attribute-escaping bugs are invisible in source review.
- Check the database, not just the response.
- Clean up probe data — a tampered row in a shared test DB can produce a large
  number of false failures elsewhere.

**When a probe disagrees with the app, suspect the probe first.** It is right
more often than not: wrong URL prefix, wrong selector, reading before render,
missing CSRF header, wrong environment. Verify the probe before you write up a
finding.

## Suite hygiene

- **A skip is not a pass.** Check the skip count against the known baseline.
  A jump from 2 to 152 skips means a dependency vanished, not that the code got
  better.
- **Update, never silently delete, tests that pinned old buggy behaviour.**
  Rewrite in place with the reasoning inline: what it used to assert, why that
  was wrong, what it asserts now.
- **Keep the suite fast enough to run.** Segment long-running checks; a suite
  nobody runs protects nothing.
- **Clear caches before a revert-proof.** Stale bytecode produces false greens.
