"""Configuration and model-provider selection for the research agent."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (two levels above this file's package dir).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

PROVIDER_OPENAI = "openai"
PROVIDER_LOCAL = "local"
PROVIDERS = (PROVIDER_OPENAI, PROVIDER_LOCAL)

DEFAULT_LOCAL_MODEL = "qwen3:4b"
DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:11434/v1"


def get_provider() -> str:
    """Return the active provider.

    Priority: RESEARCH_PROVIDER env var -> "openai" if an API key exists -> "local".
    """
    env = os.getenv("RESEARCH_PROVIDER", "").strip().lower()
    if env in PROVIDERS:
        return env
    if os.getenv("OPENAI_API_KEY"):
        return PROVIDER_OPENAI
    return PROVIDER_LOCAL


def get_openai_model() -> str | None:
    """Optional explicit OpenAI model id (e.g. for the OpenAI provider)."""
    value = os.getenv("OPENAI_MODEL", "").strip()
    return value or None


def get_openai_base_url() -> str:
    """Optional custom OpenAI-compatible endpoint (e.g. DeepSeek / GLM / Moonshot).

    Empty string means "use the OpenAI default endpoint".
    """
    return os.getenv("OPENAI_BASE_URL", "").strip()


def get_local_model() -> str:
    return os.getenv("LOCAL_MODEL", "").strip() or DEFAULT_LOCAL_MODEL


def get_local_base_url() -> str:
    return os.getenv("LOCAL_BASE_URL", "").strip() or DEFAULT_LOCAL_BASE_URL


def get_embed_model() -> str:
    """Ollama embedding model used by the vector memory."""
    return os.getenv("EMBED_MODEL", "").strip() or "nomic-embed-text"


def get_ollama_api_url() -> str:
    """Ollama native API base (without the /v1 suffix)."""
    base = get_local_base_url()
    return base.removesuffix("/v1")


def get_tavily_api_key() -> str:
    """Tavily search API key (optional; enables high-quality search)."""
    return os.getenv("TAVILY_API_KEY", "").strip()
