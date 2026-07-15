"""
Agentic OS — Webhook Triggers Router
External events → agent runs automatically.
GitHub push → code review agent
Stripe payment → onboarding email agent
Form submit → analyze and respond agent
Cron schedule → periodic agent tasks
"""
from __future__ import annotations
import asyncio, hashlib, hmac, json, logging, time, uuid
from fastapi import APIRouter, Request, Header
from ..services.memory_db import get_conn, audit_log, memory_add

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
log    = logging.getLogger("agentic.webhooks")

# ── Webhook registry ───────────────────────────────────────────────────────────
def _ensure_table():
    con = get_conn()
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS webhooks (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                description TEXT DEFAULT '',
                secret      TEXT DEFAULT '',
                agent_id    TEXT DEFAULT 'brain',
                prompt_template TEXT DEFAULT 'Process this event: {payload}',
                filters     TEXT DEFAULT '{}',
                enabled     INTEGER DEFAULT 1,
                trigger_count INTEGER DEFAULT 0,
                last_triggered TIMESTAMP,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS webhook_events (
                id          INTEGER PRIMARY KEY,
                webhook_id  TEXT,
                source      TEXT,
                payload     TEXT,
                run_id      TEXT,
                status      TEXT DEFAULT 'received',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()
    finally:
        con.close()

try:
    _ensure_table()
except Exception as _e:
    log.error("webhooks: DB init failed — %s", _e)


# ── Endpoints ──────────────────────────────────────────────────────────────────
@router.get("")
def list_webhooks():
    con = get_conn()
    try:
        rows = con.execute("SELECT * FROM webhooks ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        return []
    finally:
        con.close()


@router.post("")
async def create_webhook(req: Request):
    try:
        body   = await req.json()
    except Exception:
        body   = {}
    name   = (body.get("name") or "Webhook").strip()[:80]
    wid    = str(uuid.uuid4())[:12]
    secret = body.get("secret", uuid.uuid4().hex[:24])
    con = get_conn()
    try:
        con.execute(
            """INSERT INTO webhooks(id,name,description,secret,agent_id,prompt_template,filters)
               VALUES(?,?,?,?,?,?,?)""",
            (wid, name,
             body.get("description","")[:200],
             secret,
             body.get("agent_id","brain"),
             body.get("prompt_template","Process this webhook event: {payload}")[:2000],
             json.dumps(body.get("filters",{})))
        )
        con.commit()
    finally:
        con.close()
    audit_log("webhook_create", f"{wid}: {name}")
    return {
        "ok":         True,
        "id":         wid,
        "name":       name,
        "secret":     secret,
        "endpoint":   f"/api/webhooks/{wid}/trigger",
        "instructions": f"Send POST requests to /api/webhooks/{wid}/trigger with X-Webhook-Secret: {secret}",
    }


@router.patch("/{webhook_id}")
async def update_webhook(webhook_id: str, req: Request):
    try:
        body    = await req.json()
    except Exception:
        body    = {}
    allowed = {"name","description","agent_id","prompt_template","filters","enabled","secret"}
    sets, vals = [], []
    for k in allowed:
        if k in body:
            v = json.dumps(body[k]) if k == "filters" else body[k]
            sets.append(f"{k}=?"); vals.append(v)
    if not sets: return {"ok": False}
    vals.append(webhook_id)
    con = get_conn()
    try:
        cur = con.execute(f"UPDATE webhooks SET {', '.join(sets)} WHERE id=?", vals)
        con.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "Webhook not found"}
    finally:
        con.close()
    return {"ok": True}


@router.delete("/{webhook_id}")
def delete_webhook(webhook_id: str):
    con = get_conn()
    try:
        cur = con.execute("DELETE FROM webhooks WHERE id=?", (webhook_id,))
        con.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "Webhook not found"}
    finally:
        con.close()
    return {"ok": True}


@router.get("/{webhook_id}/events")
def webhook_events(webhook_id: str, limit: int = 20):
    con = get_conn()
    try:
        rows = con.execute(
            "SELECT * FROM webhook_events WHERE webhook_id=? ORDER BY id DESC LIMIT ?",
            (webhook_id, min(limit, 100))
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        con.close()


# ── Trigger endpoint (receives external events) ───────────────────────────────
@router.post("/{webhook_id}/trigger")
async def trigger_webhook(
    webhook_id: str,
    req: Request,
    x_webhook_secret: str = Header(default="", alias="X-Webhook-Secret"),
    x_hub_signature_256: str = Header(default="", alias="X-Hub-Signature-256"),
):
    """
    The public endpoint that external services call.
    Validates secret, then triggers the configured agent.
    """
    con = get_conn()
    try:
        wh  = con.execute("SELECT * FROM webhooks WHERE id=? AND enabled=1", (webhook_id,)).fetchone()
    finally:
        con.close()

    if not wh:
        return {"ok": False, "error": "Webhook not found or disabled"}
    wh = dict(wh)

    # Validate secret
    body_bytes = await req.body()
    secret = wh.get("secret","")

    if secret:
        # Support GitHub-style HMAC-SHA256
        if x_hub_signature_256:
            expected = "sha256=" + hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, x_hub_signature_256):
                return {"ok": False, "error": "Invalid signature"}
        elif x_webhook_secret and x_webhook_secret != secret:
            return {"ok": False, "error": "Invalid secret"}
        elif not x_webhook_secret and not x_hub_signature_256:
            # No auth header at all — still accept if no secret set
            if secret:
                return {"ok": False, "error": "Secret required"}

    # Parse payload
    try:
        payload = json.loads(body_bytes)
    except Exception:
        payload = {"raw": body_bytes.decode("utf-8", errors="ignore")[:2000]}

    # Determine source
    source = "webhook"
    if "repository" in payload and "pusher" in payload:
        source = "github-push"
    elif "type" in payload and payload.get("type","").startswith("customer"):
        source = "stripe"
    elif req.headers.get("user-agent","").lower().startswith("stripe"):
        source = "stripe"

    event_id = int(time.time() * 1000)
    payload_str = json.dumps(payload)[:5000]

    # Build agent prompt
    template = wh.get("prompt_template", "Process this webhook event: {payload}")
    prompt   = template.replace("{payload}", payload_str[:2000])
    prompt   = prompt.replace("{source}", source)
    prompt   = prompt.replace("{event_id}", str(event_id))

    # Fire agent asynchronously
    run_id = str(uuid.uuid4())[:8]
    asyncio.create_task(_run_webhook_agent(wh, prompt, run_id, webhook_id, source, payload_str))

    # Log event
    con = get_conn()
    try:
        con.execute(
            "INSERT INTO webhook_events(webhook_id,source,payload,run_id,status) VALUES(?,?,?,?,?)",
            (webhook_id, source, payload_str, run_id, "processing")
        )
        con.execute(
            "UPDATE webhooks SET trigger_count=trigger_count+1, last_triggered=CURRENT_TIMESTAMP WHERE id=?",
            (webhook_id,)
        )
        con.commit()
    finally:
        con.close()

    return {
        "ok":     True,
        "run_id": run_id,
        "source": source,
        "message": f"Webhook received — agent '{wh['agent_id']}' triggered (run {run_id})",
    }


async def _run_webhook_agent(wh: dict, prompt: str, run_id: str, webhook_id: str, source: str, payload: str):
    """Async background task: run the agent for a webhook event."""
    from ..services import llm, memory_db

    agent_id = wh.get("agent_id", "brain")
    agents   = {a["id"]: a for a in memory_db.agents_list()}
    agent    = agents.get(agent_id, {"name": agent_id, "model": "", "system_prompt": ""})
    system   = agent.get("system_prompt") or f"You are {agent.get('name', agent_id)}, processing an automated webhook event."

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt},
    ]

    try:
        result = await llm.complete(messages, agent_id=agent.get("model") or agent_id, max_tokens=1024, inject_steering=False)
        output = result.get("text", "")
        status = "done" if result.get("ok") else "error"

        # Store result
        memory_add(f"webhook:{source}", f"Webhook {source} → {output[:300]}", f"webhook,{source},{agent_id}")
        audit_log("webhook_run", f"{webhook_id} → {run_id}: {status}")

        # Update event status
        con = get_conn()
        try:
            con.execute("UPDATE webhook_events SET status=? WHERE run_id=?", (status, run_id))
            con.commit()
        finally:
            con.close()

        # Push notification (wrapped — control_tower may not be loaded)
        try:
            from .control_tower import _push_notification
            _push_notification(
                "run_complete",
                f"🔔 Webhook: {source}",
                f"{wh['name']} → {agent_id} completed · {len(output)} chars",
                run_id
            )
        except Exception:
            pass  # notification failure should not affect webhook processing
    except Exception as e:
        log.error("Webhook agent error: %s", e)
        con = get_conn()
        try:
            con.execute("UPDATE webhook_events SET status='error' WHERE run_id=?", (run_id,))
            con.commit()
        finally:
            con.close()


# ── Test trigger ───────────────────────────────────────────────────────────────
@router.post("/{webhook_id}/test")
async def test_webhook(webhook_id: str):
    """Send a test event to a webhook (bypasses secret validation)."""
    con = get_conn()
    try:
        wh = con.execute("SELECT * FROM webhooks WHERE id=? AND enabled=1", (webhook_id,)).fetchone()
    finally:
        con.close()
    if not wh:
        return {"ok": False, "error": "Webhook not found or disabled"}
    wh = dict(wh)
    
    test_payload = {
        "event": "test",
        "source": "agentic-os-test",
        "timestamp": time.time(),
        "message": "This is a test webhook event from Agentic OS",
    }
    payload_str = json.dumps(test_payload)
    run_id = str(uuid.uuid4())[:8]
    
    # Log the event
    con = get_conn()
    try:
        con.execute(
            "INSERT INTO webhook_events(webhook_id,source,payload,run_id,status) VALUES(?,?,?,?,?)",
            (webhook_id, "agentic-os-test", payload_str, run_id, "processing")
        )
        con.execute(
            "UPDATE webhooks SET trigger_count=trigger_count+1, last_triggered=CURRENT_TIMESTAMP WHERE id=?",
            (webhook_id,)
        )
        con.commit()
    finally:
        con.close()
    
    # Build prompt from template
    template = wh.get("prompt_template", "Process test event: {payload}")
    prompt = template.replace("{payload}", payload_str[:500]).replace("{source}", "test")
    
    # Run agent async
    asyncio.create_task(_run_webhook_agent(wh, prompt, run_id, webhook_id, "agentic-os-test", payload_str))
    
    return {
        "ok": True,
        "run_id": run_id,
        "source": "agentic-os-test",
        "message": f"Test event sent — agent '{wh['agent_id']}' triggered",
    }


# ── Webhook templates ──────────────────────────────────────────────────────────
@router.get("/templates")
def webhook_templates():
    return [
        {
            "id": "github-push",
            "name": "GitHub Push → Code Review",
            "description": "Auto code review when you push to GitHub",
            "agent_id": "reviewer",
            "prompt_template": "A GitHub push was made to {payload[repository][name]}. Files changed: {payload[commits][0][modified]}. Review the changes for bugs, security issues, and best practices.",
            "setup": "Add this URL to your GitHub repo → Settings → Webhooks",
        },
        {
            "id": "stripe-payment",
            "name": "Stripe Payment → Onboarding",
            "description": "Trigger onboarding sequence when payment received",
            "agent_id": "creative",
            "prompt_template": "A payment was received from customer {payload[data][object][customer_email]}. Write a personalized onboarding email welcoming them and explaining the next steps.",
            "setup": "Add this URL to your Stripe Dashboard → Developers → Webhooks",
        },
        {
            "id": "form-submit",
            "name": "Form Submit → AI Response",
            "description": "AI processes form submissions and responds",
            "agent_id": "brain",
            "prompt_template": "A form was submitted with the following data: {payload}. Analyze this submission, extract key information, and prepare an appropriate response or action.",
            "setup": "Point any HTML form's action to this webhook URL",
        },
        {
            "id": "daily-digest",
            "name": "Daily Digest Generator",
            "description": "Run this daily to generate a status report",
            "agent_id": "researcher",
            "prompt_template": "Generate a comprehensive daily status report for today. Include: tasks completed, active loops status, memory highlights from today, system health summary, and recommendations for tomorrow.",
            "setup": "Call this URL via cron job or scheduling service daily",
        },
    ]
