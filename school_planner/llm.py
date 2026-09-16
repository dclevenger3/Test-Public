"""Claude access for extract.py and study_guide.py.

Two backends:

  claude-code (default)  Runs the `claude` command-line tool in print mode. Uses whatever login
                         your Claude Code already has (your Claude subscription). No API key.
  api                    Uses the Anthropic SDK with ANTHROPIC_API_KEY. Pay-as-you-go.

Pick with `backend:` in config.yaml. Model names: for claude-code use an alias (opus, sonnet,
haiku) or a full id; for api use a full id such as claude-opus-5.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

DEFAULT_BACKEND = "claude-code"
DEFAULT_MODEL = "opus"
_ALIAS_TO_ID = {"opus": "claude-opus-5", "sonnet": "claude-sonnet-5", "haiku": "claude-haiku-4-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
CLI_TIMEOUT_S = 20 * 60


class LLMError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- claude-code

def claude_bin() -> str:
    path = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or shutil.which("claude.cmd")
    if not path:
        raise SystemExit(
            "Could not find the `claude` command. Install Claude Code (https://code.claude.com) and log in,\n"
            "or set backend: api in config.yaml and put ANTHROPIC_API_KEY in .env."
        )
    return path


def _run_claude(system: str, user: str, model: str, effort: str, schema: dict | None) -> dict[str, Any]:
    cmd = [
        claude_bin(), "-p",
        "--output-format", "json",
        "--no-session-persistence",
        "--max-turns", "1",
        "--tools", "",                 # pure generation: no file or shell access
        "--model", model,
        "--effort", effort,
        "--system-prompt", system,
    ]
    if schema is not None:
        cmd += ["--json-schema", json.dumps(schema)]
    try:
        proc = subprocess.run(cmd, input=user, text=True, capture_output=True, timeout=CLI_TIMEOUT_S, encoding="utf-8")
    except subprocess.TimeoutExpired as exc:
        raise LLMError(f"claude did not finish within {CLI_TIMEOUT_S // 60} minutes") from exc
    if proc.returncode != 0 and not proc.stdout.strip():
        raise LLMError(f"claude exited with {proc.returncode}: {proc.stderr.strip()[:500]}")
    try:
        env = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise LLMError(f"unexpected output from claude: {proc.stdout[:300]}") from exc
    if env.get("is_error") or env.get("subtype") not in (None, "success"):
        raise LLMError(f"claude reported an error: {env.get('result') or env.get('subtype')}")
    return env


# ----------------------------------------------------------------------------- api

def _api_client():
    import anthropic

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit("backend: api needs ANTHROPIC_API_KEY in .env (see .env.example).")
    return anthropic.Anthropic()


def _api_kwargs(system: str, user: str, model: str, effort: str, max_tokens: int) -> dict[str, Any]:
    kw: dict[str, Any] = dict(
        model=_ALIAS_TO_ID.get(model, model),
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
    )
    if not os.environ.get("SCHOOL_PLANNER_NO_FALLBACK"):
        # If the model declines for policy reasons, the API re-runs on Anthropic's recommended substitute.
        kw["betas"], kw["fallbacks"] = [_FALLBACK_BETA], "default"
    return kw


def _api_check(message) -> None:
    if message.stop_reason == "refusal":
        raise LLMError(f"Claude declined this request: {getattr(message, 'stop_details', None)}")


# ----------------------------------------------------------------------------- public

def generate_text(system: str, user: str, model: str = DEFAULT_MODEL, effort: str = "high",
                  backend: str = DEFAULT_BACKEND, max_tokens: int = 32_000) -> str:
    """Long-form generation (study guides)."""
    if backend == "claude-code":
        return _run_claude(system, user, model, effort, None).get("result", "")
    c = _api_client()
    with c.beta.messages.stream(**_api_kwargs(system, user, model, effort, max_tokens)) as stream:
        message = stream.get_final_message()
    _api_check(message)
    return "".join(b.text for b in message.content if b.type == "text")


def generate_json(system: str, user: str, schema: dict, model: str = DEFAULT_MODEL, effort: str = "medium",
                  backend: str = DEFAULT_BACKEND, max_tokens: int = 16_000) -> Any:
    """Structured extraction; the result matches `schema`."""
    if backend == "claude-code":
        env = _run_claude(system, user, model, effort, schema)
        if "structured_output" in env and env["structured_output"] is not None:
            return env["structured_output"]
        return json.loads(env.get("result", "{}"))
    c = _api_client()
    kw = _api_kwargs(system, user, model, effort, max_tokens)
    kw["output_config"]["format"] = {"type": "json_schema", "schema": schema}
    message = c.beta.messages.create(**kw)
    _api_check(message)
    return json.loads(next(b.text for b in message.content if b.type == "text"))
