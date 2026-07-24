"""
Agentic OS — Information Hierarchy Router (`/api/hierarchy`)
Implements the compounding 2-Tier Information Hierarchy created by Joshua Strickland and Strick Tech.
Tier 1: 4 core files (about_me.md, about_my_business.md, about_my_voice.md, about_my_offers.md)
Tier 2: Project folders with 5 IVREN subfolders (instructions, voice, references, examples, notes)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, Union, Any, Dict, List, Tuple, Set, Callable, AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/hierarchy", tags=["hierarchy"])

from backend.config import get_data_dir
ROOT = get_data_dir()
HIERARCHY_DIR = ROOT / "memory" / "hierarchy"
TIER1_DIR = HIERARCHY_DIR / "tier1"
PROJECTS_DIR = HIERARCHY_DIR / "projects"

# Ensure directories exist
TIER1_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

# Default Tier 1 templates
DEFAULT_TIER1 = {
    "about_me": """# About Me
- **Name:** Joshua Strickland
- **Role:** Founder & Creator of Agentic OS
- **Company:** Strick Tech
- **One-Line Intro:** I build local-first AI operating systems and scalable autonomous workflows.
- **Background:** Software creator and product strategist focused on multi-agent collaboration and high-leverage tools for individuals and organizations.
""",
    "about_my_business": """# About My Business
- **Company Name:** Strick Tech
- **What We Do:** Create Agentic OS Platform — software for individuals and organizations to build, run, and scale autonomous AI agents.
- **Target Audience / ICP:** Individuals, organizations, developers, and enterprise leaders seeking full local control with compounding AI memory.
- **Unique Value Proposition:** Swarm fan-out with judge synthesis, 3D Memory Galaxy, spec-driven development, and compounding information hierarchy.
""",
    "about_my_voice": """# About My Voice & Tone
- **Writing Style:** Clear, crisp, punchy, action-oriented, and deeply informative.
- **Tone:** Professional yet enthusiastic, approachable, authoritative, and direct.
- **Words & Phrases I Love:** High-leverage, compounding, clear-cut, robust, autonomous, systematic, 10/10.
- **Words & Phrases to Avoid:** Delve, tapestry, game-changer, revolutionary, synergy, unpack, endeavor, bespoke.
- **Formatting Rules:** Use bullet points, bold key concepts, keep paragraphs shorter than 4 lines, and always include concrete examples or code.
""",
    "about_my_offers": """# About My Offers & Pricing
- **Core Product:** Agentic OS Platform by Strick Tech
- **Editions / Versions:** Free, Pro, and Enterprise tiers.
  - **Free Version:** Essential local-first multi-agent chat, basic studio builder, SQLite memory, and core 2-tier information hierarchy.
  - **Pro Version:** Advanced swarm orchestration, 12 neural voice TTS agents, autonomous browser automation, full CRDT collaboration, and unlimited project IVREN hierarchies.
  - **Enterprise Version:** Dedicated Governance Control Tower, HITL approval gates, custom MCP tool routing, SLA monitoring, anomaly detection, and priority enterprise support by Strick Tech.
""",
}

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


def _ensure_tier1_init() -> None:
    """Ensure all 4 Tier 1 universal context files exist with default templates if not already present."""
    for key, content in DEFAULT_TIER1.items():
        file_path = TIER1_DIR / f"{key}.md"
        if not file_path.exists():
            file_path.write_text(content, encoding="utf-8")


class Tier1SaveRequest(BaseModel):
    """Pydantic data model for Tier1SaveRequest."""
    about_me:Optional[ str] = None
    about_my_business:Optional[ str] = None
    about_my_voice:Optional[ str] = None
    about_my_offers:Optional[ str] = None


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
    instructions:Optional[ str] = None
    voice:Optional[ str] = None
    references:Optional[ str] = None
    examples:Optional[ str] = None
    notes:Optional[ str] = None


class NoteAppendRequest(BaseModel):
    """Pydantic data model for NoteAppendRequest."""
    note: str
    author: str = "user"


@router.get("/status")
def get_hierarchy_status() -> dict[str, Any]:
    """Retrieve the overall health and file counts of the 2-Tier Information Hierarchy."""
    _ensure_tier1_init()
    tier1_files = {
        "about_me": (TIER1_DIR / "about_me.md").exists(),
        "about_my_business": (TIER1_DIR / "about_my_business.md").exists(),
        "about_my_voice": (TIER1_DIR / "about_my_voice.md").exists(),
        "about_my_offers": (TIER1_DIR / "about_my_offers.md").exists(),
    }
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
        "tier1": tier1_files,
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
    meta_path = PROJECTS_DIR / project_id / "meta.json"
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
    pid = payload.project_id.strip().lower().replace(" ", "_").replace("-", "_")
    if not pid:
        raise HTTPException(status_code=400, detail="project_id cannot be empty")
    pdir = PROJECTS_DIR / pid
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
    pdir = PROJECTS_DIR / project_id
    if not pdir.exists():
        raise HTTPException(status_code=404, detail=f"Project hierarchy '{project_id}' not found")
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
    pdir = PROJECTS_DIR / project_id
    if not pdir.exists():
        raise HTTPException(status_code=404, detail=f"Project hierarchy '{project_id}' not found")

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
    pdir = PROJECTS_DIR / project_id
    if not pdir.exists():
        raise HTTPException(status_code=404, detail=f"Project hierarchy '{project_id}' not found")
    notes_file = pdir / "notes" / "notes.md"
    (pdir / "notes").mkdir(exist_ok=True)
    existing = notes_file.read_text(encoding="utf-8") if notes_file.exists() else "# Feedback Loop & Compounding Notes\n"
    date_str = time.strftime("%Y-%m-%d %H:%M")
    new_entry = f"\n- **[{date_str}] ({payload.author}):** {payload.note.strip()}"
    notes_file.write_text(existing.rstrip() + new_entry + "\n", encoding="utf-8")
    return {"ok": True, "message": "Note appended to project hierarchy", "notes_content": notes_file.read_text(encoding="utf-8")}


@router.get("/compiled-context")
def get_compiled_context(project_id:Optional[ str] = Query(None, description="Optional project ID to merge with Tier 1")) -> dict[str, Any]:
    """Generate the full, compiled Information Hierarchy context block ready for system prompt injection."""
    _ensure_tier1_init()
    tier1_text = (
        (TIER1_DIR / "about_me.md").read_text(encoding="utf-8") + "\n\n" +
        (TIER1_DIR / "about_my_business.md").read_text(encoding="utf-8") + "\n\n" +
        (TIER1_DIR / "about_my_voice.md").read_text(encoding="utf-8") + "\n\n" +
        (TIER1_DIR / "about_my_offers.md").read_text(encoding="utf-8")
    )

    project_text = ""
    if project_id:
        pdir = PROJECTS_DIR / project_id
        if pdir.exists():
            for sub in ["instructions", "voice", "references", "examples", "notes"]:
                f = pdir / sub / f"{sub}.md"
                if f.exists():
                    project_text += f"\n\n--- TIER 2 PROJECT DELTA ({sub.upper()}) ---\n" + f.read_text(encoding="utf-8")

    compiled = f"""<information-hierarchy>
=== TIER 1: UNIVERSAL BUSINESS CONTEXT ===
{tier1_text.strip()}
"""
    if project_text:
        compiled += f"\n=== TIER 2: PROJECT-SPECIFIC DELTAS & IVREN ==={project_text}"
    compiled += "\n</information-hierarchy>"

    return {
        "ok": True,
        "project_id": project_id or "universal_only",
        "compiled_context": compiled,
        "char_count": len(compiled),
        "estimated_tokens": len(compiled) // 4,
    }
