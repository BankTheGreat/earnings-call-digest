"""llm_client.py — a small multi-vendor LLM adapter (one swap point).

Provider-neutral by construction: ZERO third-party LLM dependencies (only
httpx + stdlib). Covers Anthropic, Gemini, and OpenAI (plus any
OpenAI-compatible vendor) behind one `complete()` call with a unified response
shape, plus `calc_cost()` for a rough per-call cost estimate.

Usage:
    from earnings_digest.llm_client import complete
    r = complete("gemini", [{"role": "user", "content": "Hello"}])
    print(r.text, r.cost_usd, r.usage)

The API key for each vendor is read from that vendor's own environment variable
(ANTHROPIC_API_KEY / GEMINI_API_KEY / OPENAI_API_KEY) — never a function
argument, never logged, and (for Gemini) sent in a header, never the URL.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Iterator, Literal, Optional

import httpx

# =============================================================================
# Vendor configuration
# =============================================================================

@dataclass
class VendorConfig:
    name: Literal["anthropic", "gemini", "openai"]
    base_url: str
    api_key_env: str
    default_model: str
    extra_headers: dict[str, str] = field(default_factory=dict)
    api_shape: Literal["anthropic", "gemini", "openai"] = "openai"


VENDORS: dict[str, VendorConfig] = {
    "anthropic": VendorConfig(
        name="anthropic",
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        default_model="claude-opus-4-7",
        extra_headers={"anthropic-version": "2023-06-01"},
        api_shape="anthropic",
    ),
    "gemini": VendorConfig(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key_env="GEMINI_API_KEY",
        default_model="gemini-2.5-pro",
        api_shape="gemini",
    ),
    "openai": VendorConfig(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        default_model="gpt-5",
        api_shape="openai",
    ),
}

# =============================================================================
# Unified response shape
# =============================================================================

@dataclass
class LLMResponse:
    """Vendor-agnostic response. Same shape across Anthropic, Gemini, OpenAI."""
    text: str
    usage: dict[str, int]      # {input_tokens, output_tokens, cache_read_tokens}
    cost_usd: float
    vendor: str
    model: str
    raw: dict[str, Any]
    thinking: Optional[str] = None      # Extended-thinking trace if present
    tool_calls: list[dict] = field(default_factory=list)


# =============================================================================
# Cost catalog — refresh per validity_horizon (180 days)
# Per-million-token rates · 2026-08-04 snapshot (Anthropic per claude-api skill
# reference cached 2026-06-24; Gemini per ai.google.dev/gemini-api/docs/pricing
# fetched 2026-08-04). Sonnet 5 uses sticker rates (intro $2/$10 runs through
# 2026-08-31 — estimates here are conservative).
# =============================================================================

COST_CATALOG: dict[str, dict[str, float]] = {
    "claude-fable-5":     {"in": 10.00, "cache_read": 1.00,     "out": 50.00},
    "claude-opus-5":      {"in":  5.00, "cache_read": 0.50,     "out": 25.00},
    "claude-sonnet-5":    {"in":  3.00, "cache_read": 0.30,     "out": 15.00},
    "claude-opus-4-7":    {"in":  5.00, "cache_read": 0.50,     "out": 25.00},
    "claude-sonnet-4-6":  {"in":  3.00, "cache_read": 0.30,     "out": 15.00},
    "claude-haiku-4-5":   {"in":  1.00, "cache_read": 0.10,     "out":  5.00},
    "gemini-2.5-pro":     {"in":  1.25, "cache_read": 0.31,     "out": 10.00},
    # Flash cache-read discount unverified — billed as input here (conservative).
    "gemini-2.5-flash":   {"in":  0.30, "cache_read": 0.30,     "out":  2.50},
    "gpt-5":              {"in":  2.50, "cache_read": 0.25,     "out": 10.00},
}

def calc_cost(model: str, usage: dict[str, int]) -> float:
    rates = COST_CATALOG.get(model, {"in": 0.0, "cache_read": 0.0, "out": 0.0})
    cache_rate = rates.get("cache_read", rates["in"])
    return (
        usage.get("input_tokens", 0)      * rates["in"]   / 1_000_000
        + usage.get("cache_read_tokens", 0) * cache_rate    / 1_000_000
        + usage.get("output_tokens", 0)     * rates["out"]  / 1_000_000
    )


# =============================================================================
# Per-vendor request shapers (private)
# =============================================================================

def _anthropic_payload(model, messages, tools, thinking_budget, max_tokens):
    payload: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if tools:
        payload["tools"] = tools
    if thinking_budget:
        payload["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
    return payload

def _gemini_payload(model, messages, tools, thinking_budget, max_tokens):
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        if isinstance(m["content"], str):
            text = m["content"]
        else:
            text = "\n".join(b.get("text", "") for b in m["content"] if b.get("type") == "text")
        contents.append({"role": role, "parts": [{"text": text}]})
    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if tools:
        payload["tools"] = [{"functionDeclarations": tools}]
    if thinking_budget:
        payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": thinking_budget}
    return payload

def _openai_payload(model, messages, tools, thinking_budget, max_tokens):
    flat = []
    for m in messages:
        if isinstance(m["content"], str):
            flat.append({"role": m["role"], "content": m["content"]})
        else:
            text = "\n".join(b.get("text", "") for b in m["content"] if b.get("type") == "text")
            flat.append({"role": m["role"], "content": text})
    payload: dict[str, Any] = {"model": model, "messages": flat, "max_tokens": max_tokens}
    if tools:
        payload["tools"] = [{"type": "function", "function": t} for t in tools]
    if thinking_budget:
        payload["reasoning_effort"] = "high"
    return payload

# =============================================================================
# Per-vendor response parsers (private)
# =============================================================================

def _anthropic_parse(raw, model):
    text_parts, thinking_parts, tool_calls = [], [], []
    for blk in raw.get("content", []):
        t = blk.get("type")
        if t == "text":
            text_parts.append(blk.get("text", ""))
        elif t == "thinking":
            thinking_parts.append(blk.get("thinking", ""))
        elif t == "tool_use":
            tool_calls.append({"name": blk["name"], "args": blk["input"], "id": blk["id"]})
    usage = raw.get("usage", {})
    norm = {
        "input_tokens":      usage.get("input_tokens", 0),
        "output_tokens":     usage.get("output_tokens", 0),
        "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
    }
    return LLMResponse(
        text="".join(text_parts), usage=norm, cost_usd=calc_cost(model, norm),
        vendor="anthropic", model=model, raw=raw,
        thinking=("\n".join(thinking_parts) or None), tool_calls=tool_calls,
    )

def _gemini_parse(raw, model):
    text, tool_calls = "", []
    for cand in raw.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            if "text" in part:
                text += part["text"]
            if "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append({"name": fc.get("name", ""), "args": fc.get("args", {}), "id": ""})
    usage = raw.get("usageMetadata", {})
    norm = {
        "input_tokens":      usage.get("promptTokenCount", 0),
        "output_tokens":     usage.get("candidatesTokenCount", 0),
        "cache_read_tokens": usage.get("cachedContentTokenCount", 0),
    }
    return LLMResponse(
        text=text, usage=norm, cost_usd=calc_cost(model, norm),
        vendor="gemini", model=model, raw=raw, tool_calls=tool_calls,
    )

def _openai_parse(raw, model):
    msg = raw["choices"][0]["message"]
    tool_calls = []
    for tc in (msg.get("tool_calls") or []):
        try:
            args = json.loads(tc["function"]["arguments"])
        except (json.JSONDecodeError, KeyError):
            args = {}
        tool_calls.append({"name": tc["function"]["name"], "args": args, "id": tc["id"]})
    usage = raw.get("usage", {})
    cache_read = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
    norm = {
        "input_tokens":      usage.get("prompt_tokens", 0) - cache_read,
        "output_tokens":     usage.get("completion_tokens", 0),
        "cache_read_tokens": cache_read,
    }
    return LLMResponse(
        text=(msg.get("content") or ""), usage=norm, cost_usd=calc_cost(model, norm),
        vendor="openai", model=model, raw=raw, tool_calls=tool_calls,
    )

# =============================================================================
# Public API — the single swap point across vendors
# =============================================================================

def complete(
    vendor: str,
    messages: list[dict],
    *,
    model: Optional[str] = None,
    tools: Optional[list[dict]] = None,
    thinking_budget: Optional[int] = None,
    max_tokens: int = 4096,
    timeout: float = 120.0,
) -> LLMResponse:
    """Non-streaming completion. Returns vendor-agnostic LLMResponse.

    Args:
        vendor: "anthropic" | "gemini" | "openai"
        messages: list of {"role": "user|assistant|system", "content": str | [blocks]}
                  Anthropic blocks may include {"type":"text","text":"...",
                  "cache_control":{"type":"ephemeral"}} for prompt caching.
        model: override default; if None uses VENDORS[vendor].default_model
        tools: list of tool spec dicts in vendor-neutral schema:
               [{"name": "...", "description": "...", "input_schema": {...}}]
               (Anthropic-style; auto-translated for Gemini/OpenAI.)
        thinking_budget: integer token budget for extended-thinking
                         (Anthropic native; Gemini thinkingBudget; OpenAI reasoning_effort=high).
        max_tokens: output cap.
    """
    if vendor not in VENDORS:
        raise ValueError(f"Unknown vendor: {vendor}. Options: {list(VENDORS)}")
    cfg = VENDORS[vendor]
    api_key = os.environ.get(cfg.api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing env var {cfg.api_key_env} for vendor {vendor}")
    model = model or cfg.default_model

    if cfg.api_shape == "anthropic":
        url = f"{cfg.base_url}/messages"
        headers = {"x-api-key": api_key, "content-type": "application/json", **cfg.extra_headers}
        payload = _anthropic_payload(model, messages, tools, thinking_budget, max_tokens)
        parser = _anthropic_parse
    elif cfg.api_shape == "gemini":
        # Key rides in the x-goog-api-key HEADER, never the URL query string —
        # URLs leak into tracebacks, proxy logs, and httpx error text.
        url = f"{cfg.base_url}/models/{model}:generateContent"
        headers = {"content-type": "application/json", "x-goog-api-key": api_key}
        payload = _gemini_payload(model, messages, tools, thinking_budget, max_tokens)
        parser = _gemini_parse
    else:  # openai-shape (OpenAI + any OpenAI-compatible vendor)
        url = f"{cfg.base_url}/chat/completions"
        headers = {"authorization": f"Bearer {api_key}", "content-type": "application/json"}
        payload = _openai_payload(model, messages, tools, thinking_budget, max_tokens)
        parser = _openai_parse

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=payload)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Redact the URL from the surfaced error — query strings and paths
            # must never reach logs via exception text.
            # KEEP the vendor's reason though (2026-08-05 lesson: a bare
            # "429 (URL redacted)" hid "prepayment credits are depleted" and
            # cost a day of wrong quota theories). The JSON error.message is
            # secret-free by construction; scrub key-shaped runs as a belt.
            reason = ""
            try:
                msg = exc.response.json().get("error", {}).get("message", "")
                reason = re.sub(r"\bAIza[0-9A-Za-z_\-]{35}\b", "[REDACTED]", str(msg))[:180]
            except Exception:  # noqa: BLE001 — reason is best-effort only
                reason = ""
            raise RuntimeError(
                f"{vendor} API error HTTP {exc.response.status_code} "
                f"for model {model} (URL redacted)"
                + (f" — {reason}" if reason else "")
            ) from None
        parsed = parser(resp.json(), model)
        # Vendor field reflects the actual provider, not the wire shape.
        parsed.vendor = vendor
        return parsed


def stream(
    vendor: str,
    messages: list[dict],
    *,
    model: Optional[str] = None,
    tools: Optional[list[dict]] = None,
    thinking_budget: Optional[int] = None,
    max_tokens: int = 4096,
    timeout: float = 120.0,
) -> Iterator[str]:
    """Streaming completion. Yields plain text chunks. Vendor SSE differences are
    normalized so callers always see a stream of strings to concatenate."""
    if vendor not in VENDORS:
        raise ValueError(f"Unknown vendor: {vendor}")
    cfg = VENDORS[vendor]
    api_key = os.environ[cfg.api_key_env]
    model = model or cfg.default_model

    if cfg.api_shape == "anthropic":
        url = f"{cfg.base_url}/messages"
        headers = {"x-api-key": api_key, "content-type": "application/json", **cfg.extra_headers}
        payload = _anthropic_payload(model, messages, tools, thinking_budget, max_tokens)
        payload["stream"] = True
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=timeout) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if not data:
                    continue
                try:
                    ev = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if ev.get("type") == "content_block_delta":
                    delta = ev.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield delta["text"]
    elif cfg.api_shape == "openai":
        url = f"{cfg.base_url}/chat/completions"
        headers = {"authorization": f"Bearer {api_key}", "content-type": "application/json"}
        payload = _openai_payload(model, messages, tools, thinking_budget, max_tokens)
        payload["stream"] = True
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=timeout) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    ev = json.loads(data)
                except json.JSONDecodeError:
                    continue
                chunk = ev.get("choices", [{}])[0].get("delta", {}).get("content")
                if chunk:
                    yield chunk
    else:  # gemini
        # Key in header, never the URL (see complete()).
        url = f"{cfg.base_url}/models/{model}:streamGenerateContent?alt=sse"
        headers = {"content-type": "application/json", "x-goog-api-key": api_key}
        payload = _gemini_payload(model, messages, tools, thinking_budget, max_tokens)
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=timeout) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if not data:
                    continue
                try:
                    ev = json.loads(data)
                except json.JSONDecodeError:
                    continue
                for cand in ev.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        if "text" in part:
                            yield part["text"]


# =============================================================================
# CLI smoke test — `python llm_client.py <vendor>`
# =============================================================================

if __name__ == "__main__":
    vendor = sys.argv[1] if len(sys.argv) > 1 else "anthropic"
    print(f"[{vendor}] smoke test — sending PONG probe...")
    r = complete(vendor, [{"role": "user", "content": "Reply with exactly the word PONG."}], max_tokens=10)
    print(f"  text:   {r.text!r}")
    print(f"  model:  {r.model}")
    print(f"  usage:  {r.usage}")
    print(f"  cost:   ${r.cost_usd:.6f}")
    print(f"  pass:   {'PONG' in r.text.upper()}")
