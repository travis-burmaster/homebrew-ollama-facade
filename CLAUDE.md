# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

`ollama-facade` is a local proxy server that exposes an Ollama-compatible API and calls the Anthropic API directly using your Claude Max OAuth token. Any Ollama-compatible client (Cursor, Open WebUI, LangChain, etc.) can talk to Claude without per-token billing.

```
Ollama Clients → ollama-facade :11434 → api.anthropic.com (Chrome TLS + OAuth)
```

This repo is a **Homebrew tap** — the primary artifact is `Formula/ollama-facade.rb`, and the Python source lives in `ollama_facade/`.

## Development Commands

```bash
# Install in editable mode for local development
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .

# Initialize default config
ollama-facade config --init

# Start server (foreground)
ollama-facade start

# Start as background daemon
ollama-facade start --daemon

# Check daemon status / stop
ollama-facade status
ollama-facade stop
```

No test suite exists. The Homebrew formula test (`brew test ollama-facade`) just verifies `ollama-facade --help` exits cleanly.

## Code Architecture

### Four-File Structure

**`ollama_facade/claude_proxy.py`** — Embedded Claude OAuth client (adapted from claude-oauth-proxy):
- `Account` — reads OAuth token from credentials file, auto-refreshes using refresh token
- `AccountPool` — round-robin/priority failover across multiple accounts
- `call_anthropic(pool, body, stream)` — synchronous curl-cffi call with Chrome TLS impersonation
- `stream_anthropic(pool, body)` — async generator bridge: runs `call_anthropic` in a background thread, pushes SSE events to an `asyncio.Queue`, yields parsed dicts
- `openai_messages_to_anthropic_body(messages, model, max_tokens, tools)` — converts OpenAI-format messages to Anthropic format (system extraction, tool_calls→tool_use blocks, tool role→tool_result blocks)

**`ollama_facade/proxy_core.py`** — Thin adapter layer:
- Loads `CFG` from config file at import time
- `get_pool()` — lazily initializes `AccountPool` from config
- `_call_with_failover_streaming(messages, model, max_tokens, tools)` — the interface `server.py` calls; converts messages and delegates to `stream_anthropic`

**`ollama_facade/server.py`** — FastAPI application implementing the Ollama HTTP API:
- `POST /api/chat` and `POST /api/generate` — main request handlers
- `GET /api/tags` — advertises available models from config
- Handles streaming (NDJSON) and non-streaming responses
- Normalizes model name aliases (e.g. `sonnet` → `claude-sonnet-4-6`)
- Tool call handling: accumulates streaming `tool_call` deltas and assembles complete tool calls
- Subnet restriction middleware via `OLLAMA_ALLOWED_NETWORK`

**`ollama_facade/cli.py`** — Argument parsing and daemon lifecycle (start/stop/status/config commands). Manages PID file at `~/.ollama-facade/ollama-facade.pid`.

### Token Resolution (in `Account.get_token()`)

Checked in order:
1. Explicit `token:` in config
2. Explicit `credentials:` path in config (file format: `{"claudeAiOauth": {"accessToken": "...", "refreshToken": "...", "expiresAt": ms}}`)
3. `~/.claude/.credentials.json` as fallback

The primary intended usage is a raw `token:` in config. Token is obtained via `claude setup-token`.

### Configuration

Config file: `~/.ollama-facade/config.yaml` (or path in `OLLAMA_FACADE_CONFIG` env var).

Key fields:
- `accounts` — list of `{credentials: path}` or `{token: raw}` entries
- `ollama_port` — port to listen on (default: 11434)
- `ollama_allowed_network` — optional CIDR for network restriction
- `ollama_models` — list of models to advertise (name, context_window, max_tokens)
- `strategy` — `"priority"` (default) or `"round_robin"`
- `cooldown_seconds` — backoff after rate limit (default: 30)

### Anthropic API Details

- URL: `https://api.anthropic.com/v1/messages?beta=true`
- Auth header: `x-api-key: <oauth_token>` (not Bearer)
- Required beta: `claude-code-20250219,oauth-2025-04-20,...`
- Required header: `Anthropic-Dangerous-Direct-Browser-Access: true`
- Billing cloaking injected into system prompt (required for sonnet/opus)
- curl-cffi with `impersonate="chrome"` for correct TLS fingerprint

## Homebrew Formula Notes

`Formula/ollama-facade.rb` uses `virtualenv` isolation with Python 3.12.

Native extensions installed via post-install pip (not as resources, to avoid build failures):
- `pydantic-core` — required by pydantic 2.x
- `cffi` — required by curl-cffi
- `curl-cffi` — Chrome TLS fingerprinting

`typing-inspection` must be included as a resource (required by pydantic 2.11+).

When updating the formula for a new release:
1. Tag the release: `git tag vX.Y.Z && git push origin main --tags`
2. Get sha256: `curl -sL <tarball_url> | shasum -a 256`
3. Update `url` and `sha256` in the formula
4. Commit and push the formula change
