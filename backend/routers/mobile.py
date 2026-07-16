"""
Agentic OS — Mobile App Router (`/api/mobile`)
Exposes Expo & React Native mobile configuration, app manifest, and push notification device registration.
Created by Joshua Strickland and Strick Tech.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/mobile", tags=["mobile"])

from backend.config import get_data_dir
ROOT = get_data_dir()
MEMORY_DIR = ROOT / "memory"
MOBILE_DEVICES_FILE = MEMORY_DIR / "mobile_devices.json"

MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _get_devices() -> list[dict[str, Any]]:
    """Retrieve registered mobile devices from local JSON store."""
    if MOBILE_DEVICES_FILE.exists():
        try:
            return json.loads(MOBILE_DEVICES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_devices(devices: list[dict[str, Any]]) -> None:
    """Save mobile device registration records to local JSON store."""
    MOBILE_DEVICES_FILE.write_text(json.dumps(devices, indent=2), encoding="utf-8")


class PushRegisterRequest(BaseModel):
    """Pydantic data model for PushRegisterRequest."""
    token: str
    platform: str = "ios"  # ios or android
    device_name: str = "Mobile Device"
    user_id: str = "jstrickland"


@router.get("/config")
def get_mobile_config(request: Request) -> dict[str, Any]:
    """Retrieve runtime configuration for Expo and React Native mobile clients."""
    host = request.headers.get("host", "127.0.0.1:8787")
    protocol = "https" if request.url.scheme == "https" else "http"
    return {
        "ok": True,
        "api_base_url": f"{protocol}://{host}",
        "version": "7.0.0",
        "editions_supported": ["Free", "Pro", "Enterprise"],
        "creator": "Joshua Strickland and Strick Tech",
        "capabilities": {
            "chat_streaming": True,
            "voice_input_whisper": True,
            "neural_tts_playback": True,
            "swarm_orchestration": True,
            "kanban_tasks": True,
            "information_hierarchy_sync": True,
            "offline_sqlite_cache": True,
            "push_notifications": True,
        },
        "theme": {
            "mode": "dark",
            "primary_color": "#3b82f6",
            "accent_color": "#8b5cf6",
            "background": "#08090e",
        },
        "timestamp": time.time(),
    }


@router.get("/manifest")
def get_mobile_manifest() -> dict[str, Any]:
    """Retrieve the Expo `app.json` build manifest for native iOS and Android compilation."""
    return {
        "ok": True,
        "expo": {
            "name": "Agentic OS Platform",
            "slug": "agentic-os-mobile",
            "version": "7.0.0",
            "orientation": "portrait",
            "icon": "./assets/icon.png",
            "userInterfaceStyle": "dark",
            "splash": {
                "image": "./assets/splash.png",
                "resizeMode": "contain",
                "backgroundColor": "#08090e"
            },
            "updates": {
                "fallbackToCacheTimeout": 0
            },
            "assetBundlePatterns": ["**/*"],
            "ios": {
                "supportsTablet": True,
                "bundleIdentifier": "com.stricktech.agenticos",
                "infoPlist": {
                    "NSMicrophoneUsageDescription": "Allow Agentic OS to record voice input for AI agents.",
                    "NSAppTransportSecurity": {
                        "NSAllowsArbitraryLoads": True
                    }
                }
            },
            "android": {
                "package": "com.stricktech.agenticos",
                "permissions": [
                    "RECORD_AUDIO",
                    "INTERNET",
                    "ACCESS_NETWORK_STATE",
                    "RECEIVE_BOOT_COMPLETED",
                    "VIBRATE"
                ]
            },
            "plugins": [
                "expo-av",
                "expo-secure-store",
                "expo-notifications"
            ]
        }
    }


@router.post("/push-register")
def register_push_token(payload: PushRegisterRequest) -> dict[str, Any]:
    """Register or update a mobile device push notification token."""
    token = payload.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Device token required")
    devices = _get_devices()
    existing = next((d for d in devices if d["token"] == token), None)
    if existing:
        existing["platform"] = payload.platform
        existing["device_name"] = payload.device_name
        existing["last_active"] = time.time()
    else:
        devices.append({
            "token": token,
            "platform": payload.platform,
            "device_name": payload.device_name,
            "user_id": payload.user_id,
            "registered_at": time.time(),
            "last_active": time.time(),
        })
    _save_devices(devices)
    return {"ok": True, "message": "Push token registered successfully", "device_count": len(devices)}


@router.get("/devices")
def list_mobile_devices() -> dict[str, Any]:
    """Retrieve all registered mobile devices and push endpoints."""
    devices = _get_devices()
    return {"ok": True, "count": len(devices), "devices": devices}
