# 06 — Governance: Oversight, Audit, Compliance

> An autonomous system that cannot be inspected, stopped, or accounted for is
> not deployable — regardless of how well it performs.

---

## The four properties of a governed agent system

1. **Attributability** — every action traces to an agent, a version, a
   triggering identity, and a timestamp.
2. **Boundedness** — enforced caps on cost, scope, and blast radius.
3. **Reviewability** — a human can reconstruct what happened and why.
4. **Stoppability** — any running agent halts within 60 seconds, via a
   procedure **tested at least monthly**.

A kill switch that exists only in documentation does not satisfy anything. Test
it on a schedule and log the test.

## Human-in-the-loop

**Confidence-threshold gating.** Route to a human when confidence falls below a
threshold that varies by risk level. Two rules make this work:

- **Always-interrupt list.** Actions that reach a human regardless of stated
  confidence: delete, send (email/message/post), charge, deploy to production,
  force-push, rotate or delete secrets. Match on a **normalised** action name —
  case, whitespace, and separator folded — or the gate is defeated by
  capitalisation.
- **Unrecognised risk level fails towards oversight.** An unknown value must
  escalate, never silently downgrade to a permissive default.

**The confidence input is supplied by the agent.** Clamp it, and treat a missing
or unparseable value as *low*, never as high.

**Record the machine's decisions too.** Auto-approvals are the decisions no
human ever saw, which makes them the ones most worth being able to review. A
system that logs only human approvals has its oversight record exactly inverted.

Keep them **distinguishable**: `status='auto_approved'` is not `status='approve'`.
Report an approval rate over human decisions only, with the basis stated, and
report the machine's share separately — otherwise a flood of auto-approvals
pushes the rate towards 100% and reads as "humans approve almost everything".

**Undo.** Snapshot before destructive actions. And a *failed* undo must never
report success — the user has just been told their action was reverted, so they
stop looking. That is the most damaging false success in the whole system.

## Audit trails

Five layers, all required:

1. **Registry** — agents/models with version, owner, risk tier, approval.
2. **Version history** — prompts, tools, policies, with diff and approval.
3. **Per-request traces** — tool calls, retrieval sources, guardrail decisions,
   judge scores, token cost.
4. **Incident log** — severity, root cause, remediation.
5. **Periodic reports** — mapped to whichever framework binds you.

**Properties:** append-only, tamper-evident (hash-chained), retention set per
record type, and separable — access to trace *metadata* is a different
permission from access to trace *payloads*, because payloads contain user data
most roles do not need.

**Coverage is the thing that fails.** An audit log that covers the local
database and is silent about the remote one reads as authoritative either way.
A gap you cannot see is worse than a gap you can. When you add a surface, add
its audit at the same time.

## Budgets and cost

- Enforce at the kernel, not per-router (see `01-kernel.md`).
- The UI's budget store and the enforcer's budget store must be **the same
  store**. Two unrelated budget tables — one written by the UI, one read by the
  enforcer — is a guardrail that exists only on screen.
- Report `enforced` as **measured** against the enforcement mechanism, not
  inferred from the rule's own stated action.
- Denial-of-Wallet is a real attack (LLM10): per-session token caps, rate
  limits, and alerting on spend anomalies.

## Regulatory landscape

**EU AI Act** — high-risk obligations enforceable from **2 August 2026**:

| Article | Requirement | Evidence artefact |
|---|---|---|
| Art. 9 | Risk management system | Risk register, control mapping |
| Art. 11 / Annex IV | Technical documentation | Architecture, data governance, risk docs |
| Art. 12 | Automatic lifetime logging | Immutable traces with version metadata |
| Art. 14 | **Human oversight** — understand, monitor, intervene, halt | Override decision log with operator identity + timestamp |
| Art. 26 | Deployer log retention ≥ 6 months | Retention policy |
| Art. 72 | Post-market monitoring | Drift and incident records |

Article 14 is the one that bites agentic systems. It requires that a human can
*understand system behaviour, monitor outputs, and halt or intervene*. The
override log is itself a required artefact — which is exactly why unlogged
auto-approvals are a compliance defect and not merely untidy.

**NIST AI RMF** — Govern / Map / Measure / Manage. Measure and Manage explicitly
require ongoing monitoring of deployed systems, so evaluation history and drift
detection *are* the compliance evidence.

**ISO/IEC 42001** — management system; continuous monitoring records.

**SOC 2** — change management (prompt/config version history with approvals),
access control (RBAC + SSO with access logs), monitoring over the audit period.

**GDPR** — lawful basis, minimisation, erasure (with its own audit record),
transfer restrictions, and a DPA that covers evaluation-time model calls.

**The reframe that unblocks most programs:** governance is an *observability*
problem. Teams write policies describing systems that emit no records capable of
verifying compliance. Build the records first; the documents then describe
something real.

## RBAC for agent systems

Minimum roles: engineers (full trace, propose config), PM/domain (product-scoped
read + annotate), QA reviewers (queue-scoped), compliance/audit (read all — with
their own access logged — plus approval rights), platform admins.

Per-agent identity with **short-lived, scoped credentials**. Never a shared key.
Quarterly access certification with documented outcomes.

## Failure modes specific to this layer

- **Oversight record inverted.** Human decisions logged; machine decisions not.
- **Approval rate that mixes machine and human.** Reads as consent that was
  never given.
- **A guardrail the UI writes and nothing reads.** The user sets a cap, sees it
  listed, and believes they are protected.
- **Untested kill switch.**
- **Audit gap at a second surface.** Local covered, remote silent.
- **`localtime` published as UTC.** Timestamps converted to local wall-clock and
  then stamped `Z` misreport every event by the offset — invisible in a UTC
  environment, wrong everywhere else.
- **Governance as documentation.** Policies with no enforcing control and no
  emitted evidence.
