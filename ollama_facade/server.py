#!/usr/bin/env python3
"""Ollama-compatible HTTP facade for llm-proxy. Presents Claude Max as a local Ollama server."""

from __future__ import annotations

import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

# proxy_core lives alongside server.py in the ollama_facade package
sys.path.insert(0, str(Path(__file__).parent))

# Also support running from llm-proxy parent directory layout
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from ollama_facade import proxy_core
except ImportError:
    import proxy_core  # type: ignore
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse

app = FastAPI(title="LLM Proxy Ollama Facade")

from fastapi import Request
from fastapi.responses import JSONResponse
import ipaddress
import os

# OLLAMA_ALLOWED_NETWORK: restrict to a specific CIDR (e.g. "10.0.0.0/24").
# Unset or empty = allow all (safe when the port is already bound to 127.0.0.1 via Docker).
_ALLOWED_NET_ENV = os.environ.get("OLLAMA_ALLOWED_NETWORK", "").strip()

@app.middleware("http")
async def restrict_to_subnet(request: Request, call_next):
    if not _ALLOWED_NET_ENV:
        return await call_next(request)
    client_ip = request.client.host if request.client else ""
    try:
        ip = ipaddress.IPv4Address(client_ip)
        allowed = ipaddress.IPv4Network(_ALLOWED_NET_ENV)
        if ip not in allowed and str(ip) not in ("127.0.0.1",):
            return JSONResponse({"error": "Access denied"}, status_code=403)
    except Exception:
        return JSONResponse({"error": "Invalid client IP"}, status_code=403)
    return await call_next(request)


_OLLAMA_MODELS: list[dict] = proxy_core.CFG.get(
    "ollama_models",
    [{"name": proxy_core.DEFAULT_MODEL, "context_window": 200000, "max_tokens": 8192}],
)
_DEFAULT_MODEL: str = _OLLAMA_MODELS[0]["name"] if _OLLAMA_MODELS else proxy_core.DEFAULT_MODEL



def _normalize_model(name: str) -> str:
    """Strip :latest tags and normalize common aliases to exact Anthropic model IDs."""
    # Strip :tag suffix (e.g. "claude-sonnet-4-6:latest" -> "claude-sonnet-4-6")
    name = name.split(":")[0].strip()
    # Alias map for common variants
    # All common aliases → actual CLIProxyAPI model IDs
    aliases = {
        "claude-sonnet": "claude-sonnet-4-6",
        "sonnet": "claude-sonnet-4-6",
        "claude-3-5-sonnet": "claude-sonnet-4-6",
        "claude-3-5-sonnet-20241022": "claude-sonnet-4-6",
        "claude-3-7-sonnet-20250219": "claude-sonnet-4-6",
        "claude-sonnet-4-5": "claude-sonnet-4-6",
        "claude-sonnet-4-5-20250929": "claude-sonnet-4-6",
        "claude-sonnet-4-20250514": "claude-sonnet-4-6",
        "claude-haiku": "claude-haiku-4-5-20251001",
        "claude-haiku-4-5": "claude-haiku-4-5-20251001",
        "claude-3-haiku-20240307": "claude-haiku-4-5-20251001",
        "claude-3-5-haiku": "claude-haiku-4-5-20251001",
        "haiku": "claude-haiku-4-5-20251001",
        "claude-opus": "claude-opus-4-6",
        "opus": "claude-opus-4-6",
    }
    return aliases.get(name, name)


def _model_info(name: str) -> dict | None:
    name = _normalize_model(name)
    return next((m for m in _OLLAMA_MODELS if m["name"] == name), None)


@app.get("/")
async def root():
    return "Ollama is running"


@app.get("/api/version")
async def version():
    return {"version": "0.5.0"}


@app.get("/api/tags")
async def tags():
    now = datetime.now(timezone.utc).isoformat()
    models = [
        {
            "name": m["name"],
            "model": m["name"],
            "modified_at": now,
            "size": 0,
            "digest": "sha256:" + "0" * 64,
            "details": {
                "parent_model": "",
                "format": "gguf",
                "family": "claude",
                "families": ["claude"],
                "parameter_size": "unknown",
                "quantization_level": "unknown",
            },
        }
        for m in _OLLAMA_MODELS
    ]
    return {"models": models}


@app.get("/api/ps")
async def ps():
    now = datetime.now(timezone.utc).isoformat()
    return {
        "models": [
            {
                "name": _DEFAULT_MODEL,
                "model": _DEFAULT_MODEL,
                "size": 0,
                "digest": "sha256:" + "0" * 64,
                "details": {},
                "expires_at": "2099-01-01T00:00:00Z",
                "size_vram": 0,
            }
        ]
    }


def _convert_ollama_messages_to_openai(messages: list[dict]) -> list[dict]:
    """Assign tool_call_ids to Ollama tool result messages (Ollama omits them).
    Converts Ollama assistant tool_calls dict-arguments to JSON-string arguments.
    """
    result = []
    pending_ids: list[str] = []

    for m in messages:
        role = m.get("role")

        if role == "assistant" and m.get("tool_calls"):
            openai_tool_calls = []
            pending_ids = []
            for i, tc in enumerate(m.get("tool_calls", [])):
                fn = tc.get("function", {})
                tc_id = f"call_{abs(hash(fn.get('name', '') + str(i))):016x}"
                pending_ids.append(tc_id)
                args = fn.get("arguments", {})
                openai_tool_calls.append({
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": fn.get("name", ""),
                        "arguments": json.dumps(args) if isinstance(args, dict) else (args or "{}"),
                    },
                })
            result.append({
                "role": "assistant",
                "content": m.get("content") or None,
                "tool_calls": openai_tool_calls,
            })
        elif role == "tool":
            tc_id = pending_ids.pop(0) if pending_ids else f"call_unknown_{len(result)}"
            result.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": m.get("content", ""),
            })
        else:
            result.append(m)

    return result


async def _ollama_chat_stream(
    messages: list[dict], model: str, max_tokens: int,
    tools: list[dict] | None = None,
) -> AsyncGenerator[bytes, None]:
    """Convert proxy_core streaming chunks to Ollama NDJSON format.
    Handles both text and tool_call responses.
    """
    t0 = time.time()
    now = datetime.now(timezone.utc).isoformat()
    tool_calls_buffer: dict[int, dict] = {}  # index → {id, name, arguments}

    try:
        async for chunk in proxy_core._call_with_failover_streaming(messages, model, max_tokens, tools=tools):
            if chunk.get("error"):
                line = json.dumps({
                    "model": model,
                    "created_at": now,
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "done_reason": "error",
                    "error": chunk["error"],
                })
                yield (line + "\n").encode()
                return

            text = chunk.get("text", "")
            # Skip empty keepalive chunks — don't emit blank tokens to the client
            if text:
                line = json.dumps({
                    "model": model,
                    "created_at": now,
                    "message": {"role": "assistant", "content": text},
                    "done": False,
                })
                yield (line + "\n").encode()

            # Accumulate tool call argument deltas
            for tc in chunk.get("tool_call_deltas") or []:
                idx = tc.get("index", 0)
                if idx not in tool_calls_buffer:
                    tool_calls_buffer[idx] = {"id": tc.get("id") or "", "name": "", "arguments": ""}
                if tc.get("id"):
                    tool_calls_buffer[idx]["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    tool_calls_buffer[idx]["name"] = fn["name"]
                if fn.get("arguments"):
                    tool_calls_buffer[idx]["arguments"] += fn["arguments"]

            # When stream ends with tool_calls, emit assembled tool calls as Ollama format
            if chunk.get("finish_reason") == "tool_calls" and tool_calls_buffer:
                assembled = []
                for idx in sorted(tool_calls_buffer.keys()):
                    tc = tool_calls_buffer[idx]
                    try:
                        args_dict = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except Exception:
                        args_dict = {"_raw": tc["arguments"]}
                    assembled.append({"function": {"name": tc["name"], "arguments": args_dict}})
                line = json.dumps({
                    "model": model,
                    "created_at": now,
                    "message": {"role": "assistant", "content": "", "tool_calls": assembled},
                    "done": False,
                })
                yield (line + "\n").encode()
    except Exception as e:
        yield (json.dumps({"error": str(e), "done": True, "done_reason": "error"}) + "\n").encode()
        return

    total_ns = int((time.time() - t0) * 1_000_000_000)
    done_line = json.dumps({
        "model": model,
        "created_at": now,
        "message": {"role": "assistant", "content": ""},
        "done": True,
        "done_reason": "stop",
        "total_duration": total_ns,
        "load_duration": 0,
        "prompt_eval_count": 0,
        "prompt_eval_duration": 0,
        "eval_count": 0,
        "eval_duration": total_ns,
    })
    yield (done_line + "\n").encode()


@app.post("/api/chat")
async def chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    model = _normalize_model(body.get("model", _DEFAULT_MODEL))
    info = _model_info(model)
    if info is None:
        return JSONResponse({"error": f"model '{model}' not found"}, status_code=404)

    raw_messages = body.get("messages")
    if not raw_messages:
        return JSONResponse({"error": "messages field required"}, status_code=400)

    # Convert Ollama messages → OpenAI format (assign tool_call_ids to tool results)
    messages = _convert_ollama_messages_to_openai(raw_messages)
    tools: list[dict] | None = body.get("tools") or None
    max_tokens = body.get("options", {}).get("num_predict", info.get("max_tokens", 8192))
    stream = body.get("stream", True)

    if not stream:
        full_text = ""
        tool_calls_buffer: dict[int, dict] = {}
        try:
            async for chunk in proxy_core._call_with_failover_streaming(messages, model, max_tokens, tools=tools):
                if chunk.get("error"):
                    return JSONResponse({"error": chunk["error"]}, status_code=500)
                full_text += chunk.get("text", "")
                for tc in chunk.get("tool_call_deltas") or []:
                    idx = tc.get("index", 0)
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {"id": tc.get("id") or "", "name": "", "arguments": ""}
                    if tc.get("id"):
                        tool_calls_buffer[idx]["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        tool_calls_buffer[idx]["name"] = fn["name"]
                    if fn.get("arguments"):
                        tool_calls_buffer[idx]["arguments"] += fn["arguments"]
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=502)
        now = datetime.now(timezone.utc).isoformat()
        message: dict = {"role": "assistant", "content": full_text or ""}
        if tool_calls_buffer:
            assembled = []
            for idx in sorted(tool_calls_buffer.keys()):
                tc = tool_calls_buffer[idx]
                try:
                    args_dict = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except Exception:
                    args_dict = {"_raw": tc["arguments"]}
                assembled.append({"function": {"name": tc["name"], "arguments": args_dict}})
            message["tool_calls"] = assembled
        return {
            "model": model, "created_at": now, "message": message,
            "done": True, "done_reason": "stop",
        }

    async def _logged_stream():
        import logging
        _log = logging.getLogger("facade.debug")
        chunks = 0
        full = ""
        async for data in _ollama_chat_stream(messages, model, max_tokens, tools=tools):
            chunks += 1
            try:
                d = __import__('json').loads(data.decode().strip())
                c = d.get("message", {}).get("content", "")
                if c: full += c
                if d.get("done"):
                    _log.warning(f"DONE | chunks={chunks} len={len(full)} preview={full[:80]!r}")
            except: pass
            yield data

    return StreamingResponse(
        _logged_stream(),
        media_type="application/x-ndjson",
    )


@app.post("/api/generate")
async def generate(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    model = _normalize_model(body.get("model", _DEFAULT_MODEL))
    info = _model_info(model)
    if info is None:
        return JSONResponse({"error": f"model '{model}' not found"}, status_code=404)

    prompt = body.get("prompt", "")
    if not prompt:
        return JSONResponse({"error": "prompt field required"}, status_code=400)

    max_tokens = body.get("options", {}).get("num_predict", info.get("max_tokens", 8192))
    stream = body.get("stream", True)

    messages: list[dict] = []
    if body.get("system"):
        messages.append({"role": "system", "content": body["system"]})
    messages.append({"role": "user", "content": prompt})

    async def _generate_stream() -> AsyncGenerator[bytes, None]:
        t0 = time.time()
        now = datetime.now(timezone.utc).isoformat()
        async for chunk in proxy_core._call_with_failover_streaming(messages, model, max_tokens):
            if chunk.get("error"):
                yield (json.dumps({
                    "model": model, "created_at": now,
                    "response": "", "done": True, "error": chunk["error"],
                }) + "\n").encode()
                return
            yield (json.dumps({
                "model": model, "created_at": now,
                "response": chunk.get("text", ""), "done": False,
            }) + "\n").encode()
        total_ns = int((time.time() - t0) * 1_000_000_000)
        yield (json.dumps({
            "model": model, "created_at": now,
            "response": "", "done": True, "done_reason": "stop",
            "total_duration": total_ns,
        }) + "\n").encode()

    if not stream:
        full_text = ""
        async for chunk in proxy_core._call_with_failover_streaming(messages, model, max_tokens):
            if chunk.get("error"):
                return JSONResponse({"error": chunk["error"]}, status_code=500)
            full_text += chunk.get("text", "")
        now = datetime.now(timezone.utc).isoformat()
        return {"model": model, "created_at": now, "response": full_text, "done": True, "done_reason": "stop"}

    return StreamingResponse(_generate_stream(), media_type="application/x-ndjson")


@app.post("/api/show")
async def show(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    name = body.get("name", body.get("model", _DEFAULT_MODEL))
    info = _model_info(name)
    if info is None:
        # Try stripping tag suffix e.g. "claude-haiku-4-5:latest"
        base = name.split(":")[0]
        info = _model_info(base)
    if info is None:
        return JSONResponse({"error": f"model '{name}' not found"}, status_code=404)
    return {
        "modelfile": f"FROM {info['name']}",
        "parameters": "",
        "template": "{{ .Prompt }}",
        "details": {
            "parent_model": "",
            "format": "gguf",
            "family": "claude",
            "families": ["claude"],
            "parameter_size": "unknown",
            "quantization_level": "unknown",
        },
        "model_info": {
            "general.architecture": "claude",
            "llama.context_length": info.get("context_window", 200000),
        },
    }


if __name__ == "__main__":
    import uvicorn
    port = proxy_core.CFG.get("ollama_port", 11434)
    uvicorn.run(app, host="0.0.0.0", port=port)
