#!/usr/bin/env python3
"""Shared proxy logic: config, DB, KeySlot, failover (streaming + non-streaming)."""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import openai
import yaml

logger = logging.getLogger("llm-proxy")

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
        return yaml.safe_load(f)


try:
    CFG = load_config()
except FileNotFoundError:
    CFG = {}  # Tests patch this; real usage raises at call time if keys is empty.

# ---------------------------------------------------------------------------
# SQLite Database
# ---------------------------------------------------------------------------
class Database:
    """Thin SQLite wrapper — auto-creates tables, uses WAL mode."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
            self._create_tables()
        return self._conn

    def _create_tables(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS call_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                model TEXT NOT NULL,
                key_index INTEGER NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                latency_ms REAL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 1,
                error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_call_ts ON call_history(ts);

            CREATE TABLE IF NOT EXISTS memory (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                tags TEXT DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                priority INTEGER NOT NULL DEFAULT 0,
                tags TEXT DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_task_status ON tasks(status);
        """)
        self.conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def commit(self) -> None:
        self.conn.commit()


DB_PATH = Path(os.environ.get("LLM_PROXY_DB_PATH", Path(__file__).parent / "llm_proxy.db"))
db = Database(DB_PATH)

# ---------------------------------------------------------------------------
# Proxy Slot Management
# ---------------------------------------------------------------------------
@dataclass
class KeySlot:
    """Tracks health of a single CLIProxyAPI endpoint."""
    index: int
    url: str
    client: openai.AsyncOpenAI = field(init=False)
    calls: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    last_error: str = ""
    disabled: bool = False

    def __post_init__(self):
        # Support per-slot tokens: CLAUDE_OAUTH_TOKEN_0, CLAUDE_OAUTH_TOKEN_1
        # Falls back to CLAUDE_OAUTH_TOKEN (single-token shorthand), then
        # CLAUDE_CODE_OAUTH_TOKEN for CLIProxyAPI compatibility
        token_key = f"CLAUDE_OAUTH_TOKEN_{self.index}"
        api_key = (
            os.environ.get(token_key)
            or os.environ.get("CLAUDE_OAUTH_TOKEN")
            or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
            or CFG.get("api_key", "not-needed")
        )
        self.client = openai.AsyncOpenAI(
            base_url=self.url,
            api_key=api_key,
            default_headers={
                "anthropic-version": "2023-06-01",
            },
        )

    @property
    def is_available(self) -> bool:
        return not self.disabled and time.time() >= self.cooldown_until

    @property
    def cooldown_remaining(self) -> float:
        return max(0.0, self.cooldown_until - time.time())

    def record_success(self) -> None:
        self.calls += 1
        self.consecutive_failures = 0

    def record_failure(self, error: str, is_rate_limit: bool = False) -> None:
        self.calls += 1
        self.failures += 1
        self.consecutive_failures += 1
        self.last_error = error
        base = CFG.get("cooldown_seconds", 30)
        if is_rate_limit:
            cooldown = min(base * (2 ** (self.consecutive_failures - 1)), 300)
        else:
            cooldown = min(base, 60)
        self.cooldown_until = time.time() + cooldown
        logger.warning(f"Proxy {self.index} cooling down for {cooldown:.0f}s: {error}")

    def record_permanent_failure(self, error: str) -> None:
        self.calls += 1
        self.failures += 1
        self.last_error = error
        self.disabled = True
        logger.error(f"Proxy {self.index} permanently disabled: {error}")

    def status_dict(self) -> dict:
        return {
            "index": self.index,
            "url": self.url,
            "available": self.is_available,
            "disabled": self.disabled,
            "cooldown_remaining_s": round(self.cooldown_remaining, 1),
            "total_calls": self.calls,
            "failures": self.failures,
            "last_error": self.last_error,
        }


keys: list[KeySlot] = []
_primary_url = CFG.get("primary_url", "")
_secondary_url = CFG.get("secondary_url", "")
if _primary_url:
    keys.append(KeySlot(index=0, url=_primary_url))
if _secondary_url:
    keys.append(KeySlot(index=1, url=_secondary_url))

strategy: str = CFG.get("strategy", "priority")
rr_counter: int = 0
DEFAULT_MODEL: str = CFG.get("default_model") or "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS: int = CFG.get("default_max_tokens") or 4096


def get_ordered_keys() -> list[KeySlot]:
    global rr_counter
    if strategy == "round_robin" and len(keys) > 1:
        ordered = [keys[rr_counter % len(keys)], keys[(rr_counter + 1) % len(keys)]]
        rr_counter += 1
        return ordered
    return list(keys)


async def wait_for_available_key(timeout: float = 60.0) -> Optional[KeySlot]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for k in keys:
            if k.is_available:
                return k
        if all(k.disabled for k in keys):
            return None
        await asyncio.sleep(0.5)
    return None

# ---------------------------------------------------------------------------
# Core LLM call logic
# ---------------------------------------------------------------------------
def _log_call(model: str, key_index: int, input_tok: int, output_tok: int,
              latency_ms: float, success: bool, error: str = "") -> None:
    db.execute(
        "INSERT INTO call_history (ts, model, key_index, input_tokens, output_tokens, latency_ms, success, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (time.time(), model, key_index, input_tok, output_tok, latency_ms, int(success), error),
    )
    db.commit()


async def _call_with_failover(messages: list[dict], model: str, max_tokens: int) -> dict:
    """Try proxy slots in order; failover on rate-limit or server errors. Returns full response dict."""
    if not keys:
        return {"error": "No proxy URLs configured. Set primary_url in config.yaml."}
    ordered = get_ordered_keys()
    last_err = ""

    for slot in ordered:
        if not slot.is_available:
            continue
        t0 = time.time()
        try:
            resp = await slot.client.chat.completions.create(
                model=model, max_tokens=max_tokens, messages=messages
            )
            latency = (time.time() - t0) * 1000
            slot.record_success()
            input_tok = resp.usage.prompt_tokens if resp.usage else 0
            output_tok = resp.usage.completion_tokens if resp.usage else 0
            _log_call(model, slot.index, input_tok, output_tok, latency, True)
            return {
                "text": resp.choices[0].message.content,
                "model": resp.model,
                "proxy_used": slot.index,
                "input_tokens": input_tok,
                "output_tokens": output_tok,
                "latency_ms": round(latency, 1),
            }
        except openai.RateLimitError as e:
            latency = (time.time() - t0) * 1000
            slot.record_failure(str(e), is_rate_limit=True)
            _log_call(model, slot.index, 0, 0, latency, False, str(e))
            last_err = str(e)
        except (openai.AuthenticationError, openai.PermissionDeniedError) as e:
            latency = (time.time() - t0) * 1000
            slot.record_permanent_failure(str(e))
            _log_call(model, slot.index, 0, 0, latency, False, str(e))
            last_err = str(e)
        except openai.APIStatusError as e:
            latency = (time.time() - t0) * 1000
            slot.record_failure(str(e), is_rate_limit=False)
            _log_call(model, slot.index, 0, 0, latency, False, str(e))
            last_err = str(e)

    # Fallback: wait for any available slot (strategy ordering not applied here)
    slot = await wait_for_available_key(timeout=30)
    if slot is None:
        return {"error": f"All proxies exhausted. Last error: {last_err}"}

    t0 = time.time()
    try:
        resp = await slot.client.chat.completions.create(
            model=model, max_tokens=max_tokens, messages=messages
        )
        latency = (time.time() - t0) * 1000
        slot.record_success()
        input_tok = resp.usage.prompt_tokens if resp.usage else 0
        output_tok = resp.usage.completion_tokens if resp.usage else 0
        _log_call(model, slot.index, input_tok, output_tok, latency, True)
        return {
            "text": resp.choices[0].message.content,
            "model": resp.model,
            "proxy_used": slot.index,
            "input_tokens": input_tok,
            "output_tokens": output_tok,
            "latency_ms": round(latency, 1),
        }
    except (openai.AuthenticationError, openai.PermissionDeniedError) as e:
        latency = (time.time() - t0) * 1000
        slot.record_permanent_failure(str(e))
        _log_call(model, slot.index, 0, 0, latency, False, str(e))
        return {"error": str(e)}
    except Exception as e:
        latency = (time.time() - t0) * 1000
        _log_call(model, slot.index, 0, 0, latency, False, str(e))
        return {"error": str(e)}


async def _call_with_failover_streaming(
    messages: list[dict], model: str, max_tokens: int,
    tools: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """Try proxy slots in order with streaming. Yields {"text": str} dicts,
    {"tool_call_deltas": list} dicts when tool calls are in progress,
    {"finish_reason": str} when the stream ends, and {"error": str} on failure.
    Pre-stream failures failover to next slot transparently.
    """
    if not keys:
        yield {"error": "No proxy URLs configured. Set primary_url in config.yaml."}
        return
    ordered = get_ordered_keys()
    last_err = ""

    async def _stream_slot(slot: KeySlot) -> AsyncGenerator[dict, None]:
        t0 = time.time()
        input_tok = 0
        output_tok = 0
        kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
        stream = await slot.client.chat.completions.create(**kwargs)
        last_yield = time.time()
        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            delta = (choice.delta.content if choice and choice.delta else None) or ""
            reasoning = getattr(choice.delta, "reasoning_content", "") or "" if (choice and choice.delta) else ""
            tool_call_deltas = getattr(choice.delta, "tool_calls", None) if (choice and choice.delta) else None
            finish_reason = choice.finish_reason if choice else None

            if delta:
                yield {"text": delta}
                last_yield = time.time()
            elif reasoning:
                yield {"text": ""}
                last_yield = time.time()
            elif tool_call_deltas:
                yield {"tool_call_deltas": [
                    {
                        "index": tc.index,
                        "id": getattr(tc, "id", None),
                        "type": getattr(tc, "type", "function"),
                        "function": {
                            "name": getattr(tc.function, "name", None) if tc.function else None,
                            "arguments": getattr(tc.function, "arguments", None) if tc.function else None,
                        },
                    }
                    for tc in tool_call_deltas
                ]}
                last_yield = time.time()
            elif time.time() - last_yield > 5:
                yield {"text": ""}
                last_yield = time.time()

            if finish_reason:
                yield {"finish_reason": finish_reason}

            if hasattr(chunk, "usage") and chunk.usage:
                input_tok = getattr(chunk.usage, "prompt_tokens", 0) or 0
                output_tok = getattr(chunk.usage, "completion_tokens", 0) or 0

        latency = (time.time() - t0) * 1000
        slot.record_success()
        _log_call(model, slot.index, input_tok, output_tok, latency, True)

    for slot in ordered:
        if not slot.is_available:
            continue
        t0 = time.time()
        try:
            async for item in _stream_slot(slot):
                yield item
            return
        except openai.RateLimitError as e:
            latency = (time.time() - t0) * 1000
            slot.record_failure(str(e), is_rate_limit=True)
            _log_call(model, slot.index, 0, 0, latency, False, str(e))
            last_err = str(e)
        except (openai.AuthenticationError, openai.PermissionDeniedError) as e:
            latency = (time.time() - t0) * 1000
            slot.record_permanent_failure(str(e))
            _log_call(model, slot.index, 0, 0, latency, False, str(e))
            last_err = str(e)
        except openai.APIStatusError as e:
            latency = (time.time() - t0) * 1000
            slot.record_failure(str(e), is_rate_limit=False)
            _log_call(model, slot.index, 0, 0, latency, False, str(e))
            last_err = str(e)

    # All ordered slots failed — wait for soonest available
    slot = await wait_for_available_key(timeout=30)
    if slot is None:
        yield {"error": f"All proxies exhausted. Last error: {last_err}"}
        return

    t0 = time.time()
    try:
        async for item in _stream_slot(slot):
            yield item
    except Exception as e:
        latency = (time.time() - t0) * 1000
        _log_call(model, slot.index, 0, 0, latency, False, str(e))
        yield {"error": str(e)}
