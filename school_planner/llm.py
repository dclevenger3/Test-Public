"""Thin wrapper around the Anthropic SDK used by extract.py and study_guide.py."""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic

DEFAULT_MODEL = "claude-opus-5"
# Server-side refusal fallback: if the model declines, the API re-runs on Anthropic's
# recommended substitute inside the same call. Set SCHOOL_PLANNER_NO_FALLBACK=1 to turn off.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


def client() -> anthropic.Anthropic:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit("ANTHROPIC_API_KEY is not set. Put it in .env (see .env.example).")
    return anthropic.Anthropic()


def _fallback_kwargs() -> dict[str, Any]:
    if os.environ.get("SCHOOL_PLANNER_NO_FALLBACK"):
        return {}
    return {"betas": [_FALLBACK_BETA], "fallbacks": "default"}


def _check_refusal(message) -> None:
    if message.stop_reason == "refusal":
        detail = getattr(message, "stop_details", None)
        raise RuntimeError(f"Claude declined this request: {detail}")


def generate_text(system: str, user: str, model: str = DEFAULT_MODEL, effort: str = "high",
                  max_tokens: int = 32_000) -> str:
    """Streamed long-form generation (study guides). System prompt is cached across calls."""
    c = client()
    with c.beta.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        **_fallback_kwargs(),
    ) as stream:
        message = stream.get_final_message()
    _check_refusal(message)
    return "".join(b.text for b in message.content if b.type == "text")


def generate_json(system: str, user: str, schema: dict, model: str = DEFAULT_MODEL,
                  effort: str = "medium", max_tokens: int = 16_000) -> Any:
    """Structured extraction: the response is guaranteed to match `schema`."""
    c = client()
    message = c.beta.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        thinking={"type": "adaptive"},
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        **_fallback_kwargs(),
    )
    _check_refusal(message)
    text = next(b.text for b in message.content if b.type == "text")
    return json.loads(text)
