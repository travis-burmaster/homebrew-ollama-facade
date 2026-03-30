# ollama-facade

Run **Claude Max as a local Ollama server** on your network. Any Ollama-compatible client — Cursor, Open WebUI, Claude Code, LangChain — can talk to Claude sonnet/opus/haiku through a single endpoint, routed through your existing Claude Max subscription.

No API keys. No per-token billing. Just your subscription, available everywhere on your network.

---

## Install via Homebrew

```bash
brew tap travis-burmaster/ollama-facade
brew install ollama-facade
```

## Quick Start

```bash
# Create default config
ollama-facade config --init

# Edit config — point at your claude-oauth-proxy backend
nano ~/.ollama-facade/config.yaml

# Start (foreground)
ollama-facade start

# Or start as a background daemon
ollama-facade start --daemon

# Check status
ollama-facade status

# Stop daemon
ollama-facade stop
```

## Homebrew Service (macOS launchd)

```bash
brew services start ollama-facade
brew services stop ollama-facade
```

---

## Configuration

Config lives at `~/.ollama-facade/config.yaml`:

```yaml
# Backend — point at claude-oauth-proxy or any OpenAI-compatible endpoint
primary_url: "http://127.0.0.1:8319/v1"
secondary_url: null   # optional failover

# Port for the Ollama-compatible API
ollama_port: 11434

# Restrict to your local subnet (recommended)
ollama_allowed_network: "10.0.0.0/24"

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

### curl test

```bash
curl http://localhost:11434/api/tags
curl -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"hello"}]}'
```

---

## How It Works

```
Your clients (Cursor, OpenClaw, Open WebUI)
         │  Ollama protocol
         ▼
  ollama-facade :11434
         │  OpenAI /v1/messages
         ▼
  claude-oauth-proxy :8319
         │  Chrome TLS + OAuth token
         ▼
  api.anthropic.com
         │
         ▼
  Claude sonnet / opus / haiku
```

`ollama-facade` speaks the Ollama protocol. Behind it, [`claude-oauth-proxy`](https://github.com/travis-burmaster/claude-oauth-proxy) handles authentication using your Claude Max OAuth token with Chrome TLS fingerprinting — the same mechanism that makes the official Claude Code client work.

---

## Backend: claude-oauth-proxy

ollama-facade is the Ollama-protocol frontend. For the authentication backend, see:

**[travis-burmaster/claude-oauth-proxy](https://github.com/travis-burmaster/claude-oauth-proxy)**

That repo handles:
- OAuth token reading + auto-refresh
- Chrome TLS impersonation via `curl-cffi`
- Multi-account pooling with rate limit failover
- Subnet restriction

Install both for the full stack, or point `primary_url` at any existing OpenAI-compatible endpoint.

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
pip install ollama-facade

# Create service
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
- A running [claude-oauth-proxy](https://github.com/travis-burmaster/claude-oauth-proxy) or any OpenAI-compatible backend

---

## License

MIT — Travis Burmaster
