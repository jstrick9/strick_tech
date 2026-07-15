"""
Agentic OS — Documentation Center
Full in-app docs: quick-starts, feature reference, FAQ, video links, search.

Content is stored as structured JSON so the frontend can render it beautifully.
Supports: full-text search, contextual help (docs for current pane), categories,
          feedback rating (helpful / not helpful tracked in memory).
"""
from __future__ import annotations
import json, re
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/docs", tags=["docs"])

# ── In-memory feedback store (lightweight — resets on restart, no DB needed) ──
_feedback: list[dict] = []   # [{doc_id, doc_type, helpful, ts}]

# ── Documentation content ──────────────────────────────────────────────────────
QUICK_STARTS = [
    {
        "id":    "qs_chat",
        "title": "Chat with AI in 60 seconds",
        "icon":  "💬",
        "time":  "1 min",
        "level": "beginner",
        "steps": [
            {"step": 1, "title": "Open Chat",       "desc": "Click 'Chat' in the left sidebar. It's the first item.",                                                                           "tip": "Keyboard shortcut: click the logo at top-left"},
            {"step": 2, "title": "Add your API key","desc": "Go to Settings → API Keys and paste your OpenRouter API key. It's free to get one at openrouter.ai",                               "tip": "The key is stored encrypted on your machine — never sent anywhere else"},
            {"step": 3, "title": "Pick a model",    "desc": "Click the model badge (top of chat) and choose from 10+ free and paid models",                                                      "tip": "Start with 'Gemini Flash' — it's free and fast"},
            {"step": 4, "title": "Start chatting!", "desc": "Type anything and press Enter. Your AI is ready.",                                                                                   "tip": "Try: 'Explain what FastAPI is in simple terms'"},
        ],
        "video_url": "",
        "related": ["qs_agents", "qs_workflow"],
    },
    {
        "id":    "qs_agents",
        "title": "Create your first AI agent",
        "icon":  "🤖",
        "time":  "3 min",
        "level": "beginner",
        "steps": [
            {"step": 1, "title": "Go to Agents",           "desc": "In the sidebar, find 'Agents' under your active agent pill at the top of chat. Click '+ New Agent'.",  "tip": "Or press ⌘/Ctrl + click on the avatar"},
            {"step": 2, "title": "Name your agent",        "desc": "Give it a name that reflects its purpose: 'Research Assistant', 'Python Helper', 'Writing Coach'",     "tip": "You can have unlimited agents with different specialties"},
            {"step": 3, "title": "Write a system prompt",  "desc": "Tell the agent its role: 'You are a Python expert. Always write clean, documented code with type hints.'", "tip": "Be specific — the more focused the prompt, the better the results"},
            {"step": 4, "title": "Pick a model and color", "desc": "Choose which AI model powers this agent, and give it a color so you can spot it quickly",               "tip": "Different agents can use different models — use free models for simple tasks"},
            {"step": 5, "title": "Save and chat!",         "desc": "Click Save, then select your new agent from the agent picker at the top of the chat pane",             "tip": "Switch agents mid-conversation anytime"},
        ],
        "video_url": "",
        "related": ["qs_chat", "qs_workflow"],
    },
    {
        "id":    "qs_workflow",
        "title": "Build your first workflow",
        "icon":  "🗺️",
        "time":  "5 min",
        "level": "intermediate",
        "steps": [
            {"step": 1, "title": "Open Workflow Builder",    "desc": "Click '🗺️ Workflows' in the sidebar. You'll see 3 starter workflows already there.",                          "tip": "Start with 'Chat → Research → Summarize' as a template"},
            {"step": 2, "title": "Add a node",               "desc": "Drag a node type from the left palette onto the canvas. Start with a Trigger node.",                            "tip": "Trigger → Agent → Output is the simplest workflow"},
            {"step": 3, "title": "Connect nodes",            "desc": "Drag from the right port (●) of one node to the left port of another to connect them",                          "tip": "Hover over nodes to see connection points"},
            {"step": 4, "title": "Configure the agent node", "desc": "Click an Agent node → set which agent runs it and what prompt template to use. Use {{input}} for the workflow input.", "tip": "You can chain multiple agents — output of one feeds the next"},
            {"step": 5, "title": "Run it!",                  "desc": "Click '▶ Run' in the toolbar, type your input, and watch each node execute in real time",                        "tip": "Visit 'Replay' pane to scrub through the execution step-by-step afterward"},
        ],
        "video_url": "",
        "related": ["qs_agents", "qs_specs"],
    },
    {
        "id":    "qs_specs",
        "title": "Spec-driven development (plan before code)",
        "icon":  "📋",
        "time":  "10 min",
        "level": "intermediate",
        "steps": [
            {"step": 1, "title": "Open Spec Builder",         "desc": "Click '📋 Spec Builder' in the sidebar",                                                                                  "tip": "Like Kiro (AWS) — plan before you code"},
            {"step": 2, "title": "Create a new spec",         "desc": "Click '+ New Spec', give it a name like 'User Authentication System'",                                                    "tip": "Be descriptive — the AI uses your description to generate requirements"},
            {"step": 3, "title": "Describe what you want",    "desc": "Write a detailed description: what it does, who uses it, key behaviors",                                                  "tip": "More detail = better requirements. Include 'must haves' and 'nice to haves'"},
            {"step": 4, "title": "Run Full Pipeline",         "desc": "Click '🚀 Run Full Pipeline' — this generates Requirements → Design → Tasks automatically",                               "tip": "Watch as the AI creates a proper requirements doc, architecture design, and task list"},
            {"step": 5, "title": "Review and execute",        "desc": "Switch to the Tasks tab to see the implementation plan. Click 'Execute' to have agents implement each task.",            "tip": "Tasks run in parallel waves — independent tasks execute simultaneously"},
        ],
        "video_url": "",
        "related": ["qs_workflow", "qs_chat"],
    },
    {
        "id":    "qs_rag",
        "title": "Build a document Q&A system",
        "icon":  "📚",
        "time":  "5 min",
        "level": "intermediate",
        "steps": [
            {"step": 1, "title": "Open RAG Builder",  "desc": "Click '📚 RAG' in the sidebar (Enterprise feature)",                                "tip": "RAG = Retrieval-Augmented Generation — AI answers from your documents"},
            {"step": 2, "title": "Create a pipeline", "desc": "Click '+ New Pipeline', name it 'My Knowledge Base'",                              "tip": "You can have multiple pipelines for different document sets"},
            {"step": 3, "title": "Add documents",     "desc": "Paste text content (from docs, manuals, notes) and click 'Add Document'",           "tip": "The AI automatically chunks and indexes the content"},
            {"step": 4, "title": "Ask questions",     "desc": "Type a question and press Ask — the AI searches your documents and answers with citations", "tip": "Answers reference which chunk they came from — no hallucination"},
        ],
        "video_url": "",
        "related": ["qs_chat", "qs_agents"],
    },
    {
        "id":    "qs_eval",
        "title": "Evaluate your AI agent quality",
        "icon":  "🧮",
        "time":  "5 min",
        "level": "advanced",
        "steps": [
            {"step": 1, "title": "Open Evals",        "desc": "Click '🧮 Evals' in the sidebar (Enterprise feature)",                                        "tip": "Like DeepEval — score every agent response automatically"},
            {"step": 2, "title": "Run a quick eval",  "desc": "Click '▶ Quick Eval', enter the prompt you sent and the agent's response",                    "tip": "The AI-judge scores faithfulness, hallucination, task completion, safety"},
            {"step": 3, "title": "Review the score",  "desc": "You'll get a 0-100 score with breakdown by metric and any detected issues",                   "tip": "Below 70 = fail. Aim for 85+ in production"},
            {"step": 4, "title": "Run Red Team tests","desc": "Click '🔴 Red Team' to test if your agent is vulnerable to prompt injection, jailbreaks, PII extraction", "tip": "8 OWASP LLM Top 10 attacks — know your agent's security posture"},
        ],
        "video_url": "",
        "related": ["qs_agents", "qs_specs"],
    },
]

FEATURE_DOCS: dict[str, dict] = {
    "chat":     {"title":"Chat",           "icon":"💬","tier":"free",       "summary":"Chat with any AI model. Switch agents mid-conversation. Stream responses in real time.",                                            "details":"The Chat pane is the heart of Agentic OS. You can talk to any of your agents, switch models on the fly, and the conversation is saved automatically. Use @mentions to pull in files from your project.",                                                                   "tips":["Press ⌘↑ to access chat history","Click the model badge to switch models without losing context","Use /command shortcuts: /clear, /save, /export"],"video_url":""},
    "workflow": {"title":"Workflow Builder","icon":"🗺️","tier":"pro",       "summary":"Build n8n-style visual workflows that chain multiple AI agents together.",                                                           "details":"The Workflow Builder lets you create automated pipelines by connecting nodes on a canvas. Drag nodes from the palette, connect them with edges, and run the workflow with a single click.",                                                                              "tips":["⌘S saves the workflow","Use the ⊡ button to fit the canvas to screen","Workflow history in the Replay pane"],"video_url":""},
    "specs":    {"title":"Spec Builder",   "icon":"📋","tier":"pro",       "summary":"Like AWS Kiro — generate Requirements → Design → Tasks → Code from a plain English description.",                                    "details":"Spec-driven development prevents 'vibe coding' drift. You describe a feature, and the AI generates: a Requirements doc (EARS notation), an Architecture Design, and a dependency-mapped Task list.",                                                                     "tips":["The more detail in your description, the better the requirements","Wave execution runs independent tasks simultaneously"],"video_url":""},
    "evals":    {"title":"Agent Evals",    "icon":"🧮","tier":"enterprise","summary":"DeepEval-level scoring: faithfulness, hallucination, task completion, safety, and red-team attacks.",                               "details":"The Evals engine runs automated quality scores on every agent response. Use it to detect regressions, benchmark model changes, and red-team your agents with 8 OWASP LLM Top 10 attacks.",                                                                               "tips":["Run Quick Eval after every major prompt change","Red Team before going to production","Compare scores across agents in the Leaderboard"],"video_url":""},
    "bugbot":   {"title":"BugBot",         "icon":"🐛","tier":"pro",       "summary":"AI code reviewer for diffs, files, and GitHub PRs. Like Cursor BugBot.",                                                             "details":"BugBot reviews code for bugs, security issues, performance problems, and documentation gaps. Paste a diff, review your git changes, upload a file, or connect a GitHub PR URL.",                                                                                        "tips":["Review before every commit","GitHub PR review automatically posts a comment","Feedback on reviews helps BugBot learn your standards"],"video_url":""},
    "rag":      {"title":"RAG Pipeline",   "icon":"📚","tier":"enterprise","summary":"Build document Q&A systems with vector search and citations. No hallucination.",                                                      "details":"The RAG Pipeline Builder lets you create document retrieval systems. Ingest any text, PDFs, or code; the system chunks, embeds, and indexes it. Ask questions and get cited answers.",                                                                                   "tips":["Use chunk size 512 for most documents","Add multiple pipelines for different knowledge bases","Combine with steering files for project-aware AI"],"video_url":""},
    "steering": {"title":"Steering Files", "icon":"🧭","tier":"pro",       "summary":"Persistent project context injected into every AI prompt. Like Kiro steering + Cursor .cursorrules.",                              "details":"Steering files encode your tech stack, coding conventions, and architectural decisions so the AI always follows your standards without you repeating them. Enable Auto-Learn to extract patterns automatically.",                                                           "tips":["Start with the 4 pre-loaded files: Stack, Style, Architecture, Context","Auto-Learn analyzes your last 100 chats to extract your patterns","Enable/disable individual files per project"],"video_url":""},
    "arena":    {"title":"Arena Mode",     "icon":"⚔️","tier":"pro",       "summary":"A/B test two AI models side-by-side. Vote on winners. ELO ratings build a personal leaderboard.",                                  "details":"Arena Mode sends the same prompt to two models simultaneously and streams both responses. Vote on which is better — ELO ratings update automatically. Over time you build a personal leaderboard.",                                                                       "tips":["Budget preset uses free models — zero cost","Quality preset uses frontier models","Let Auto-Judge score battles automatically to build the leaderboard faster"],"video_url":""},
    "memory":   {"title":"Memory / Galaxy","icon":"🌌","tier":"pro",       "summary":"Persistent semantic memory across all conversations. The AI remembers key facts automatically.",                                     "details":"The Memory system stores important facts, decisions, and patterns from your conversations. The AI automatically retrieves relevant memories when answering questions, giving it long-term context.",                                                                       "tips":["Add memories manually from any chat message","Search your memory bank with semantic search","Export memories as markdown for backup"],"video_url":""},
    "websearch":{"title":"Web Search",     "icon":"🔎","tier":"pro",       "summary":"Ground AI answers with live web citations. Like Perplexity — free DuckDuckGo search.",                                             "details":"Web Search Grounding searches the web first, then has the AI answer with citations. No API key needed — powered by DuckDuckGo. Use Deep Research mode for comprehensive multi-query research reports.",                                                                   "tips":["Use Grounded AI for factual questions","Deep Research generates 4+ queries and synthesizes a report","Search history is saved for quick replay"],"video_url":""},
}

FAQ = [
    {"q":"Do I need an OpenRouter API key?",          "a":"For chat and agent features, yes. Get a free key at openrouter.ai — many models are free with no credit card required. The key is stored encrypted on your machine.", "tags":["setup","api"]},
    {"q":"Is my data private?",                       "a":"Yes. Agentic OS is local-first. Your code, conversations, and documents stay on your machine. Only the text you send to AI models goes to the model provider — never to us.", "tags":["privacy","security"]},
    {"q":"What's the difference between Simple Mode and Power Mode?", "a":"Simple Mode shows only the 6 core features in a clean layout — perfect for getting started. Power Mode unlocks the full sidebar with all 50+ panes. Switch anytime in Settings → Appearance.", "tags":["ui","modes"]},
    {"q":"How do I add my own AI models?",            "a":"Go to Settings → API Keys. Add your OpenRouter key for 100+ models, or your Ollama URL for local models. You can also add direct Anthropic, OpenAI, or Google API keys.", "tags":["models","setup"]},
    {"q":"Can I use this offline?",                   "a":"Basic features work offline (docs, kanban, saved conversations). AI features require internet to reach model providers. Ollama gives you fully offline local AI if installed.", "tags":["offline","privacy"]},
    {"q":"What happens when my trial expires?",       "a":"After 14 days, advanced features are locked behind Pro/Enterprise. Your data is safe — conversations, agents, and projects stay. You just can't access Pro features until upgrading.", "tags":["trial","pricing"]},
    {"q":"How do I back up my data?",                 "a":"Go to Settings → click 'Backup Database'. This creates a timestamped .db file in memory/. You can also export your workspace as a ZIP from the Workspaces pane.", "tags":["backup","data"]},
    {"q":"Can multiple people use this?",             "a":"Single-user for Free and Pro. Enterprise adds multi-user admin with role-based access, team workspaces, and shared steering files.", "tags":["team","enterprise"]},
    {"q":"How do I reset my 14-day trial?",           "a":"For development and testing, you can reset via Settings → License → 'Reset Trial (Dev)'. In production this option is removed.", "tags":["trial","dev"]},
    {"q":"What's a Steering File?",                   "a":"Steering files are like .cursorrules or Kiro's .kiro/steering/ — markdown files that get injected into every AI prompt so the AI always knows your tech stack, coding style, and project context. Go to 🧭 Steering to manage them.", "tags":["steering","agents"]},
    {"q":"How does the Workflow Builder work?",       "a":"Drag nodes from the palette onto the canvas, connect them with edges, and run. Each node is a step: Trigger → Agent → Condition → Output. Agents chain their outputs as inputs to the next node.", "tags":["workflow","agents"]},
    {"q":"What is Spec-Driven Development?",          "a":"Instead of jumping straight to code, Spec Builder generates Requirements, Design, and Tasks from your description first. Like AWS Kiro — forces planning before coding, prevents drift.", "tags":["specs","workflow"]},
]

KEYBOARD_SHORTCUTS = [
    {"key":"⌘K",       "desc":"Open command palette / global search"},
    {"key":"⌘P",       "desc":"Code search"},
    {"key":"⌘L",       "desc":"Prompt library"},
    {"key":"⌘U",       "desc":"Share / invite to collaboration"},
    {"key":"⌘\\",      "desc":"Toggle sidebar"},
    {"key":"⌘,",       "desc":"Open settings"},
    {"key":"⌘/",       "desc":"Open documentation center"},
    {"key":"⌘⇧W",      "desc":"Open Workflow Builder"},
    {"key":"⌘⇧P",      "desc":"Open Profiler"},
    {"key":"⌘⇧B",      "desc":"Open BugBot"},
    {"key":"⌘⇧E",      "desc":"Open Evals"},
    {"key":"⌘⇧F",      "desc":"Open Model Fusion"},
    {"key":"⌘⇧M",      "desc":"Open Marketplace"},
    {"key":"⌘⇧R",      "desc":"Open Replay"},
    {"key":"Ctrl+Shift+V", "desc":"Toggle Voice Coding"},
    {"key":"⌘T",       "desc":"New tab (Multi-tab preview)"},
    {"key":"⌘W",       "desc":"Close current tab"},
    {"key":"⌘⇧I",      "desc":"Open user profile panel"},
]


# ── REST endpoints ──────────────────────────────────────────────────────────────

@router.get("/quick-starts")
def get_quick_starts(level: str = ""):
    qs = QUICK_STARTS
    if level:
        qs = [q for q in qs if q.get("level", "") == level]
    return {"quick_starts": qs, "count": len(qs)}


@router.get("/quick-starts/{qs_id}")
def get_quick_start(qs_id: str):
    qs = next((q for q in QUICK_STARTS if q["id"] == qs_id), None)
    if not qs:
        raise HTTPException(status_code=404, detail=f"Quick-start '{qs_id}' not found")
    return qs


@router.get("/features")
def list_feature_docs(tier: str = ""):
    docs = [{"id": k, **v} for k, v in FEATURE_DOCS.items()]
    if tier:
        docs = [d for d in docs if d.get("tier", "") == tier]
    return {"features": docs, "count": len(docs)}


@router.get("/features/{pane_id}")
def get_feature_doc(pane_id: str):
    doc = FEATURE_DOCS.get(pane_id)
    if not doc:
        # Return a stub rather than 404 so contextual help always works
        return {
            "id":      pane_id,
            "title":   pane_id.replace("-", " ").title(),
            "icon":    "🔧",
            "tier":    "pro",
            "summary": f"The {pane_id} feature. Documentation coming soon.",
            "details": "This feature is part of the Agentic OS platform. Check back for detailed documentation.",
            "tips":    ["Explore the feature by clicking around", "Hover over elements for tooltips"],
            "video_url": "",
        }
    return {"id": pane_id, **doc}


@router.get("/faq")
def get_faq(q: str = ""):
    faq = FAQ
    if q:
        qlow = q.lower()
        faq = [f for f in FAQ if qlow in f["q"].lower() or qlow in f["a"].lower()
               or any(qlow in t for t in f.get("tags", []))]
    return {"faq": faq, "count": len(faq)}


@router.get("/shortcuts")
def get_shortcuts():
    return {"shortcuts": KEYBOARD_SHORTCUTS, "count": len(KEYBOARD_SHORTCUTS)}


@router.get("/search")
def search_docs(q: str = "", limit: int = 20):
    """Full-text search across all docs content."""
    limit = max(1, min(int(limit), 50))   # clamp to sane range
    if not q:
        return {"results": [], "query": q, "count": 0}
    qlow    = q.lower()
    results: list[dict] = []

    # Search quick-starts
    for qs in QUICK_STARTS:
        score = 0
        if qlow in qs["title"].lower(): score += 10
        for step in qs.get("steps", []):
            if qlow in step.get("title", "").lower(): score += 5
            if qlow in step.get("desc",  "").lower(): score += 2
        if score > 0:
            results.append({"type": "quickstart", "score": score,
                            "title": qs["title"], "icon": qs["icon"],
                            "id": qs["id"], "level": qs["level"]})

    # Search feature docs
    for pane_id, doc in FEATURE_DOCS.items():
        score = 0
        if qlow in doc.get("title",   "").lower(): score += 10
        if qlow in doc.get("summary", "").lower(): score += 6
        if qlow in doc.get("details", "").lower(): score += 3
        for tip in doc.get("tips", []):
            if qlow in tip.lower(): score += 2
        if score > 0:
            results.append({"type": "feature", "score": score,
                            "title": doc["title"], "icon": doc.get("icon", "🔧"),
                            "id": pane_id, "tier": doc.get("tier", "pro")})

    # Search FAQ
    for i, f in enumerate(FAQ):
        score = 0
        if qlow in f["q"].lower(): score += 10
        if qlow in f["a"].lower(): score += 4
        if any(qlow in t for t in f.get("tags", [])): score += 3
        if score > 0:
            results.append({"type": "faq", "score": score, "title": f["q"],
                            "id": str(i), "answer_preview": f["a"][:120]})

    # Search shortcuts
    for s in KEYBOARD_SHORTCUTS:
        if qlow in s["desc"].lower():
            results.append({"type": "shortcut", "score": 5,
                            "title": s["desc"], "id": s["key"], "shortcut": s["key"]})

    results.sort(key=lambda x: x["score"], reverse=True)
    trimmed = results[:limit]
    return {"results": trimmed, "count": len(results), "shown": len(trimmed), "query": q}


@router.get("/contextual/{pane_id}")
def contextual_help(pane_id: str):
    """Get contextual help content for the currently active pane."""
    try:
        doc = FEATURE_DOCS.get(pane_id)
        if doc:
            doc = {"id": pane_id, **doc}

        related_qs = [
            qs for qs in QUICK_STARTS
            if pane_id in qs.get("related", [])
            or any(pane_id in s.get("desc", "") for s in qs.get("steps", []))
        ]

        faq_matches = [
            f for f in FAQ
            if pane_id in " ".join(f.get("tags", [])) or pane_id in f["q"].lower()
        ][:3]

        shortcut_matches = [s for s in KEYBOARD_SHORTCUTS if pane_id in s["desc"].lower()]

        return {
            "pane":         pane_id,
            "doc":          doc,
            "quick_starts": related_qs[:2],
            "faq":          faq_matches,
            "shortcuts":    shortcut_matches,
        }
    except Exception as exc:
        return {"pane": pane_id, "doc": None, "quick_starts": [], "faq": [], "shortcuts": [], "error": str(exc)}


@router.post("/feedback")
async def submit_feedback(req: Request):
    """Rate a doc as helpful or not helpful."""
    try:
        try:
            body = await req.json()
        except Exception:
            body = {}
    except Exception:
        return {"ok": False, "error": "Invalid JSON body"}

    doc_id   = (body.get("doc_id")   or "").strip()[:100]
    doc_type = (body.get("doc_type") or "feature").strip()[:20]
    helpful  = bool(body.get("helpful", True))

    if not doc_id:
        return {"ok": False, "error": "doc_id required"}
    if doc_type not in {"feature", "quickstart", "faq", "shortcut"}:
        doc_type = "feature"

    import time
    _feedback.append({"doc_id": doc_id, "doc_type": doc_type, "helpful": helpful, "ts": int(time.time())})

    # Keep last 1000 feedback items in memory
    if len(_feedback) > 1000:
        _feedback.pop(0)

    return {"ok": True, "total_feedback": len(_feedback)}


@router.get("/feedback/summary")
def feedback_summary():
    """Return aggregated feedback counts."""
    from collections import Counter
    counts: dict[str, dict] = {}
    for item in _feedback:
        key = f"{item['doc_type']}:{item['doc_id']}"
        if key not in counts:
            counts[key] = {"doc_id": item["doc_id"], "doc_type": item["doc_type"],
                           "helpful": 0, "not_helpful": 0}
        if item["helpful"]:
            counts[key]["helpful"] += 1
        else:
            counts[key]["not_helpful"] += 1
    return {"feedback": list(counts.values()), "total": len(_feedback)}
