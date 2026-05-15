"""Prompt builder for issue implementation tasks."""

from pathlib import Path

_WORKFLOW_PATH = Path("WORKFLOW.md")


def load_workflow_md(repo_root: Path) -> str:
    """Read WORKFLOW.md from the repository root.

    Raises FileNotFoundError with a clear message if the file is missing.
    """
    path = repo_root / _WORKFLOW_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"{_WORKFLOW_PATH} not found at {path}. "
            "Cannot build prompt without workflow rules."
        )
    return path.read_text(encoding="utf-8")


def build_prompt(issue: dict, workflow_md: str) -> str:
    """Build the implementation prompt from an issue dict and workflow contents.

    The issue dict must have at least: number, title, body.
    """
    num = issue["number"]
    title = issue["title"]
    body = issue.get("body") or ""

    return (
        f"# Implementation Task - Issue #{num}: {title}\n"
        f"\n"
        f"## Issue Description\n"
        f"{body}\n"
        f"\n"
        f"## Working Rules\n"
        f"{workflow_md}\n"
        f"\n"
        f"## Acceptance\n"
        f"Implement the change described above. "
        f"Stop when done. Do not commit.\n"
    )
