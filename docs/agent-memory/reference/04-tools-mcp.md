# 04 — Tools and MCP

> Tools are the only way an agent changes the world. A loop with no tools is a
> chatbot in a `while` statement.

---

## Tool design — the four rules

1. **Self-contained and non-overlapping.** *Every tool must justify its
   existence.* If you cannot say definitively which tool applies in a given
   situation, neither can the model.
2. **Explicit, unambiguous parameters.** Descriptive names, obvious types, no
   overloaded string fields that mean three things.
3. **Token-efficient returns.** Claude Code caps tool responses at ~25k tokens
   by default. Use pagination, range selection, filtering, and truncation with
   sensible defaults. Effective context will grow; the need for context-efficient
   tools will not go away.
4. **Clear success and failure modes.** A tool that returns `{"ok": true}` on
   failure is worse than a tool that throws.

**The test:** describe the tool as you would to a new hire. If that description
is ambiguous, the schema is wrong.

**Bloated tool sets are the common failure.** Twenty overlapping tools produce
worse behaviour than six clear ones — the model spends its reasoning on
selection rather than on the task.

## Scoped tool loading

Do not load every tool for every task. Load the set the current stage needs.

Why it matters: (a) each tool definition consumes context permanently; (b) a
tool the agent cannot see cannot be misused; (c) selection accuracy falls as the
menu grows. This is least-agency applied to the tool layer, and it is the
cheapest security control available.

Implementation shapes: per-stage allow-lists, capability tiers tied to the
agent's identity, or dynamic loading driven by the task classifier.

## MCP — Model Context Protocol

Open standard for connecting LLM applications to external data and tools.
Host–client–server over JSON-RPC. Ecosystem scale as of 2026: 10k+ public
servers, 97M+ monthly SDK downloads, first-party support across Anthropic,
OpenAI, Google, Microsoft, GitHub, Vercel, VS Code, Cursor.

**Primitives:**

| Side | Primitive | Purpose |
|---|---|---|
| Server | **Tools** | Executable functions the model can invoke |
| Server | **Resources** | Context data (files, records, API responses) |
| Server | **Prompts** | Reusable templates and workflows |
| Client | **Elicitation** | Server asks the *user* for input mid-operation |
| Client | ~~Sampling~~ | Server requests an LLM completion via the client — **deprecated 2026-07-28** |
| Client | ~~Roots~~ | Filesystem/URI scoping — **deprecated 2026-07-28** |

**The 2026-07-28 specification — what changed and why it matters:**

- **Stateless core.** No handshake, no sessions. Every request is
  self-describing, so any request can land on any instance behind plain
  round-robin. This is the change that makes MCP horizontally scalable.
- **Header-based routing.** `Mcp-Method` and `Mcp-Name` travel as HTTP headers,
  so gateways route and authorise without parsing the body.
- **Multi Round-Trip Requests (MRTR).** Replaces server-initiated requests that
  needed a held-open bidirectional stream. A server returns `InputRequiredResult`
  with `inputRequests`; the client gathers input and *retries* the original
  request with `inputResponses`. This is what lets a stateless server still ask
  "are you sure? this will cost $X" before acting.
- **Cacheable list results.** `tools/list`, `prompts/list`, `resources/list`
  carry `ttlMs` and `cacheScope`.
- **Deprecated:** Sampling, Roots, Logging, and the legacy HTTP+SSE transport —
  all with ~12-month off-ramps. New implementations should not adopt them; use
  provider APIs directly instead of sampling.

**Transports:** `stdio` for local, **Streamable HTTP** for remote. HTTP+SSE is
deprecated.

**Agent-native server design.** Design servers around *workflows and user
intent*, not as a 1:1 mirror of an existing REST API. The question is "how would
a human accomplish this task", not "what endpoints do we have". Use structured
outputs, resources, and elicitation rather than returning raw JSON blobs.

## MCP security — treat servers as a supply chain

The OWASP MCP Top 10 is its own list for a reason:

| ID | Risk |
|---|---|
| MCP01 | Token mismanagement & secret exposure |
| MCP02 | Privilege escalation via scope creep |
| MCP03 | Tool poisoning |
| MCP04 | Supply-chain / dependency tampering |
| MCP05 | Command injection & execution |
| MCP06 | Intent flow subversion |
| MCP07 | Insufficient authn/authz |
| MCP08 | Lack of audit & telemetry |
| MCP09 | Shadow MCP servers |
| MCP10 | Context injection & over-sharing |

Real incidents: a malicious server impersonating Postmark and silently
forwarding email; typosquatted tools; "agent-in-the-middle" servers advertising
inflated capabilities; tool descriptors carrying malicious metadata.

**Controls that actually help:** pin versions; allow-list capabilities rather
than servers; review tool *descriptions* as executable content (they enter the
model's context and can carry instructions); require mutual auth for remote
servers; log every tool invocation with arguments; deny-by-default egress from
tool sandboxes; maintain an AI-BOM of installed servers and their provenance.

## Tool execution safety

- **Sandbox anything that executes code.** Hardware-enforced where possible.
  Deny-by-default network egress from the sandbox.
- **Never pass model output to `eval()`, a shell, or an ORM without
  validation.** Improper output handling (LLM05) is how a text bug becomes RCE.
- **Parameterise identifiers as well as values.** A parameterised `?` protects
  the value while an interpolated column name is wide open — this is the classic
  form of the bug and it is easy to miss precisely because the query *looks*
  parameterised.
- **Validate the parameters the model chose**, not just the ones you documented.
  Parameter pollution is a named attack (ASI02).
- **Human gate on destructive actions**, matched on a *normalised* action name.
  A gate keyed on exact strings is defeated by capitalisation.

## Failure modes specific to this layer

- **Tool reports success it did not achieve.** The most common and most
  damaging: partial writes reported as complete, no-op reported as done.
- **Guard on one entry point, not its twin.** Streaming vs non-streaming;
  install vs import; create vs update. Always ask where else this shape exists.
- **Silent capability discard.** A caller asks for `max_runs: 1`, gets `ok:
  true`, and receives an unbounded loop — strictly worse than rejecting the
  request, because the user believes the limit is active.
- **Tool descriptions as an injection channel.** They are model-visible text
  from a third party. Treat accordingly.
- **Unbounded tool output.** One `cat` of a large file evicts the plan from
  context.
- **No audit of tool calls.** When something goes wrong you cannot reconstruct
  what the agent actually did.
