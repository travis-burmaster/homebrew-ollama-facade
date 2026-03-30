# ollama-facade

Run **Claude Max as a local Ollama server** on your network. Any Ollama-compatible client — Cursor, Open WebUI, Claude Code, LangChain — can talk to Claude sonnet/opus/haiku through a single endpoint, using your existing Claude Max subscription.

No API keys. No per-token billing. No external proxy. Just your subscription, available everywhere on your network.

---

## Install via Homebrew

```bash
brew tap travis-burmaster/ollama-facade
brew install ollama-facade
```

## Quick Start

```bash
# 1. Create default config
ollama-facade config --init

# 2. Start as a background service
brew services start ollama-facade

# 3. Test it
curl http://localhost:11434/
# → "Ollama is running"

curl -s http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"say hi"}],"stream":false}'
```

Token is auto-detected — see [Authentication](#authentication) below.

## Homebrew Service (macOS launchd)

```bash
brew services start ollama-facade
brew services stop ollama-facade
brew services restart ollama-facade
```

---

## Authentication

ollama-facade auto-detects your Claude OAuth token from these locations, in order:

1. **`~/.cli-proxy-api/<email>.json`** — written by [cliproxyapi](https://github.com/travis-burmaster/cliproxyapi) or the Claude CLI. **If you use Claude Code, this file already exists.**
2. **`~/.claude/.credentials.json`** — written by `claude setup-token`
3. **Explicit path or token** in `~/.ollama-facade/config.yaml`

No extra setup needed if you already have Claude Code or cliproxyapi installed. Tokens auto-refresh when they expire.

**If you need to create a token from scratch:**
```bash
brew install claude   # or: npm install -g @anthropic-ai/claude-code
claude setup-token
```

**Explicit config** (if auto-detection doesn't find your token):
```yaml
accounts:
  - credentials: "~/.cli-proxy-api/you@example.com.json"
  # or:
  # - credentials: "~/.claude/.credentials.json"
  # or raw token (expires, no auto-refresh):
  # - token: "sk-ant-oat01-..."
```

**Multi-account setup** (multiply your rate limits):
```yaml
accounts:
  - credentials: "~/.cli-proxy-api/account1@example.com.json"
  - credentials: "~/.cli-proxy-api/account2@example.com.json"
```

After updating the config, restart the service:
```bash
brew services restart ollama-facade
```

---

## Configuration

Config lives at `~/.ollama-facade/config.yaml`:

```yaml
# Claude accounts — auto-detected if not specified
accounts:
  - credentials: "~/.cli-proxy-api/you@example.com.json"

# Port for the Ollama-compatible API
ollama_port: 11434

# Restrict to your local subnet (recommended)
# ollama_allowed_network: "10.0.0.0/24"

# Failover strategy: "priority" or "round_robin"
strategy: "priority"

# Cooldown seconds after a rate-limit error
cooldown_seconds: 30

# Models to expose
ollama_models:
  - name: "claude-sonnet-4-6"
    context_window: 200000
    max_tokens: 8192
  - name: "claude-opus-4-6"
    context_window: 200000
    max_tokens: 8192
  - name: "claude-haiku-4-5-20251001"
    context_window: 200000
    max_tokens: 8192
```

---

## Connect Your Clients

### OpenClaw / any Ollama client

```json
{
  "api": "ollama",
  "baseUrl": "http://YOUR_SERVER_IP:11434",
  "models": [
    { "id": "claude-sonnet-4-6" },
    { "id": "claude-opus-4-6" }
  ]
}
```

### curl tests

Health check (no credentials required):
```bash
curl http://localhost:11434/
# → "Ollama is running"

curl http://localhost:11434/api/version
# → {"version":"0.5.0"}

curl http://localhost:11434/api/tags
# → {"models":[{"name":"claude-sonnet-4-6",...},{"name":"claude-opus-4-6",...}]}
```

Chat:
```bash
# Non-streaming
curl -s http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "say hi"}],
    "stream": false
  }'

# Streaming (default)
curl -s http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "say hi"}]
  }'
```

**Common errors:**

| Error | Cause | Fix |
|---|---|---|
| `"no token available"` | No credentials found | Check `~/.cli-proxy-api/` or run `claude setup-token` |
| `"Config not found"` | Config file missing | Run `ollama-facade config --init` |
| `"Anthropic API error 401"` | OAuth token expired and refresh failed | Restart service (triggers refresh); or re-run `claude setup-token` |
| `"Anthropic API error 429"` | Rate limited | Wait for cooldown (configurable via `cooldown_seconds`) |
| `"All accounts exhausted"` | All accounts rate-limited | Add more accounts to the `accounts:` list in config |

---

## How It Works

```
Your clients (Cursor, OpenClaw, Open WebUI)
         │  Ollama protocol
         ▼
  ollama-facade :11434
         │  Anthropic /v1/messages
         │  Chrome TLS + OAuth token
         ▼
  api.anthropic.com
         │
         ▼
  Claude sonnet / opus / haiku
```

ollama-facade speaks the Ollama protocol and calls the Anthropic API directly using your Claude Max OAuth token with Chrome TLS fingerprinting — the same mechanism that makes the official Claude Code client work. No intermediate proxy required.

Token sources checked in order:
- `~/.cli-proxy-api/<email>.json` (cliproxyapi / Claude CLI)
- `~/.claude/.credentials.json` (claude setup-token)
- Explicit `credentials:` or `token:` in config

---

## Development

The system Python on macOS is too old (3.9). Use a virtualenv with Homebrew Python 3.12+:

```bash
git clone https://github.com/travis-burmaster/homebrew-ollama-facade
cd homebrew-ollama-facade

python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .

ollama-facade config --init
ollama-facade start
```

---

## Linux (systemd)

```bash
pip install curl-cffi pyyaml fastapi uvicorn
pip install ollama-facade

cat > ~/.config/systemd/user/ollama-facade.service << EOF
[Unit]
Description=Ollama Facade — Claude Max as Ollama server
After=network.target

[Service]
ExecStart=ollama-facade start
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user enable --now ollama-facade
```

---

## Requirements

- Python 3.10+
- A Claude Max subscription with an OAuth token in `~/.cli-proxy-api/` or `~/.claude/.credentials.json`
- `curl-cffi` (installed automatically via Homebrew or pip)

---

## License

MIT — Travis Burmaster
