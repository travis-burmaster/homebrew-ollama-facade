#!/usr/bin/env python3
"""Proxy core: config loading, account pool, and streaming bridge to Anthropic."""

from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator

import yaml

from ollama_facade.claude_proxy import AccountPool, openai_messages_to_anthropic_body, stream_anthropic

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _resolve_config_path() -> Path:
    if env := os.environ.get("OLLAMA_FACADE_CONFIG"):
        return Path(env)
    user_cfg = Path.home() / ".ollama-facade" / "config.yaml"
    if user_cfg.exists():
        return user_cfg
    return Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    path = _resolve_config_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Config not found at {path}. Run: ollama-facade config --init"
        )
    with open(path) as f:
        return yaml.safe_load(f) or {}


try:
    CFG = load_config()
except FileNotFoundError:
    CFG = {}

# ---------------------------------------------------------------------------
# Account Pool
# ---------------------------------------------------------------------------

_pool: AccountPool | None = None


def get_pool() -> AccountPool:
    global _pool
    if _pool is None:
        _pool = AccountPool.from_config(CFG)
    return _pool


# ---------------------------------------------------------------------------
# Public constants used by server.py
# ---------------------------------------------------------------------------

DEFAULT_MODEL: str = CFG.get("default_model") or "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS: int = CFG.get("default_max_tokens") or 4096

# ---------------------------------------------------------------------------
# Streaming interface (consumed by server.py)
# ---------------------------------------------------------------------------

async def _call_with_failover_streaming(
    messages: list[dict],
    model: str,
    max_tokens: int,
    tools: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """Async generator yielding streaming chunks from Anthropic.

    Yields dicts with keys:
      {"text": str}
      {"tool_call_deltas": list}
      {"finish_reason": str}
      {"error": str}
    """
    pool = get_pool()
    body = openai_messages_to_anthropic_body(messages, model, max_tokens, tools=tools)

    try:
        async for chunk in stream_anthropic(pool, body):
            yield chunk
    except Exception as e:
        yield {"error": str(e)}
