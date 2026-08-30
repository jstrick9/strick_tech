"""Inbox review: capture worked, filing could not.

MODULE REVIEW 2 of 2 — inbox. The second of the two destinations with no
review document, and the thinnest tested surface in the app (416 lines, one
test file).

The pane's promise is "Capture anything, the router files it." Capture worked.
Filing was unreachable for a new user, for two independent reasons.

DEFECT 1 — a new workspace could never receive anything
────────────────────────────────────────────────────────
`icm_router.parse_routes()` reads trigger phrases from a `## Routes` section of
a workspace's L1 CONTEXT.md. The scaffolder never wrote that section. Verified
on a freshly created workspace: the generated CONTEXT.md contained `# Routing`,
a stage table and `## Conventions` — no `## Routes` — and the ICM pane has no
UI for adding one, only a read-only view that says "No routes declared".

So every sweep left everything in the inbox, and the only documented way to fix
it was to know the exact markdown heading and hand-edit the file. The feature
was complete on both sides and had no path between them.

Scaffolding now emits an empty `## Routes` section with a comment explaining
what belongs there and what happens without it. Empty is correct — inventing
routes for the user would file their notes somewhere they never chose — but
absent is not, because absent is invisible.

DEFECT 2 — declared routes still did not match real sentences
──────────────────────────────────────────────────────────────
`score_workspace()` required the whole route phrase CONTIGUOUSLY:

    if f' {phrase} ' in hay:

A workspace declaring `- vendor renewal quote` scored **0.0** against

    "Follow up with the vendor about the renewal quote"

Every word is present, in order, separated by two filler words. The sweep
reported "no workspace declared a route for this request (best: ... at 0.0)"
— which is actively misleading, because a route WAS declared and it did match
in every sense a person would mean.

Measured before the fix: `score 0.0, evidence []`.

A route is a human's stated intent, not a search query, so near misses count.
A multi-word route now earns partial credit when a clear majority of its words
appear, scaled by the fraction matched and multiplied by W_ROUTE_PARTIAL
(0.75) so an exact phrase always outranks a near miss.

END TO END, after both fixes, through HTTP against a live server:

    POST /api/inbox        -> captured
    PUT  .../CONTEXT.md    -> "- vendor renewal quote"
    POST /api/inbox/sweep  -> filed: vendor-ops / 01-intake
                              reason: route: 'vendor renewal quote' (3/3 words)
    GET  /api/inbox/stats  -> inbox 0, filed 1
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import icm, icm_router  # noqa: E402


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A real scaffolded workspace on disk, isolated from the user's data."""
    root = tmp_path / "icm"
    root.mkdir()
    monkeypatch.setattr(icm, "WORKSPACES_DIR", root)
    monkeypatch.setattr(icm_router, "list_workspace_dirs",
                        lambda: sorted(p for p in root.iterdir() if p.is_dir()))
    ws = root / "vendor-ops"
    ws.mkdir()
    icm.scaffold(ws, "Vendor Ops", "", ["intake", "review"])
    return ws


def _declare(ws: Path, *phrases: str) -> None:
    text = (ws / "CONTEXT.md").read_text(encoding="utf-8")
    bullets = "".join(f"- {p}\n" for p in phrases)
    (ws / "CONTEXT.md").write_text(
        text.replace("## Routes\n", f"## Routes\n{bullets}", 1), encoding="utf-8")


# ── defect 1: the section must exist to be discoverable ──────────────────────

def test_a_new_workspace_ships_a_routes_section(workspace) -> None:
    """Pre-fix this section did not exist, so parse_routes() always returned
    [] and no captured item could ever be filed."""
    text = (workspace / "CONTEXT.md").read_text(encoding="utf-8")
    assert "## Routes" in text, (
        "no ## Routes section — the inbox router has nothing to read and every "
        "sweep will leave items unfiled"
    )


def test_the_routes_section_explains_itself(workspace) -> None:
    """An empty heading is a puzzle. The comment has to say what goes there and
    what happens without it, because there is no UI for this yet."""
    text = (workspace / "CONTEXT.md").read_text(encoding="utf-8")
    section = text[text.index("## Routes"):]
    assert "Inbox router" in section
    assert "-" in section, "no example bullet to copy"


def test_the_stub_declares_no_routes(workspace) -> None:
    """Empty is correct. Inventing routes would file a user's notes somewhere
    they never chose — the wrong-folder failure ICM exists to prevent."""
    assert icm_router.parse_routes(workspace) == []


def test_the_commented_example_is_not_parsed_as_a_route(workspace) -> None:
    """The stub contains `- weekly client report` inside an HTML comment as an
    example. If the parser read it, every workspace would silently claim that
    traffic."""
    routes = icm_router.parse_routes(workspace)
    assert "weekly client report" not in routes, (
        "the example inside the comment is being parsed as a real route"
    )


# ── defect 2: scattered words must score ─────────────────────────────────────

def test_a_route_matches_when_its_words_are_not_adjacent(workspace) -> None:
    """THE BUG. Pre-fix: score 0.0, evidence [], "no workspace declared a
    route for this request"."""
    _declare(workspace, "vendor renewal quote")
    decision = icm_router.resolve(
        "Follow up with the vendor about the renewal quote")
    assert decision["matched"] is True, decision["reason"]
    assert decision["workspace_id"] == "vendor-ops"
    assert "vendor renewal quote" in decision["reason"]


def test_an_exact_phrase_still_outranks_a_near_miss(workspace, tmp_path) -> None:
    """Partial credit must not let a scattered match beat a literal one, or
    the more precisely written route loses."""
    _declare(workspace, "vendor renewal quote")
    other = tmp_path / "icm" / "exact-co"
    other.mkdir()
    icm.scaffold(other, "Exact Co", "", ["intake"])
    _declare(other, "vendor renewal quote")

    scattered = icm_router.score_workspace(
        "the vendor sent a renewal and a quote", workspace)
    exact = icm_router.score_workspace("vendor renewal quote today", other)
    assert exact["score"] > scattered["score"], (exact, scattered)


def test_one_stray_word_does_not_win_the_route(workspace) -> None:
    """A clear majority of the route's words is required. Otherwise a route
    like 'client invoice reminder' would capture any message containing
    'client'."""
    _declare(workspace, "client invoice reminder")
    result = icm_router.score_workspace("a note about the client", workspace)
    assert result["score"] == 0.0, result


def test_a_single_word_route_still_needs_the_word(workspace) -> None:
    """Partial credit applies to multi-word routes only; there is no fraction
    of one word."""
    _declare(workspace, "invoice")
    assert icm_router.score_workspace("send the bill", workspace)["score"] == 0.0
    assert icm_router.score_workspace("the invoice is due", workspace)["score"] > 0


def test_the_decision_always_says_why(workspace) -> None:
    """Both outcomes must be explainable — a silent no-match is what made this
    defect survive."""
    _declare(workspace, "vendor renewal quote")
    matched = icm_router.resolve("vendor renewal quote please")
    assert matched["reason"]
    unmatched = icm_router.resolve("something entirely unrelated")
    assert unmatched["reason"]
    assert unmatched["matched"] is False


def test_partial_weight_is_below_one(workspace) -> None:
    """The invariant behind test_an_exact_phrase_still_outranks_a_near_miss."""
    assert 0 < icm_router.W_ROUTE_PARTIAL < 1.0
