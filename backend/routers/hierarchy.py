"""
Agentic OS — Information Hierarchy Router (`/api/hierarchy`)
Implements the compounding 2-Tier Information Hierarchy created by Joshua Strickland and Strick Tech.
Tier 1: 4 core files (about_me.md, about_my_business.md, about_my_voice.md, about_my_offers.md)
Tier 2: Project folders with 5 IVREN subfolders (instructions, voice, references, examples, notes)
"""
from __future__ import annotations

import json
import pathlib
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/hierarchy", tags=["hierarchy"])

from backend.config import get_data_dir

from ..services.safe_paths import safe_path

ROOT = get_data_dir()
HIERARCHY_DIR = ROOT / "memory" / "hierarchy"
TIER1_DIR = HIERARCHY_DIR / "tier1"
PROJECTS_DIR = HIERARCHY_DIR / "projects"

# Ensure directories exist
TIER1_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

# Default Tier 1 templates.
#
# These are PROMPTS, not content. They previously shipped the author's own
# name, company, product tiers and pricing as the default for every install:
#
#   - **Name:** Joshua Strickland
#   - **Company Name:** Strick Tech
#   - **Free Version:** ... **Pro Version:** ... **Enterprise Version:** ...
#
# Because /compiled-context is concatenated into the system prompt by chat.py,
# every user's AI was silently told it was working for someone else's business
# until they happened to find and rewrite these four files. Worse, the content
# is confidently phrased, so the model has no way to tell placeholder text from
# real user context — it would cite another company's pricing as fact.
#
# A template that is obviously unfilled is far more useful than a plausible
# wrong answer: the model can say "your profile isn't set up yet", and
# /status can detect it (see _is_placeholder).
PLACEHOLDER_MARKER = '<!-- agentic-os:unfilled -->'

DEFAULT_TIER1 = {
    "about_me": f"""# About Me
{PLACEHOLDER_MARKER}
> Not filled in yet. Replace the prompts below with your own details, or use
> the guided interview in AI Context & Guidelines.

- **Name:** _(your name)_
- **Role:** _(what you do)_
- **Company / Project:** _(where you do it)_
- **One-Line Intro:** _(how you'd describe yourself in a sentence)_
- **Background:** _(experience and focus that an assistant should know about)_
""",
    "about_my_business": f"""# About My Business
{PLACEHOLDER_MARKER}
> Not filled in yet.

- **Company Name:** _(name)_
- **What We Do:** _(the product or service, in plain terms)_
- **Target Audience / ICP:** _(who it is for)_
- **Unique Value Proposition:** _(why someone chooses you)_
""",
    "about_my_voice": f"""# About My Voice & Tone
{PLACEHOLDER_MARKER}
> Not filled in yet. This one has the largest effect on output quality —
> being specific about words to avoid is usually worth more than the rest.

- **Writing Style:** _(e.g. concise and direct, or warm and discursive)_
- **Tone:** _(e.g. professional, playful, academic)_
- **Words & Phrases I Like:** _(terms that sound like you)_
- **Words & Phrases to Avoid:** _(pet hates — the model will genuinely avoid them)_
- **Formatting Rules:** _(bullets vs prose, paragraph length, code examples)_
""",
    "about_my_offers": f"""# About My Offers & Pricing
{PLACEHOLDER_MARKER}
> Not filled in yet.

- **Core Product / Service:** _(what you sell or deliver)_
- **Tiers / Packages:** _(names and what each includes)_
- **Pricing:** _(or "not public" if you would rather the assistant not quote it)_
""",
}


def _is_placeholder(text: str) -> bool:
    """True when a Tier 1 file is still the unedited template.

    Detected by an explicit marker rather than by comparing against the default
    text, so a user who edits one line doesn't stay flagged as unconfigured
    forever, and reformatting the templates later doesn't break detection.
    """
    return PLACEHOLDER_MARKER in (text or '')


# Default IVREN project templates
DEFAULT_IVREN = {
    "instructions": """# Project Master Instructions (CLAW / SPEC)
- **Project Name:** {name}
- **Goal:** Deliver high-quality, specialized outputs for this specific domain.
- **Target Audience:** {audience}
- **Definition of Good Output:** Clear, actionable, well-formatted, and completely aligned with project requirements.
- **What to Avoid:** Fluff, unnecessary disclaimers, or generic assumptions.
""",
    "voice": """# Project Specific Voice & Tone Deltas
- **Tone Adjustments:** Maintain universal tone (`about_my_voice.md`) but adapt for {name} specificity.
- **Domain Terminology:** Use exact domain terminology and client preferences.
""",
    "references": """# References, SOPs & Background Context
- **SOPs:** Add Loom transcripts, process notes, or API specifications here.
- **Key Links:** Reference documentation and internal architecture manuals.
""",
    "examples": """# 10/10 Examples of Good Work
- **Example 1:** Add a past newsletter issue, winning email copy, or ideal code snippet here.
- **Example 2:** Showcase ideal structure and tone.
""",
    "notes": """# Feedback Loop & Compounding Notes
- [{date}] Initial project hierarchy created.
- [{date}] Tip: Always include concrete data points and bulleted executive summaries.
""",
}


_PROJECT_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_]{0,63}$')


def normalize_project_id(raw: str) -> str:
    """Fold a caller-supplied project id into the safe id form."""
    pid = str(raw or '').strip().lower().replace(' ', '_').replace('-', '_')
    # Strip anything that could carry path meaning. Doing this BEFORE the
    # regex check means a traversal attempt fails validation rather than
    # silently becoming a different, valid-looking id.
    return re.sub(r'[^a-z0-9_]', '', pid)[:64]


def project_dir(project_id: str) -> pathlib.Path | None:
    """Resolve a project directory, or None if the id escapes PROJECTS_DIR.

    The id must first pass _PROJECT_ID_RE, so path separators and dots never
    reach the filesystem call at all; safe_path() is the second layer.

    Both matter here: compiled-context output is concatenated into the LLM
    system prompt by chat.py, so traversal is an arbitrary-file-read whose
    results are handed to the model.
    """
    if not project_id or not _PROJECT_ID_RE.match(str(project_id)):
        return None
    return safe_path(project_id, base=PROJECTS_DIR)


def _require_project(project_id: str) -> pathlib.Path:
    """Return an existing project directory or raise the right HTTP error."""
    pdir = project_dir(project_id)
    if pdir is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid project_id '{project_id}': use lowercase letters, "
                f'digits and underscores only.'
            ),
        )
    if not pdir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project hierarchy '{project_id}' not found")
    return pdir


def _ensure_tier1_init() -> None:
    """Ensure all 4 Tier 1 universal context files exist with default templates if not already present."""
    for key, content in DEFAULT_TIER1.items():
        file_path = TIER1_DIR / f"{key}.md"
        if not file_path.exists():
            file_path.write_text(content, encoding="utf-8")


class Tier1SaveRequest(BaseModel):
    """Pydantic data model for Tier1SaveRequest."""
    about_me:str | None = None
    about_my_business:str | None = None
    about_my_voice:str | None = None
    about_my_offers:str | None = None


class InterviewAnswerRequest(BaseModel):
    """Pydantic data model for InterviewAnswerRequest."""
    name_and_role: str
    business_and_icp: str
    voice_and_words: str
    offers_and_pricing: str


class ProjectCreateRequest(BaseModel):
    """Pydantic data model for ProjectCreateRequest."""
    project_id: str
    name: str
    audience: str = "General audience"
    description: str = "Specialized AI project hierarchy"


class ProjectSaveRequest(BaseModel):
    """Pydantic data model for ProjectSaveRequest."""
    instructions:str | None = None
    voice:str | None = None
    references:str | None = None
    examples:str | None = None
    notes:str | None = None


class NoteAppendRequest(BaseModel):
    """Pydantic data model for NoteAppendRequest."""
    note: str
    author: str = "user"


@router.get("/status")
def get_hierarchy_status() -> dict[str, Any]:
    """Retrieve the overall health and file counts of the 2-Tier Information Hierarchy."""
    _ensure_tier1_init()
    tier1_files = {}
    tier1_unfilled = []
    for key in ("about_me", "about_my_business", "about_my_voice", "about_my_offers"):
        path = TIER1_DIR / f"{key}.md"
        tier1_files[key] = path.exists()
        # "The file exists" was the only signal, and _ensure_tier1_init()
        # creates all four on first read — so `initialized` was ALWAYS true and
        # the UI could never tell a configured profile from an untouched one.
        if path.exists() and _is_placeholder(path.read_text(encoding="utf-8")):
            tier1_unfilled.append(key)
    projects = []
    if PROJECTS_DIR.exists():
        for p in sorted(PROJECTS_DIR.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                projects.append({
                    "project_id": p.name,
                    "meta": _get_project_meta(p.name),
                    "ivren_files": {
                        "instructions": (p / "instructions" / "instructions.md").exists(),
                        "voice": (p / "voice" / "voice.md").exists(),
                        "references": (p / "references" / "references.md").exists(),
                        "examples": (p / "examples" / "examples.md").exists(),
                        "notes": (p / "notes" / "notes.md").exists(),
                    }
                })
    return {
        "ok": True,
        "initialized": all(tier1_files.values()),
        # `initialized` only means the files exist. `configured` means the user
        # has actually replaced the templates — which is what callers care about.
        "configured": not tier1_unfilled,
        "tier1": tier1_files,
        "tier1_unfilled": tier1_unfilled,
        "project_count": len(projects),
        "projects": projects,
        "timestamp": time.time(),
    }


@router.get("/tier1")
def get_tier1_files() -> dict[str, Any]:
    """Retrieve the Markdown content of the 4 Universal Context files."""
    _ensure_tier1_init()
    return {
        "ok": True,
        "about_me": (TIER1_DIR / "about_me.md").read_text(encoding="utf-8"),
        "about_my_business": (TIER1_DIR / "about_my_business.md").read_text(encoding="utf-8"),
        "about_my_voice": (TIER1_DIR / "about_my_voice.md").read_text(encoding="utf-8"),
        "about_my_offers": (TIER1_DIR / "about_my_offers.md").read_text(encoding="utf-8"),
    }


@router.post("/tier1")
def save_tier1_files(payload: Tier1SaveRequest) -> dict[str, Any]:
    """Update existing Tier 1 universal context files with provided Markdown text."""
    _ensure_tier1_init()
    if payload.about_me is not None:
        (TIER1_DIR / "about_me.md").write_text(payload.about_me, encoding="utf-8")
    if payload.about_my_business is not None:
        (TIER1_DIR / "about_my_business.md").write_text(payload.about_my_business, encoding="utf-8")
    if payload.about_my_voice is not None:
        (TIER1_DIR / "about_my_voice.md").write_text(payload.about_my_voice, encoding="utf-8")
    if payload.about_my_offers is not None:
        (TIER1_DIR / "about_my_offers.md").write_text(payload.about_my_offers, encoding="utf-8")
    return {"ok": True, "message": "Tier 1 Universal Context updated successfully"}


@router.post("/tier1/interview")
def interview_generate_tier1(payload: InterviewAnswerRequest) -> dict[str, Any]:
    """Auto-generate structured Tier 1 context files from user interview answers."""
    # Compute the first line outside the f-string: Python 3.10/3.11 do not
    # allow a backslash escape sequence (e.g. '\n') inside an f-string
    # expression part (only 3.12+ supports that) — this must stay
    # compatible with the project's documented Python 3.10+ requirement.
    name_and_role_first_line = payload.name_and_role.split('\n')[0] if '\n' in payload.name_and_role else payload.name_and_role
    about_me = f"""# About Me
- **Name / Role:** {name_and_role_first_line}
- **Background & Mission:**
{payload.name_and_role}
"""
    about_business = f"""# About My Business
- **Core Business & ICP:**
{payload.business_and_icp}
"""
    about_voice = f"""# About My Voice & Tone
- **Writing Style, Words to Use & Words to Avoid:**
{payload.voice_and_words}
- **Formatting Guidelines:** Maintain high clarity, bulleted action items, and bold keywords.
"""
    about_offers = f"""# About My Offers & Pricing
- **Core Offers & Pricing Structure:**
{payload.offers_and_pricing}
"""
    (TIER1_DIR / "about_me.md").write_text(about_me, encoding="utf-8")
    (TIER1_DIR / "about_my_business.md").write_text(about_business, encoding="utf-8")
    (TIER1_DIR / "about_my_voice.md").write_text(about_voice, encoding="utf-8")
    (TIER1_DIR / "about_my_offers.md").write_text(about_offers, encoding="utf-8")
    return {
        "ok": True,
        "message": "Tier 1 Universal Context generated and saved from interview answers",
        "tier1": {
            "about_me": about_me,
            "about_my_business": about_business,
            "about_my_voice": about_voice,
            "about_my_offers": about_offers,
        }
    }


def _get_project_meta(project_id: str) -> dict[str, Any]:
    """Retrieve metadata for a specific Tier 2 project folder."""
    pdir = project_dir(project_id)
    if pdir is None:
        return {"project_id": project_id, "name": project_id, "audience": "General audience"}
    meta_path = pdir / "meta.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"project_id": project_id, "name": project_id.replace("_", " ").title(), "audience": "General audience"}


@router.get("/projects")
def list_projects() -> dict[str, Any]:
    """Retrieve all Tier 2 Project Hierarchies and their metadata."""
    projects = []
    if PROJECTS_DIR.exists():
        for p in sorted(PROJECTS_DIR.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                projects.append(_get_project_meta(p.name))
    return {"ok": True, "count": len(projects), "projects": projects}


@router.post("/projects/create")
def create_project(payload: ProjectCreateRequest) -> dict[str, Any]:
    """Create a new Tier 2 Project folder with standardized IVREN structure."""
    pid = normalize_project_id(payload.project_id)
    if not pid:
        raise HTTPException(status_code=400, detail="project_id cannot be empty")
    pdir = project_dir(pid)
    if pdir is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid project_id '{payload.project_id}': use lowercase letters, "
                f"digits and underscores only."
            ),
        )
    # Re-creating an existing project silently overwrote meta.json — the name,
    # audience and created_at were replaced with no warning while the IVREN
    # content stayed, leaving a project whose metadata described something
    # else. Report the conflict instead.
    if pdir.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Project '{pid}' already exists. Use /projects/{pid}/save to update it.",
        )
    pdir.mkdir(parents=True, exist_ok=True)

    meta = {
        "project_id": pid,
        "name": payload.name,
        "audience": payload.audience,
        "description": payload.description,
        "created_at": time.time(),
    }
    (pdir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    date_str = time.strftime("%Y-%m-%d")
    # Create the 5 IVREN subfolders
    for sub in ["instructions", "voice", "references", "examples", "notes"]:
        subdir = pdir / sub
        subdir.mkdir(exist_ok=True)
        file_path = subdir / f"{sub}.md"
        if not file_path.exists():
            tmpl = DEFAULT_IVREN.get(sub, "").format(name=payload.name, audience=payload.audience, date=date_str)
            file_path.write_text(tmpl, encoding="utf-8")

    return {"ok": True, "project": meta}


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    """Retrieve the content of all 5 IVREN sections for a specific project hierarchy."""
    pdir = _require_project(project_id)
    meta = _get_project_meta(project_id)
    return {
        "ok": True,
        "meta": meta,
        "ivren": {
            "instructions": (pdir / "instructions" / "instructions.md").read_text(encoding="utf-8") if (pdir / "instructions" / "instructions.md").exists() else "",
            "voice": (pdir / "voice" / "voice.md").read_text(encoding="utf-8") if (pdir / "voice" / "voice.md").exists() else "",
            "references": (pdir / "references" / "references.md").read_text(encoding="utf-8") if (pdir / "references" / "references.md").exists() else "",
            "examples": (pdir / "examples" / "examples.md").read_text(encoding="utf-8") if (pdir / "examples" / "examples.md").exists() else "",
            "notes": (pdir / "notes" / "notes.md").read_text(encoding="utf-8") if (pdir / "notes" / "notes.md").exists() else "",
        }
    }


@router.post("/projects/{project_id}/save")
def save_project(project_id: str, payload: ProjectSaveRequest) -> dict[str, Any]:
    """Save or update any of the 5 IVREN sections for a specific project."""
    pdir = _require_project(project_id)

    if payload.instructions is not None:
        (pdir / "instructions").mkdir(exist_ok=True)
        (pdir / "instructions" / "instructions.md").write_text(payload.instructions, encoding="utf-8")
    if payload.voice is not None:
        (pdir / "voice").mkdir(exist_ok=True)
        (pdir / "voice" / "voice.md").write_text(payload.voice, encoding="utf-8")
    if payload.references is not None:
        (pdir / "references").mkdir(exist_ok=True)
        (pdir / "references" / "references.md").write_text(payload.references, encoding="utf-8")
    if payload.examples is not None:
        (pdir / "examples").mkdir(exist_ok=True)
        (pdir / "examples" / "examples.md").write_text(payload.examples, encoding="utf-8")
    if payload.notes is not None:
        (pdir / "notes").mkdir(exist_ok=True)
        (pdir / "notes" / "notes.md").write_text(payload.notes, encoding="utf-8")

    return {"ok": True, "message": f"Project '{project_id}' IVREN hierarchy updated successfully"}


@router.post("/projects/{project_id}/notes/append")
def append_project_note(project_id: str, payload: NoteAppendRequest) -> dict[str, Any]:
    """Append a new feedback or metric note to a project's notes.md file."""
    pdir = _require_project(project_id)
    notes_file = pdir / "notes" / "notes.md"
    (pdir / "notes").mkdir(exist_ok=True)
    existing = notes_file.read_text(encoding="utf-8") if notes_file.exists() else "# Feedback Loop & Compounding Notes\n"
    date_str = time.strftime("%Y-%m-%d %H:%M")
    new_entry = f"\n- **[{date_str}] ({payload.author}):** {payload.note.strip()}"
    notes_file.write_text(existing.rstrip() + new_entry + "\n", encoding="utf-8")
    return {"ok": True, "message": "Note appended to project hierarchy", "notes_content": notes_file.read_text(encoding="utf-8")}


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, Any]:
    """Delete a Tier 2 project hierarchy and all five IVREN files.

    The lifecycle was create-and-save only: a project made by mistake, or one
    no longer relevant, could never be removed through the API. DELETE returned
    405 and the folder stayed in every /status and /projects listing forever.
    """
    pdir = _require_project(project_id)
    import shutil

    shutil.rmtree(pdir)
    return {"ok": True, "deleted": project_id}


@router.post("/tier1/reset")
def reset_tier1() -> dict[str, Any]:
    """Restore the four Tier 1 files to blank templates.

    Needed because the originals shipped with another person's details baked
    in: an existing install has those on disk already, and nothing short of
    manually deleting four files would clear them.
    """
    for key, content in DEFAULT_TIER1.items():
        (TIER1_DIR / f"{key}.md").write_text(content, encoding="utf-8")
    return {"ok": True, "message": "Tier 1 reset to blank templates", "reset": sorted(DEFAULT_TIER1)}


@router.get("/compiled-context")
def get_compiled_context(project_id:str | None = Query(None, description="Optional project ID to merge with Tier 1")) -> dict[str, Any]:
    """Generate the full, compiled Information Hierarchy context block ready for system prompt injection."""
    _ensure_tier1_init()
    # Only inject files the user has actually filled in. An unedited template
    # is a page of "_(your name)_" prompts; injecting it teaches the model
    # nothing and actively wastes context, and injecting the OLD defaults
    # taught it a different person's business as fact.
    filled, unfilled = [], []
    for key in ("about_me", "about_my_business", "about_my_voice", "about_my_offers"):
        text = (TIER1_DIR / f"{key}.md").read_text(encoding="utf-8")
        (unfilled if _is_placeholder(text) else filled).append((key, text))
    tier1_text = "\n\n".join(t for _, t in filled)

    project_text = ""
    if project_id:
        # This text is concatenated into the LLM system prompt by chat.py, so an
        # unvalidated id here is an arbitrary-file-read that feeds the model.
        pdir = project_dir(project_id)
        if pdir is None:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid project_id '{project_id}'",
            )
        if pdir.is_dir():
            for sub in ["instructions", "voice", "references", "examples", "notes"]:
                f = pdir / sub / f"{sub}.md"
                if f.exists():
                    project_text += f"\n\n--- TIER 2 PROJECT DELTA ({sub.upper()}) ---\n" + f.read_text(encoding="utf-8")

    if filled:
        compiled = f"""<information-hierarchy>
=== TIER 1: UNIVERSAL BUSINESS CONTEXT ===
{tier1_text.strip()}
"""
    else:
        # Say so explicitly rather than emitting an empty section: a model given
        # a blank context block will often invent details to fill the gap.
        compiled = """<information-hierarchy>
=== TIER 1: UNIVERSAL BUSINESS CONTEXT ===
The user has not set up their profile yet. Do not invent details about them,
their business, their voice, or their pricing. If such a detail is needed, ask.
"""
    if project_text:
        compiled += f"\n=== TIER 2: PROJECT-SPECIFIC DELTAS & IVREN ==={project_text}"
    compiled += "\n</information-hierarchy>"

    # MODULE MERGE: the "AI Guidelines" (Steering Files) tab now lives inside
    # this same pane, and its rules are ALSO injected into every AI call
    # (see backend/routers/chat.py's chat_stream()). The "Preview Injection"
    # / live split-preview UI in this pane claims to show "the exact context
    # injected into every Agentic OS chat" — before this fix that was only
    # half true, since it never included the Guidelines block. Append it here
    # so both preview surfaces (which just call this one endpoint) show the
    # complete, honest picture without needing separate frontend fetches.
    try:
        from .steering import compile_steering_context

        steering_text = compile_steering_context(max_chars=4000)
        if steering_text:
            compiled += f"\n\n=== AI GUIDELINES: STEERING RULES ===\n{steering_text.strip()}"
    except Exception:
        pass

    return {
        "ok": True,
        "project_id": project_id or "universal_only",
        "compiled_context": compiled,
        "char_count": len(compiled),
        "estimated_tokens": len(compiled) // 4,
        # Surfaced so the preview UI can show what is missing instead of
        # implying the injected block is complete.
        "tier1_filled": [k for k, _ in filled],
        "tier1_unfilled": [k for k, _ in unfilled],
    }
