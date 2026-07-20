# ═══════════════════════════════════════════════════════════════
#  Agentic OS — Configuration Validation
#  Pydantic settings for type-safe configuration
# ═══════════════════════════════════════════════════════════════
from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Optional, Union, Any, Dict, List, Tuple, Set, Callable, AsyncGenerator

_STATIC_ROOT = Path(__file__).resolve().parent.parent


def get_data_dir() -> Path:
    """Return runtime write directory (AGENTIC_OS_DATA_DIR when packaged or local workspace)."""
    env_dir = os.environ.get('AGENTIC_OS_DATA_DIR')
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return _STATIC_ROOT


from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    """Server configuration."""

    host: str = Field(default='0.0.0.0', description='Server host')
    port: int = Field(default=8787, ge=1024, le=65535, description='Server port')
    debug: bool = Field(default=False, description='Debug mode')
    log_format: str = Field(default='text', description='Log format: text or json')


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    openrouter_api_key: Optional[str] = Field(default=None, description='OpenRouter API key')
    ollama_base_url: str = Field(default='http://localhost:11434', description='Ollama base URL')
    default_model: str = Field(default='claude', description='Default model ID')
    primary_provider: str = Field(default='openrouter', description='Primary LLM provider')


class SecurityConfig(BaseModel):
    """Security configuration."""

    secret_key: Optional[str] = Field(default=None, description='Secret key for signing')
    rate_limit_max: int = Field(default=300, ge=10, description='Max requests per minute')
    rate_limit_window: int = Field(default=60, ge=10, description='Rate limit window (seconds)')


class FeatureFlags(BaseModel):
    """Feature flags."""

    memory_galaxy: bool = Field(default=True, description='Enable Memory Galaxy')
    swarm: bool = Field(default=True, description='Enable multi-agent swarm')
    builder: bool = Field(default=True, description='Enable live app builder')
    kanban: bool = Field(default=True, description='Enable Kanban board')
    vault: bool = Field(default=True, description='Enable secrets vault')
    e2e: bool = Field(default=False, description='Enable E2E testing (requires Playwright)')
    voice: bool = Field(default=True, description='Enable voice features')
    browser: bool = Field(default=True, description='Enable browser automation')


class AppConfig(BaseModel):
    """Root application configuration."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    features: FeatureFlags = Field(default_factory=FeatureFlags)
    version: str = Field(default='6.0.0', description='Application version')


def load_config() -> AppConfig:
    """Load configuration from environment variables."""
    return AppConfig(
        server=ServerConfig(
            host=os.getenv('AGENTIC_OS_HOST', '0.0.0.0'),
            port=int(os.getenv('AGENTIC_OS_PORT', '8787')),
            debug=os.getenv('AGENTIC_OS_DEBUG', 'false').lower() == 'true',
            log_format=os.getenv('LOG_FORMAT', 'text'),
        ),
        llm=LLMConfig(
            openrouter_api_key=os.getenv('OPENROUTER_API_KEY'),
            ollama_base_url=os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'),
            default_model=os.getenv('DEFAULT_MODEL', 'claude'),
            primary_provider=os.getenv('PRIMARY_PROVIDER', 'openrouter'),
        ),
        security=SecurityConfig(
            secret_key=os.getenv('SECRET_KEY'),
            rate_limit_max=int(os.getenv('RATE_LIMIT_MAX', '300')),
            rate_limit_window=int(os.getenv('RATE_LIMIT_WINDOW', '60')),
        ),
        features=FeatureFlags(
            memory_galaxy=os.getenv('FEATURE_MEMORY_GALAXY', 'true').lower() == 'true',
            swarm=os.getenv('FEATURE_SWARM', 'true').lower() == 'true',
            builder=os.getenv('FEATURE_BUILDER', 'true').lower() == 'true',
            kanban=os.getenv('FEATURE_KANBAN', 'true').lower() == 'true',
            vault=os.getenv('FEATURE_VAULT', 'true').lower() == 'true',
            e2e=os.getenv('FEATURE_E2E', 'false').lower() == 'true',
            voice=os.getenv('FEATURE_VOICE', 'true').lower() == 'true',
            browser=os.getenv('FEATURE_BROWSER', 'true').lower() == 'true',
        ),
    )


# Global config instance
config = load_config()
