"""Worktree management for isolated issue implementation."""

from pathlib import Path

WORKTREE_ROOT = Path(".autoforge/work")

# git commands that should not fail when no remote is configured
_NO_REMOTE_OK = {"fetch"}


def worktree_path(issue_num: int) -> Path:
    """Return the worktree path for a given issue number."""
    return WORKTREE_ROOT / str(issue_num)


def branch_name(issue_num: int) -> str:
    """Return the branch name for a given issue number."""
    return f"autoforge/issue-{issue_num}"


def _ensure_gitignore(repo_root: Path) -> None:
    """Ensure .autoforge/ is listed in the repo-level .gitignore."""
    gitignore = repo_root / ".gitignore"
    entry = ".autoforge/"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if entry not in content:
            gitignore.write_text(
                content.rstrip("\n") + "\n" + entry + "\n",
                encoding="utf-8",
            )
    else:
        gitignore.write_text(entry + "\n", encoding="utf-8")


def create_worktree(
    issue_num: int, base_branch: str = "master"
) -> Path:
    """Create a git worktree for the given issue number.

    Returns the worktree path on success.
    Raises RuntimeError if the path already exists.
    """
    path = worktree_path(issue_num)
    if path.exists():
        raise RuntimeError(
            f"Worktree already exists at {path}. "
            f"Remove with `git worktree remove {path}` first."
        )

    path.parent.mkdir(parents=True, exist_ok=True)

    # Import run_cmd here to avoid circular imports
    from autoforge.cli import run_cmd

    _ensure_gitignore(Path("."))

    # Fetch origin (best-effort; may fail with no remote)
    fetch = run_cmd(["git", "fetch", "origin"])
    if fetch.returncode != 0 and "fetch" not in _NO_REMOTE_OK:
        # Try anyway -- the worktree add may still work with local refs
        pass

    result = run_cmd([
        "git", "worktree", "add",
        "-b", branch_name(issue_num),
        str(path),
        base_branch,
    ])

    if result.returncode != 0:
        raise RuntimeError(
            f"git worktree add failed: {result.stderr.strip()}"
        )

    return path


def remove_worktree(path: Path) -> None:
    """Remove an existing worktree, forcing if needed."""
    from autoforge.cli import run_cmd
    run_cmd(["git", "worktree", "remove", "--force", str(path)])
