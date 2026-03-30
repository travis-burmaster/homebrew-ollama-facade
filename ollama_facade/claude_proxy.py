#!/usr/bin/env python3
"""
Embedded Claude OAuth proxy core.
Adapted from https://github.com/travis-burmaster/claude-oauth-proxy
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, AsyncGenerator

try:
    from curl_cffi import requests as cffi_requests
    CFFI_AVAILABLE = True
except ImportError as _curl_cffi_import_error:
    CFFI_AVAILABLE = False
    _curl_cffi_import_error_msg = str(_curl_cffi_import_error)


# ── Constants ─────────────────────────────────────────────────────────────────

ANTHROPIC_API = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
OAUTH_BETA = (
    "claude-code-20250219,oauth-2025-04-20,"
    "interleaved-thinking-2025-05-14,"
    "context-management-2025-06-27,"
    "prompt-caching-scope-2026-01-05"
)
# Older beta string kept as fallback reference
OAUTH_BETA_COMPAT = (
    "claude-code-20250219,oauth-2025-04-20,"
    "prompt-caching-2024-07-31"
)
TOKEN_REFRESH_URL = "https://api.anthropic.com/v1/oauth/token"
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
BILLING_HEADER = "x-anthropic-billing-header: cc_version=2.1.63.e4d; cc_entrypoint=cli; cch=ce2dd;"

DEFAULT_CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
DEFAULT_AUTH_PROFILES_PATH = (
    Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
)

MODEL_ALIASES = {
    "sonnet": "claude-sonnet-4-6",
    "claude-sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
    "claude-opus": "claude-opus-4-6",
    "haiku": "claude-haiku-4-5-20251001",
    "claude-haiku": "claude-haiku-4-5-20251001",
}


# ── Account / Token Management ────────────────────────────────────────────────

class Account:
    """Represents a single Claude subscription account with token management."""

    def __init__(self, name: str, token: str | None = None,
                 token_path: str | None = None):
        self.name = name
        self._token = token
        self._token_path = Path(token_path).expanduser() if token_path else None
        self._lock = threading.Lock()
        self.cooldown_until: float = 0
        self.failure_count: int = 0

    @property
    def is_available(self) -> bool:
        return time.time() >= self.cooldown_until

    def get_token(self) -> str:
        with self._lock:
            # Try auth-profiles.json path (OpenClaw)
            if DEFAULT_AUTH_PROFILES_PATH.exists():
                try:
                    data = json.loads(DEFAULT_AUTH_PROFILES_PATH.read_text())
                    tok = data.get("profiles", {}).get("anthropic:default", {}).get("token")
                    if tok:
                        return tok
                except Exception:
                    pass

            # Try explicit token
            if self._token:
                return self._token

            # Try explicit credentials path (auto-detect format)
            if self._token_path and self._token_path.exists():
                return self._load_from_credentials(self._token_path)

            # Fall back to ~/.claude/.credentials.json (claude setup-token)
            if DEFAULT_CREDENTIALS_PATH.exists() and DEFAULT_CREDENTIALS_PATH.stat().st_size > 0:
                return self._load_from_credentials(DEFAULT_CREDENTIALS_PATH)

            raise RuntimeError(f"Account '{self.name}': no token available. "
                               "Run 'claude setup-token' to authenticate.")

    def _load_from_credentials(self, path: Path) -> str:
        """Load token from credentials file (auto-detects format)."""
        creds = json.loads(path.read_text())

        # Format 1: cli-proxy-api format {access_token, refresh_token, expired, ...}
        if "access_token" in creds:
            return self._load_cliproxyapi_format(creds, path)

        # Format 2: claude setup-token format {claudeAiOauth: {accessToken, refreshToken, expiresAt}}
        oauth = creds.get("claudeAiOauth", {})
        expires_at = oauth.get("expiresAt", 0)
        if expires_at < (time.time() + 300) * 1000:
            self._try_refresh(oauth, creds, path)
            creds = json.loads(path.read_text())
            oauth = creds.get("claudeAiOauth", {})
        token = oauth.get("accessToken")
        if not token:
            raise RuntimeError(f"Account '{self.name}': no accessToken in {path}")
        return token

    def force_refresh(self) -> None:
        """Force a token refresh (called after 401). Works with any credential format."""
        with self._lock:
            path = self._token_path
            if not path:
                path = DEFAULT_CREDENTIALS_PATH
            if not path or not path.exists():
                return
            try:
                creds = json.loads(path.read_text())
                if "access_token" in creds:
                    self._try_refresh_cliproxyapi(creds, path)
                else:
                    oauth = creds.get("claudeAiOauth", {})
                    self._try_refresh(oauth, creds, path)
            except Exception:
                pass

    def _load_cliproxyapi_format(self, creds: dict, path: Path) -> str:
        """Load from cli-proxy-api format {access_token, refresh_token, expired}."""
        from datetime import datetime, timezone, timedelta
        token = creds.get("access_token", "")
        if not token:
            raise RuntimeError(f"Account '{self.name}': no access_token in {path}")

        # Check expiry — field is ISO 8601 string like "2026-03-30T18:27:42-04:00"
        expired_str = creds.get("expired", "")
        if expired_str:
            try:
                expires_dt = datetime.fromisoformat(expired_str)
                now = datetime.now(timezone.utc)
                if expires_dt < now + timedelta(minutes=5):
                    refresh_tok = creds.get("refresh_token", "")
                    if refresh_tok:
                        self._try_refresh_cliproxyapi(creds, path)
                        creds = json.loads(path.read_text())
                        token = creds.get("access_token", "")
            except (ValueError, TypeError):
                pass  # Can't parse expiry, use token as-is

        return token

    def _try_refresh(self, oauth: dict, creds: dict, path: Path) -> None:
        refresh_tok = oauth.get("refreshToken", "")
        if not refresh_tok:
            return
        try:
            payload = json.dumps({
                "grant_type": "refresh_token",
                "refresh_token": refresh_tok,
                "client_id": OAUTH_CLIENT_ID,
            }).encode()
            req = urllib.request.Request(
                TOKEN_REFRESH_URL, data=payload,
                headers={"Content-Type": "application/json",
                         "anthropic-version": ANTHROPIC_VERSION},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                new_token = data.get("access_token")
                new_refresh = data.get("refresh_token")
                expires_in = data.get("expires_in", 3600)
                if new_token:
                    creds["claudeAiOauth"]["accessToken"] = new_token
                    if new_refresh:
                        creds["claudeAiOauth"]["refreshToken"] = new_refresh
                    creds["claudeAiOauth"]["expiresAt"] = int(
                        (time.time() + expires_in) * 1000
                    )
                    path.write_text(json.dumps(creds, indent=2))
        except Exception as e:
            import sys
            print(f"[claude-proxy] {self.name}: token refresh failed: {e}", file=sys.stderr)

    def _try_refresh_cliproxyapi(self, creds: dict, path: Path) -> None:
        """Refresh token for cli-proxy-api format credentials."""
        from datetime import datetime, timezone, timedelta
        import sys
        refresh_tok = creds.get("refresh_token", "")
        if not refresh_tok:
            print(f"[claude-proxy] {self.name}: no refresh_token in {path}", file=sys.stderr)
            return
        try:
            payload = json.dumps({
                "grant_type": "refresh_token",
                "refresh_token": refresh_tok,
                "client_id": OAUTH_CLIENT_ID,
            }).encode()
            print(f"[claude-proxy] {self.name}: refreshing token...", file=sys.stderr)
            req = urllib.request.Request(
                TOKEN_REFRESH_URL, data=payload,
                headers={"Content-Type": "application/json",
                         "anthropic-version": ANTHROPIC_VERSION},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                new_token = data.get("access_token")
                new_refresh = data.get("refresh_token")
                expires_in = data.get("expires_in", 3600)
                if new_token:
                    creds["access_token"] = new_token
                    if new_refresh:
                        creds["refresh_token"] = new_refresh
                    expires_dt = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                    creds["expired"] = expires_dt.isoformat()
                    creds["last_refresh"] = datetime.now(timezone.utc).isoformat()
                    path.write_text(json.dumps(creds, indent=2))
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            print(f"[claude-proxy] {self.name}: token refresh failed: {e.code} {body}", file=sys.stderr)
        except Exception as e:
            print(f"[claude-proxy] {self.name}: token refresh failed: {e}", file=sys.stderr)

    def record_rate_limit(self, cooldown_seconds: int = 60) -> None:
        self.failure_count += 1
        self.cooldown_until = time.time() + cooldown_seconds

    def record_success(self) -> None:
        self.failure_count = 0


class AccountPool:
    """Manages multiple Claude accounts with round-robin failover."""

    def __init__(self, accounts: list[Account]):
        if not accounts:
            raise ValueError("At least one account required")
        self.accounts = accounts
        self._index = 0
        self._lock = threading.Lock()

    def get_account(self) -> Account:
        with self._lock:
            for _ in range(len(self.accounts)):
                account = self.accounts[self._index % len(self.accounts)]
                self._index = (self._index + 1) % len(self.accounts)
                if account.is_available:
                    return account
            # All on cooldown — return soonest available
            return min(self.accounts, key=lambda a: a.cooldown_until)

    @classmethod
    def from_config(cls, config: dict) -> "AccountPool":
        accounts = []
        for i, acct in enumerate(config.get("accounts", [])):
            # Support both "credentials" (new key) and "token_path" (legacy)
            cred_path = acct.get("credentials") or acct.get("token_path")
            accounts.append(Account(
                name=acct.get("name", f"Account {i + 1}"),
                token=acct.get("token"),
                token_path=cred_path,
            ))
        if not accounts:
            # Default: use whatever credentials are available locally
            accounts = [Account(name="Default")]
        return cls(accounts)


# ── Request Helpers ───────────────────────────────────────────────────────────

def _resolve_model(name: str) -> str:
    base = name.split(":")[0].strip()
    return MODEL_ALIASES.get(base, base)


def _build_headers(token: str, stream: bool = False) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "anthropic-version": ANTHROPIC_VERSION,
        "anthropic-beta": OAUTH_BETA,
        "Anthropic-Dangerous-Direct-Browser-Access": "true",
        "X-App": "cli",
        "X-Stainless-Arch": "x86_64",
        "X-Stainless-Lang": "js",
        "X-Stainless-Os": "Linux",
        "X-Stainless-Package-Version": "0.74.0",
        "X-Stainless-Retry-Count": "0",
        "X-Stainless-Runtime": "node",
        "X-Stainless-Runtime-Version": "v22.22.1",
        "X-Stainless-Timeout": "600",
        "User-Agent": "claude-cli/2.1.85 (external, sdk-cli)",
        "Content-Type": "application/json",
        "Connection": "keep-alive",
        "Accept": "text/event-stream" if stream else "application/json",
        "Accept-Encoding": "identity" if stream else "gzip, deflate, br, zstd",
    }


def _inject_cloaking(body: dict) -> dict:
    """Inject billing cloaking into system prompt (required for sonnet/opus access)."""
    body = dict(body)
    existing = body.get("system")
    cloaking = {"type": "text", "text": BILLING_HEADER}
    if existing is None:
        body["system"] = [
            cloaking,
            {"type": "text", "text": "You are a helpful assistant.",
             "cache_control": {"type": "ephemeral"}},
        ]
    elif isinstance(existing, str):
        body["system"] = [
            cloaking,
            {"type": "text", "text": existing, "cache_control": {"type": "ephemeral"}},
        ]
    elif isinstance(existing, list):
        body["system"] = [cloaking] + existing
    return body


def _openai_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """Convert OpenAI tool definitions to Anthropic format."""
    result = []
    for t in tools:
        fn = t.get("function", {})
        result.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return result


def openai_messages_to_anthropic_body(
    messages: list[dict],
    model: str,
    max_tokens: int,
    tools: list[dict] | None = None,
) -> dict:
    """Convert OpenAI-format chat messages to an Anthropic /v1/messages request body."""
    system_parts: list[str] = []
    anthropic_messages: list[dict] = []

    for m in messages:
        role = m.get("role", "")
        content = m.get("content")

        if role == "system":
            if content:
                system_parts.append(content if isinstance(content, str) else
                                    " ".join(c.get("text", "") for c in content
                                             if isinstance(c, dict)))
            continue

        if role == "assistant":
            tool_calls = m.get("tool_calls")
            if tool_calls:
                # Convert tool_calls → tool_use content blocks
                blocks: list[dict] = []
                if content:
                    text = content if isinstance(content, str) else (
                        " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                    )
                    if text:
                        blocks.append({"type": "text", "text": text})
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    args_raw = fn.get("arguments", "{}")
                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                    except Exception:
                        args = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", f"call_{len(blocks)}"),
                        "name": fn.get("name", ""),
                        "input": args,
                    })
                anthropic_messages.append({"role": "assistant", "content": blocks})
            else:
                # Plain assistant message
                text = content if isinstance(content, str) else (
                    " ".join(c.get("text", "") for c in (content or []) if isinstance(c, dict))
                )
                anthropic_messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": text}],
                })
            continue

        if role == "tool":
            # tool result → user message with tool_result block
            result_block = {
                "type": "tool_result",
                "tool_use_id": m.get("tool_call_id", ""),
                "content": content if isinstance(content, str) else str(content),
            }
            # Merge into previous user message if possible, otherwise create new one
            if anthropic_messages and anthropic_messages[-1]["role"] == "user":
                anthropic_messages[-1]["content"].append(result_block)
            else:
                anthropic_messages.append({"role": "user", "content": [result_block]})
            continue

        # user role
        if isinstance(content, str):
            blocks_u: list[dict] = [{"type": "text", "text": content}]
        elif isinstance(content, list):
            blocks_u = []
            for c in content:
                if isinstance(c, str):
                    blocks_u.append({"type": "text", "text": c})
                elif isinstance(c, dict):
                    if c.get("type") == "text":
                        blocks_u.append({"type": "text", "text": c.get("text", "")})
                    elif c.get("type") == "image_url":
                        # Skip image content (not supported here)
                        pass
        else:
            blocks_u = [{"type": "text", "text": str(content or "")}]

        # Merge consecutive user messages
        if anthropic_messages and anthropic_messages[-1]["role"] == "user":
            anthropic_messages[-1]["content"].extend(blocks_u)
        else:
            anthropic_messages.append({"role": "user", "content": blocks_u})

    # Ensure messages start with user role (Anthropic requirement)
    while anthropic_messages and anthropic_messages[0]["role"] != "user":
        anthropic_messages.pop(0)

    body: dict[str, Any] = {
        "model": _resolve_model(model),
        "messages": anthropic_messages,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if system_parts:
        body["system"] = "\n\n".join(system_parts)
    if tools:
        body["tools"] = _openai_tools_to_anthropic(tools)

    return body


# ── Core API Call ─────────────────────────────────────────────────────────────

def call_anthropic(pool: AccountPool, body: dict, stream: bool, max_retries: int = 3):
    """Call Anthropic API with multi-account failover. Returns response object."""
    if not CFFI_AVAILABLE:
        import sys
        raise RuntimeError(
            f"curl-cffi not importable in this Python environment ({sys.executable}). "
            f"Import error: {_curl_cffi_import_error_msg}. "
            f"Fix: {sys.executable} -m pip install curl-cffi"
        )

    body = _inject_cloaking(body)
    payload = json.dumps(body).encode()
    url = f"{ANTHROPIC_API}/v1/messages?beta=true"

    for attempt in range(max_retries):
        account = pool.get_account()
        try:
            token = account.get_token()
            headers = _build_headers(token, stream=stream)
            resp = cffi_requests.post(
                url, headers=headers, data=payload,
                impersonate="chrome", timeout=300, stream=stream,
            )
            if resp.status_code == 401:
                # Token likely expired/revoked — force refresh and retry once
                import sys
                print(f"[claude-proxy] {account.name}: 401 — forcing token refresh", file=sys.stderr)
                account.force_refresh()
                token = account.get_token()
                headers = _build_headers(token, stream=stream)
                resp = cffi_requests.post(
                    url, headers=headers, data=payload,
                    impersonate="chrome", timeout=300, stream=stream,
                )
                if resp.status_code >= 400:
                    raise RuntimeError(f"Anthropic API error {resp.status_code}: {resp.text[:200]}")
                account.record_success()
                return resp
            if resp.status_code == 429:
                account.record_rate_limit(cooldown_seconds=60 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise RuntimeError(f"Anthropic API error {resp.status_code}: {resp.text[:200]}")
            account.record_success()
            return resp
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            import sys
            print(f"[claude-proxy] {account.name}: error ({e}), retrying...", file=sys.stderr)

    raise RuntimeError("All accounts exhausted")


# ── Async Streaming Bridge ────────────────────────────────────────────────────

async def stream_anthropic(
    pool: AccountPool,
    body: dict,
) -> AsyncGenerator[dict, None]:
    """Async generator that streams Anthropic SSE events as parsed dicts.

    Yields dicts with keys:
      {"text": str}                                    — text delta
      {"tool_call_deltas": list}                       — tool use input delta
      {"finish_reason": str}                           — stream finished
      {"error": str}                                   — error occurred
    """
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _SENTINEL = object()

    def _thread():
        try:
            resp = call_anthropic(pool, body, stream=True)
            # Track tool_use blocks by content block index
            tool_blocks: dict[int, dict] = {}

            for raw_line in resp.iter_lines():
                line = raw_line.decode(errors="ignore").strip() if isinstance(raw_line, bytes) else raw_line.strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    event = json.loads(data_str)
                except Exception:
                    continue

                etype = event.get("type", "")

                if etype == "content_block_start":
                    idx = event.get("index", 0)
                    block = event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        tool_blocks[idx] = {
                            "id": block.get("id", ""),
                            "name": block.get("name", ""),
                        }

                elif etype == "content_block_delta":
                    idx = event.get("index", 0)
                    delta = event.get("delta", {})
                    dtype = delta.get("type", "")

                    if dtype == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            loop.call_soon_threadsafe(queue.put_nowait, {"text": text})

                    elif dtype == "input_json_delta":
                        args_fragment = delta.get("partial_json", "")
                        tb = tool_blocks.get(idx, {})
                        chunk = {
                            "tool_call_deltas": [{
                                "index": idx,
                                "id": tb.get("id"),
                                "type": "function",
                                "function": {
                                    "name": tb.get("name"),
                                    "arguments": args_fragment,
                                },
                            }]
                        }
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)

                elif etype == "message_delta":
                    delta = event.get("delta", {})
                    stop_reason = delta.get("stop_reason")
                    if stop_reason:
                        finish = "tool_calls" if stop_reason == "tool_use" else stop_reason
                        loop.call_soon_threadsafe(queue.put_nowait, {"finish_reason": finish})

        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, {"error": str(e)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    thread = threading.Thread(target=_thread, daemon=True)
    thread.start()

    while True:
        item = await queue.get()
        if item is _SENTINEL:
            break
        yield item
