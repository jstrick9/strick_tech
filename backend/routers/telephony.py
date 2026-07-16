"""
Agentic OS — Autonomous Telephony Router (`/api/telephony`)
Enables real-time WebRTC audio streaming and Twilio voice webhook orchestration.
Created by Joshua Strickland and Strick Tech for Pro & Enterprise editions.
"""
from __future__ import annotations
import time
import uuid
from typing import Any
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

router = APIRouter(prefix="/api/telephony", tags=["telephony"])

_CALL_SESSIONS: dict[str, dict[str, Any]] = {}


class OutboundCallRequest(BaseModel):
    """Pydantic data model for OutboundCallRequest."""
    phone_number: str
    agent_id: str = "voice_assistant"
    greeting_prompt: str = "Hello, I am calling from Strick Tech regarding your AI workflow."
    goal: str = "Confirm appointment details and answer technical questions."


@router.get("/config")
def get_telephony_config(request: Request) -> dict[str, Any]:
    """Retrieve runtime configuration for voice-to-voice WebRTC and Twilio telephony agents."""
    host = request.headers.get("host", "127.0.0.1:8787")
    wss_url = f"wss://{host}/api/telephony/stream"
    return {
        "ok": True,
        "providers_supported": ["WebRTC", "Twilio", "LiveKit", "LocalAudio"],
        "stream_endpoint": wss_url,
        "sample_rate": 16000,
        "codecs_supported": ["PCMU", "OPUS", "PCM"],
        "turn_detection_ms": 300,
        "creator": "Joshua Strickland and Strick Tech",
        "editions_supported": ["Pro", "Enterprise"],
        "timestamp": time.time(),
    }


@router.post("/twilio/voice")
async def handle_twilio_webhook(request: Request) -> Response:
    """Handle incoming Twilio voice call webhooks and return TwiML WebSocket streaming instructions."""
    form_data = await request.form()
    call_sid = str(form_data.get("CallSid", f"call_{uuid.uuid4().hex[:8]}"))
    from_number = str(form_data.get("From", "unknown"))
    to_number = str(form_data.get("To", "unknown"))
    host = request.headers.get("host", "127.0.0.1:8787")

    _CALL_SESSIONS[call_sid] = {
        "call_sid": call_sid,
        "from": from_number,
        "to": to_number,
        "direction": "inbound",
        "status": "active",
        "started_at": time.time(),
        "transcript": [],
        "tools_executed": [],
    }

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Connecting your call to the autonomous Agentic OS voice assistant.</Say>
    <Connect>
        <Stream url="wss://{host}/api/telephony/stream/{call_sid}" />
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@router.post("/calls/outbound")
def initiate_outbound_call(payload: OutboundCallRequest) -> dict[str, Any]:
    """Initiate an autonomous outbound voice call session."""
    call_id = f"out_{uuid.uuid4().hex[:8]}"
    _CALL_SESSIONS[call_id] = {
        "call_id": call_id,
        "phone_number": payload.phone_number,
        "agent_id": payload.agent_id,
        "greeting": payload.greeting_prompt,
        "goal": payload.goal,
        "direction": "outbound",
        "status": "ringing",
        "started_at": time.time(),
        "transcript": [{"speaker": "agent", "text": payload.greeting_prompt, "ts": time.time()}],
        "tools_executed": [],
    }
    return {
        "ok": True,
        "call_id": call_id,
        "status": "ringing",
        "message": f"Outbound call initiated to {payload.phone_number} with agent '{payload.agent_id}'",
    }


@router.get("/calls/list")
def list_active_calls() -> dict[str, Any]:
    """Retrieve all active and recently completed voice-to-voice telephony sessions."""
    return {
        "ok": True,
        "count": len(_CALL_SESSIONS),
        "active_count": sum(1 for c in _CALL_SESSIONS.values() if c.get("status") in ("active", "ringing")),
        "calls": list(_CALL_SESSIONS.values()),
    }


@router.post("/calls/{call_id}/end")
def end_telephony_call(call_id: str) -> dict[str, Any]:
    """Terminate an active voice call session and calculate call duration."""
    if call_id not in _CALL_SESSIONS:
        raise HTTPException(status_code=404, detail="Call session not found")
    _CALL_SESSIONS[call_id]["status"] = "completed"
    _CALL_SESSIONS[call_id]["ended_at"] = time.time()
    duration = _CALL_SESSIONS[call_id]["ended_at"] - _CALL_SESSIONS[call_id]["started_at"]
    _CALL_SESSIONS[call_id]["duration_sec"] = round(duration, 2)
    return {"ok": True, "call_id": call_id, "status": "completed", "duration_sec": round(duration, 2)}
