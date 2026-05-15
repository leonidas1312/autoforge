"""Headless jcode invocation for issue implementation."""

import json
import os
import time
from pathlib import Path

from autoforge.cli import run_cmd

_DEBUG_DIR = Path(".autoforge")
_LAST_RUN_FILE = _DEBUG_DIR / "last-run.json"

_DEFAULT_MODEL = "qwen/qwen3.6-35b-a3b"
_DEFAULT_PROVIDER = "openrouter"


def _redact_sensitive(text: str) -> str:
    """Replace OPENROUTER_API_KEY occurrences with ***REDACTED***."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return text
    return text.replace(key, "***REDACTED***")


def _tail_lines(text: str, n: int = 50) -> str:
    """Return the last N lines of *text*."""
    lines = text.splitlines()
    return "\n".join(lines[-n:])


def _write_debug(result: dict) -> None:
    """Write the raw result to .autoforge/last-run.json for debugging."""
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    _LAST_RUN_FILE.write_text(
        json.dumps(result, indent=2, default=str),
        encoding="utf-8",
    )


def invoke_jcode(
    prompt: str,
    cwd: Path,
    model: str | None = None,
    provider: str | None = None,
    timeout_seconds: int = 1800,
) -> dict:
    """Invoke jcode headlessly against a worktree.

    Builds: `jcode run --provider <p> --model <m> --cwd <path> --quiet --json
    "<prompt>"`

    Returns a dict with: exit_code, stdout_raw, stderr_tail, parsed.
    Writes a debug copy to .autoforge/last-run.json.
    """
    m = model or _DEFAULT_MODEL
    p = provider or _DEFAULT_PROVIDER

    cmd = [
        "jcode", "run",
        "--provider", p,
        "--model", m,
        "--cwd", str(cwd),
        "--quiet",
        "--json",
        prompt,
    ]

    start = time.time()
    result = run_cmd(cmd, timeout=timeout_seconds)
    elapsed = time.time() - start

    stdout_raw = result.stdout or ""
    stderr_raw = result.stderr or ""

    # Redact sensitive data
    stdout_raw = _redact_sensitive(stdout_raw)
    stderr_redacted = _redact_sensitive(stderr_raw)

    # Parse JSON if present
    parsed = None
    if stdout_raw.strip():
        try:
            parsed = json.loads(stdout_raw.strip())
        except (json.JSONDecodeError, ValueError):
            pass

    debug = {
        "exit_code": result.returncode,
        "stdout_raw": stdout_raw,
        "stderr_tail": _tail_lines(stderr_redacted),
        "parsed": parsed,
        "elapsed_seconds": round(elapsed, 2),
        "cwd": str(cwd),
        "model": m,
        "provider": p,
    }

    _write_debug(debug)

    return debug
