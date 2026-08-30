"""ICM review: `/api/icm/describe` silently dropped most of the user's stages.

MODULE REVIEW — icm (Workspaces). The pane had no review document and carried
the highest risk score in scripts/audit/module_risk.py (940 JS + 704 py router
+ 3,456 py services across 8 modules, 37 endpoints).

Most of ICM is in good shape. Verified live before changing anything:

    workspace create        -> 200, stages numbered 01-/02-/03-
    walk test               -> can_orient / can_find_work / can_report_status
    entry routing           -> "first stage with no output"
    layered context (L0-L4) -> compiled, correct order
    file read/write         -> 200, re-runs the walk test on save
    path traversal x5       -> "Path escapes the workspace" / 404
    write without CSRF      -> 403
    malformed create x7     -> 400/409/422, nothing created
    pane + all six tabs     -> render, 0 page errors, 0 failed requests

THE DEFECT
──────────
`POST /api/icm/describe` turns a plain-English description of your work into a
proposed workspace. It splits the narrative at SEQUENCE_MARKERS ('then',
'next', 'finally'...). Nothing else opened a boundary.

But people LIST their stages at least as often as they narrate them, and a
comma is not a sequence marker. Measured against the live endpoint:

    "Every week I research a topic, draft an article, then review it"
        -> ['research', 'review']                    'draft' lost
    "I research, draft, edit, and publish each piece."
        -> ['research']                              three lost
    "I intake the request, triage it, assign an owner, and close it out."
        -> ['intake']                                three lost

This is worse than an obvious failure. The proposal looks considered — it
names a form, cites evidence, explains its reasoning — and invites the user to
confirm a structure that quietly omits most of their process. Under the ICM
canon the stage list IS the architecture, so a dropped stage is a folder that
never exists and work that has nowhere to go.

THREE CAUSES, all required for the full fix
────────────────────────────────────────────
1. Only sequence markers cut. A comma or "and" followed by a known stage verb
   is now also a boundary (_LIST_RE). It is restricted to the curated
   STAGE_VERBS vocabulary so ordinary prose -- "a topic, an article" -- cannot
   shred a sentence into noise.

2. A two-word floor discarded the survivors. Fixing the split alone still lost
   'draft', because the fragment is one word. The floor exists to drop debris
   ("it", "that") and is kept -- except for a fragment that IS a stage verb.

3. The vocabulary was written around content production. A support or ops
   workflow matched almost nothing, so 'intake'/'triage'/'assign'/'close' and
   16 similar case-handling verbs were added.

AFTER, same inputs:
    ['research', 'draft', 'review']
    ['research', 'draft', 'edit', 'publish']
    ['intake', 'triage', 'assign', 'close']
and non-process prose still yields ONE stage -- no over-fragmentation.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services.icm_dialogue import (  # noqa: E402
    STAGE_VERBS,
    analyse,
    extract_stages,
)


def _names(text: str) -> list[str]:
    return [s["name"] for s in extract_stages(text)]


# ── the reported shapes ──────────────────────────────────────────────────────

def test_a_comma_list_with_a_trailing_then_keeps_every_stage() -> None:
    """Pre-fix: ['research', 'review'] — 'draft' silently dropped."""
    got = _names("Every week I research a topic, draft an article, "
                 "then review it before publishing.")
    assert got == ["research", "draft", "review"], got


def test_a_pure_comma_list_keeps_every_stage() -> None:
    """Pre-fix: ['research'] — three of four stages dropped. No sequence
    marker appears anywhere in this sentence."""
    got = _names("I research, draft, edit, and publish each piece.")
    assert got == ["research", "draft", "edit", "publish"], got


def test_an_operations_workflow_is_understood() -> None:
    """Pre-fix: ['intake'] — the vocabulary only knew content-production verbs,
    so a support/ops process collapsed to a single stage."""
    got = _names("I intake the request, triage it, assign an owner, "
                 "and close it out.")
    assert got == ["intake", "triage", "assign", "close"], got


def test_narrated_sequences_are_unaffected() -> None:
    """The original marker path must keep working exactly as before."""
    got = _names("First I gather requirements, then I design, "
                 "then I build, then I ship.")
    assert got == ["gather", "design", "build", "ship"], got


# ── the guardrails: no over-fragmentation ────────────────────────────────────

def test_ordinary_prose_does_not_fragment() -> None:
    """Only the curated verb list opens a cut. Commas between plain nouns must
    not invent stages — a proposal with six imaginary stages is as wrong as
    one with three missing."""
    assert _names("I take notes.") == ["take"]
    assert _names("We meet, discuss the roadmap, and go home.") == ["meet"]


def test_object_nouns_after_a_verb_do_not_become_stages() -> None:
    """'research a topic, an article, and a summary' is ONE stage with three
    objects, not three stages."""
    got = _names("I research a topic, an article, and a summary.")
    assert got == ["research"], got


def test_the_same_verb_twice_is_still_one_stage() -> None:
    """'One stage, one job' cuts both ways — the pre-existing dedupe must
    survive the new splitting."""
    got = _names("I draft the intro, then draft the body.")
    assert got == ["draft"], got


def test_short_debris_is_still_discarded() -> None:
    """The two-word floor is relaxed only for known stage verbs, not removed."""
    got = _names("I plan the week, it, and that.")
    assert got == ["plan"], got


# ── the vocabulary ───────────────────────────────────────────────────────────

def test_case_handling_verbs_are_in_the_vocabulary() -> None:
    for verb in ("intake", "triage", "assign", "route", "escalate",
                 "resolve", "close", "qualify", "onboard", "verify"):
        assert verb in STAGE_VERBS, f"{verb!r} missing — ops workflows collapse"


def test_the_vocabulary_has_no_duplicates() -> None:
    """A duplicate is harmless at runtime but means two people added the same
    verb without seeing each other's edit."""
    assert len(STAGE_VERBS) == len(set(STAGE_VERBS))


# ── the endpoint contract ────────────────────────────────────────────────────

def test_analyse_returns_the_stages_it_extracted() -> None:
    """The bug reached the user through analyse(), so assert at that level too
    and not only at the splitter."""
    out = analyse("I research, draft, edit, and publish each piece.")
    assert out["ok"] is True
    assert [s["name"] for s in out["stages"]] == \
        ["research", "draft", "edit", "publish"]


def test_every_stage_explains_why_it_was_identified() -> None:
    """The pane shows this reasoning so the user can correct a wrong guess.
    A stage with no explanation is unreviewable."""
    for stage in extract_stages("I research, draft, and publish."):
        assert stage["why"], f"{stage['name']} has no rationale"
        assert stage["said"], f"{stage['name']} does not quote the user"
