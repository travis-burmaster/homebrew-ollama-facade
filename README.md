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
# 1. Authenticate with Claude (creates ~/.claude/.credentials.json)
claude setup-token

# 2. Create default config
ollama-facade config --init

# 3. Start as a background service
brew services start ollama-facade

# 4. Test it
curl http://localhost:11434/
# → "Ollama is running"

curl -s http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"say hi"}],"stream":false}'
```

## Homebrew Service (macOS launchd)

```bash
brew services start ollama-facade
brew services stop ollama-facade
brew services restart ollama-facade
```

---

## Authentication

ollama-facade reads your Claude Max OAuth token from `~/.claude/.credentials.json`. Run the following once to create it:

```bash
claude setup-token
```

This opens a browser where you log into claude.ai with your Claude Max subscription. The token is stored locally and auto-refreshes — you only need to do this once.

**If you don't have the Claude CLI installed:**
```bash
brew install claude   # or: npm install -g @anthropic-ai/claude-code
claude setup-token
```

**Explicit credentials path** (if your file is in a non-default location):
```yaml
accounts:
  - credentials: "/path/to/.credentials.json"
```

**Raw token** (expires, no auto-refresh — not recommended):
```yaml
accounts:
  - token: "sk-ant-oat01-..."
```

**Multi-account setup** (multiply your rate limits):
```yaml
accounts:
  - credentials: "~/.claude/.credentials.json"
  - name: "Account 2"
    credentials: "~/.claude2/.credentials.json"
```

After updating the config, restart the service:
```bash
brew services restart ollama-facade
```

---

## Configuration

Config lives at `~/.ollama-facade/config.yaml`:

```yaml
# Claude accounts — credentials file written by 'claude setup-token'
accounts:
  - credentials: "~/.claude/.credentials.json"
  # - name: "Account 2"
  #   credentials: "~/.claude2/.credentials.json"

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
| `"no token available"` | `~/.claude/.credentials.json` not found | Run `claude setup-token` |
| `"Config not found"` | Config file missing | Run `ollama-facade config --init` |
| `"Anthropic API error 401"` | OAuth token expired and refresh failed | Re-run `claude setup-token` |
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
- A Claude Max subscription authenticated via `claude setup-token`
- `curl-cffi` (installed automatically via Homebrew or pip)

---

## License

MIT — Travis Burmaster
