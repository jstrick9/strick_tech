# ICM Workspaces — folder structure as agent architecture

Implements the **Model Workspace Protocol** from *Interpretable Context
Methodology: Folder Structure as Agentic Architecture* (Van Clief & McDermott,
arXiv:2603.16021, MIT). Background and rationale: `AGENTIC-OS-RESEARCH.md` §6.

**Code:** `backend/services/icm.py` (rules) · `backend/routers/icm.py` (transport)
**Tests:** `tests/unit/test_148_icm_workspace.py` (39)

---

## What this is

An ICM workspace replaces framework orchestration with filesystem structure:

| Framework concern | ICM mechanism |
|---|---|
| Stage sequencing | Folder **numbering** (`01-`, `02-`) |
| Context scoping | Folder **hierarchy** |
| State management | **Files on disk** |
| Stage coordination | One stage's `output/` is the next stage's input |
| Observability | **Open the folder and read it** |

One agent reads the right files at the right moment. There is no orchestrator
process, no message bus, and no state machine.

---

## Layout

```
memory/icm/<workspace_id>/
  IDENTITY.md              L0  identity + goals        (always loads)
  CONTEXT.md               L1  routing: which stage handles what
  _config/conventions.md   L3  house rules
  shared/                  L3  cross-stage resources
  stages/
    01-research/
      CONTEXT.md           L2  the STAGE CONTRACT      (control point)
      references/          L3  stage-scoped reference material
      output/              L4  working artifacts       (handoff point)
    02-script/  …
    03-production/  …
  .icm.json                metadata
```

L3 persists across runs. L4 changes every run.

---

## The stage contract

Every stage declares **Inputs / Process / Outputs**. The Inputs table is the
control point of the whole system — it names the file *and the section*:

```markdown
## Inputs
| Source         | File/Location            | Section/Scope | Why             |
|----------------|--------------------------|---------------|-----------------|
| Previous stage | ../01-research/output/   | Full file     | Source material |
| Style guide    | ../../_config/voice.md   | Tone Rules    | Tone guidance   |

## Process
1. Read the research output
2. Write following the tone rules
3. Save to output/

## Outputs
| Artifact | Location            | Format   |
|----------|---------------------|----------|
| Script   | output/script.md    | Markdown |
```

**Anything the table does not name is not loaded.** Verified live: a reference
file with a 200-line appendix contributed only its `Tone Rules` section.

---

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/icm/workspaces` | List with stage progress |
| POST | `/api/icm/workspaces` | Scaffold from stage names |
| GET | `/api/icm/workspaces/{id}` | Detail + parsed contracts |
| DELETE | `/api/icm/workspaces/{id}` | Remove |
| GET | `/api/icm/workspaces/{id}/entry` | **Where should an agent start?** |
| GET | `/api/icm/workspaces/{id}/context` | Assemble layered context |
| GET | `/api/icm/workspaces/{id}/validate` | Walk test + conventions |
| GET/PUT | `/api/icm/workspaces/{id}/file` | Read/edit any artifact |

---

## The failure mode this design prevents

From the author's notes on ICM in practice:

> "When you add more and more folders agents begin to skip information.
> Guidelines are missed, rules are overlooked… the model scans economically and
> thinks it knows enough. The solution is again simple, the agent has to
> actually start in the right folder."

In a team, *"just cd to the correct directory"* is the invisible, error-prone
step that breaks repeatability. So **entry is computed, never assumed**:

- `resolve_entry()` returns the first stage with no output.
- An explicit request wins — but an **unknown** stage is refused, not silently
  defaulted to the first. Silently starting elsewhere *is* the failure.
- `/context` with no `stage` resolves automatically.
- Unnumbered folders under `stages/` are not stages, and `validate()` **names
  them** rather than skipping in silence.

---

## Measured behaviour (live)

| Check | Result |
|---|---|
| Scaffold 3 stages | 10 files, walk test passes |
| Stage 01 context | ~420 tokens (L0+L1+L2+L3) |
| Stage 02 after 01 writes output | picks up `01-research/output/` as L4 automatically |
| Entry after 01 completes | advances `01-research` → `02-script` |
| Selective section routing | loaded `Tone Rules`, excluded 200 filler lines |
| Contract naming `/etc/passwd` | refused, reported in `missing_inputs` |

Per-stage context is **hundreds of tokens**, against the 30–50k a monolithic
prompt reaches. That gap is the entire point of the methodology.

---

## Security

This context is concatenated into an LLM **system prompt**, so a traversal here
is an arbitrary-file-read fed to a model. Four vectors are closed and tested:

1. Workspace id — regex + `safe_path()` (same two-layer guard as `hierarchy.py`)
2. File read — resolved path must stay inside the workspace
3. File write — same
4. **Contract `Inputs` path** — the subtle one: a malicious `CONTEXT.md` naming
   `../../../../etc/passwd` is refused and reported

---

## Validation — the walk test, mechanised

The paper's acceptance criterion: an agent with no memory opens the root, finds
its way, acts, and reports status **from the files alone**.

**Errors** (workspace is broken): no L0 identity · no L1 routing · no numbered
stages · duplicate stage numbers · stage without a contract · **forward
reference** (a stage reading from a later stage breaks the one-way rule).

**Warnings** (works, but drifts from convention): unnumbered folder ·
`CONTEXT.md` over 80 lines · reference over 200 lines · no Inputs/Process/
Outputs declared · missing `output/`.

---

## Chat integration

`chat.py` names a workspace → resolves the entry stage → injects only that
stage's context. It calls `resolve_entry()` rather than assuming a stage, which
is pinned by a test.

---

## Relationship to `hierarchy.py`

**Additive, not a replacement.** They are complementary:

| | `hierarchy.py` | `icm.py` |
|---|---|---|
| Shape | Fixed 2-tier (Tier 1 + IVREN) | Arbitrary numbered stages |
| Scope | Who the user is, per project | How a workflow runs, per stage |
| Maps to | ICM's `_config/` (L3) | ICM stages (L2/L4) |

Tier 1 answers *"who am I writing for?"*; ICM answers *"what step am I on?"*
Both inject into chat; neither was changed by the other.

---

## Conventions enforced

- One stage, one job
- Plain markdown as the interface
- Every output is an edit surface
- Canonical sources — one home per fact
- One-way references
- Selective section routing
- `CONTEXT.md` < 80 lines, references < 200 lines
- Configure the factory, not the product

---

## Next

Ontologies (typed entities/relations in `_config/`) are the natural extension:
the `.md` + section-routing substrate is now in place to carry them.
