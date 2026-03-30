#!/usr/bin/env python3
"""
ollama-facade CLI
Usage:
  ollama-facade start           # start server (foreground)
  ollama-facade start --daemon  # start as background daemon
  ollama-facade stop            # stop daemon
  ollama-facade status          # show running status
  ollama-facade config          # print config path and current settings
  ollama-facade config --init   # create default config.yaml
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path


CONFIG_DIR  = Path.home() / ".ollama-facade"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
PID_FILE    = CONFIG_DIR / "ollama-facade.pid"
LOG_FILE    = CONFIG_DIR / "ollama-facade.log"

DEFAULT_CONFIG = """\
# ollama-facade config
# Proxy backend — point this at claude-oauth-proxy or any OpenAI-compatible endpoint
primary_url: "http://127.0.0.1:8319/v1"
secondary_url: null

# Port to expose Ollama-compatible API (default: 11434)
ollama_port: 11434

# Restrict access to subnet (comment out to allow all)
# ollama_allowed_network: "10.0.0.0/24"

# Default model
default_model: "claude-sonnet-4-6"

# Models to advertise via /api/tags
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
"""


def cmd_start(args):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(DEFAULT_CONFIG)
        print(f"Created default config at {CONFIG_FILE}")

    server_module = Path(__file__).parent / "server.py"
    env = os.environ.copy()
    env["OLLAMA_FACADE_CONFIG"] = str(CONFIG_FILE)

    if args.daemon:
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            try:
                os.kill(pid, 0)
                print(f"ollama-facade already running (PID {pid})")
                return
            except ProcessLookupError:
                PID_FILE.unlink(missing_ok=True)

        log = open(LOG_FILE, "a")
        proc = subprocess.Popen(
            [sys.executable, str(server_module)],
            env=env, stdout=log, stderr=log,
            start_new_session=True,
        )
        PID_FILE.write_text(str(proc.pid))
        print(f"ollama-facade started (PID {proc.pid})")
        print(f"Logs: {LOG_FILE}")
        print(f"Stop: ollama-facade stop")
    else:
        try:
            subprocess.run([sys.executable, str(server_module)], env=env)
        except KeyboardInterrupt:
            print("\nStopped.")


def cmd_stop(_args):
    if not PID_FILE.exists():
        print("ollama-facade is not running (no PID file)")
        return
    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink(missing_ok=True)
        print(f"Stopped ollama-facade (PID {pid})")
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        print(f"Process {pid} not found (already stopped)")


def cmd_status(_args):
    if not PID_FILE.exists():
        print("ollama-facade: stopped")
        return
    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, 0)
        cfg = CONFIG_FILE.read_text() if CONFIG_FILE.exists() else ""
        port = 11434
        for line in cfg.splitlines():
            if line.startswith("ollama_port:"):
                port = int(line.split(":")[-1].strip())
        print(f"ollama-facade: running (PID {pid})")
        print(f"Endpoint:  http://localhost:{port}")
        print(f"Config:    {CONFIG_FILE}")
        print(f"Log:       {LOG_FILE}")
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        print("ollama-facade: stopped (stale PID file removed)")


def cmd_config(args):
    if args.init:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            print(f"Config already exists at {CONFIG_FILE}")
        else:
            CONFIG_FILE.write_text(DEFAULT_CONFIG)
            print(f"Created {CONFIG_FILE}")
        return
    print(f"Config path: {CONFIG_FILE}")
    if CONFIG_FILE.exists():
        print(CONFIG_FILE.read_text())
    else:
        print("(no config file — run: ollama-facade config init)")


def main():
    parser = argparse.ArgumentParser(
        prog="ollama-facade",
        description="Run Claude Max as a local Ollama server",
    )
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="Start the server")
    p_start.add_argument("--daemon", "-d", action="store_true", help="Run in background")

    sub.add_parser("stop", help="Stop the background daemon")
    sub.add_parser("status", help="Show running status")

    p_cfg = sub.add_parser("config", help="Show or init config")
    p_cfg.add_argument("--init", action="store_true", help="Create default config.yaml")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "config":
        cmd_config(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
