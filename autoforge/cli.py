"""Autoforge CLI - lightweight autonomous engineering orchestrator."""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from autoforge.prompt import build_prompt, load_workflow_md
from autoforge.worktree import create_worktree


def check_tool(name: str) -> bool:
    """Check if a tool exists on PATH."""
    return shutil.which(name) is not None


def run_cmd(
    cmd: list[str],
    timeout: int | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            cmd,
            124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\nTimed out after {timeout}s",
        )


def run_shell(
    command: str,
    cwd: Path | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    """Run a user-provided shell command for validation steps."""
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            command,
            124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\nTimed out after {timeout}s",
        )


# ---- helpers shared across subcommands ----


def _list_ready_issues() -> list[dict]:
    """Return the list of issues labeled status:ready (raw JSON parse).

    This is the shared backend used by cmd_issues and cmd_run.
    """
    result = run_cmd([
        "gh", "issue", "list",
        "--label", "status:ready",
        "--json", "number,title,state,labels,url",
    ])
    if result.returncode != 0:
        raise RuntimeError(f"gh failed: {result.stderr.strip()}")
    try:
        issues = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"invalid JSON from gh: {exc}")
    return issues


def _view_issue(issue_num: int) -> dict:
    """Fetch details for a single issue by number."""
    result = run_cmd([
        "gh", "issue", "view", str(issue_num),
        "--json", "number,title,body,labels,url",
    ])
    if result.returncode != 0:
        raise RuntimeError(
            f"gh issue view {issue_num} failed: {result.stderr.strip()}"
        )
    try:
        issue = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"invalid JSON from gh issue view: {exc}")
    if issue is None:
        raise RuntimeError(f"Issue #{issue_num} not found.")
    return issue


# ---- subcommand implementations ----


def cmd_issues(args: argparse.Namespace) -> int:
    """List GitHub issues labeled status:ready."""
    if not check_tool("gh"):
        print("[ERROR] gh not found on PATH. Install GitHub CLI first.",
              file=sys.stderr)
        return 1

    try:
        issues = _list_ready_issues()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if not issues:
        print("No ready issues found.")
        return 0

    print(f"Found {len(issues)} ready issue(s):\n")
    for issue in issues:
        number = issue["number"]
        title = issue["title"]
        state = issue["state"]
        labels = ", ".join(l["name"] for l in issue.get("labels", []))
        url = issue["url"]
        print(f"  #{number} [{state}] {title}")
        if labels:
            print(f"       labels: {labels}")
        print(f"       {url}")
        print()

    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run doctor checks."""
    ok = True
    for tool in ("git", "gh"):
        if check_tool(tool):
            print(f"  [OK] {tool} found")
        else:
            print(f"  [MISSING] {tool} not found")
            ok = False
    if ok:
        print("All checks passed.")
    else:
        print("Some checks failed.")
    return 0 if ok else 1


def _gh_issue_comment(issue_num: int, body: str) -> subprocess.CompletedProcess:
    """Post a GitHub issue comment."""
    return run_cmd(["gh", "issue", "comment", str(issue_num), "--body", body])


def _gh_label(
    issue_num: int,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> None:
    """Best-effort add/remove labels for an issue."""
    if add:
        run_cmd([
            "gh", "issue", "edit", str(issue_num),
            "--add-label", ",".join(add),
        ])
    if remove:
        run_cmd([
            "gh", "issue", "edit", str(issue_num),
            "--remove-label", ",".join(remove),
        ])


def _commit_changes(
    wt_path: Path,
    issue_num: int,
    title: str,
) -> subprocess.CompletedProcess:
    """Commit all worktree changes for an issue."""
    run_cmd(["git", "-C", str(wt_path), "add", "-A"])
    message = f"Implement issue #{issue_num}: {title}"
    return run_cmd(["git", "-C", str(wt_path), "commit", "-m", message])


def _create_pr(
    wt_path: Path,
    issue: dict,
    test_summary: str | None,
) -> subprocess.CompletedProcess:
    """Create a pull request for the current worktree branch."""
    body = f"Closes #{issue['number']}\n\nGenerated by autoforge."
    if test_summary:
        body += f"\n\nTest command:\n```\n{test_summary}\n```"
    return run_cmd([
        "gh", "pr", "create",
        "--title", f"Implement issue #{issue['number']}: {issue['title']}",
        "--body", body,
    ], cwd=wt_path)


def cmd_run(args: argparse.Namespace) -> int:
    """Pick a ready issue, create a worktree, and invoke jcode."""
    from autoforge.jcode_run import invoke_jcode

    # 1. Preflight: check required tools
    required_tools = ["gh"] if args.dry_run else ["gh", "git", "jcode"]
    if args.pr or args.comment or args.label_status:
        required_tools.append("gh")
    for tool in dict.fromkeys(required_tools):
        if not check_tool(tool):
            print(f"[ERROR] {tool} not found on PATH.", file=sys.stderr)
            return 1

    # 2. Resolve issue
    model = args.model
    provider = args.provider
    issue_num = args.issue

    if args.pr and not args.commit:
        print(
            "[ERROR] --pr requires --commit so the branch has a commit "
            "to publish.",
            file=sys.stderr,
        )
        return 1

    try:
        if issue_num is not None:
            issue = _view_issue(issue_num)
        else:
            issues = _list_ready_issues()
            if not issues:
                print("No ready issues found.")
                return 0
            issue = issues[0]
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    num = issue["number"]
    title = issue["title"]
    print(f"Selected issue #{num}: {title}")
    if args.label_status and not args.dry_run:
        _gh_label(num, add=["status:in-progress"], remove=["status:ready"])

    # 3. Build prompt
    repo_root = Path.cwd()
    try:
        workflow_md = load_workflow_md(repo_root)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    prompt = build_prompt(issue, workflow_md)
    print(f"Prompt length: {len(prompt)} chars")
    print(f"Prompt preview: {prompt[:200]}...")

    # 4. Dry-run shortcut
    if args.dry_run:
        print("\n--- DRY-RUN: printing full prompt ---")
        print(prompt)
        print("--- END DRY-RUN ---")
        return 0

    # 5. Create worktree
    try:
        wt_path = create_worktree(num, base_branch=args.base)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"Worktree created at: {wt_path}")

    # 6. Invoke jcode
    print("\nRunning jcode...")
    result = invoke_jcode(
        prompt=prompt,
        cwd=wt_path,
        model=model,
        provider=provider,
        timeout_seconds=args.jcode_timeout,
    )
    print(f"jcode exit code: {result['exit_code']}")
    print(f"Elapsed: {result['elapsed_seconds']}s")

    if result["exit_code"] != 0:
        print(
            "[ERROR] jcode failed; leaving worktree for inspection.",
            file=sys.stderr,
        )
        return result["exit_code"] or 1

    test_summary = None
    if args.test_cmd:
        print(f"\nRunning tests: {args.test_cmd}")
        test = run_shell(args.test_cmd, cwd=wt_path, timeout=args.test_timeout)
        test_summary = f"{args.test_cmd}\nexit code: {test.returncode}"
        if test.stdout.strip():
            print(test.stdout)
        if test.stderr.strip():
            print(test.stderr, file=sys.stderr)
        if test.returncode != 0:
            print(
                "[ERROR] test command failed; leaving worktree for inspection.",
                file=sys.stderr,
            )
            if args.comment:
                _gh_issue_comment(
                    num,
                    "Autoforge run failed tests.\n\n"
                    f"```\n{test_summary}\n```",
                )
            if args.label_status:
                _gh_label(
                    num,
                    add=["status:blocked"],
                    remove=["status:ready", "status:in-progress"],
                )
            return test.returncode

    if args.commit:
        print("\nCommitting worktree changes...")
        commit = _commit_changes(wt_path, num, title)
        if commit.returncode != 0:
            print(commit.stderr or commit.stdout, file=sys.stderr)
            return commit.returncode
        print(commit.stdout.strip())

    if args.pr:
        print("\nCreating pull request...")
        pr = _create_pr(wt_path, issue, test_summary)
        if pr.returncode != 0:
            print(pr.stderr or pr.stdout, file=sys.stderr)
            return pr.returncode
        print(pr.stdout.strip())

    if args.comment:
        _gh_issue_comment(
            num,
            f"Autoforge completed a run for issue #{num}.\n\n"
            f"Worktree: `{wt_path}`",
        )
    if args.label_status:
        _gh_label(
            num,
            add=["status:review"],
            remove=["status:ready", "status:in-progress"],
        )

    # 7. Show worktree status
    status = run_cmd(["git", "-C", str(wt_path), "status", "--short"])
    if status.stdout.strip():
        print("\nWorktree changes:")
        print(status.stdout)
    else:
        print("\nNo changes in worktree.")

    # 8. Tell user where to find it (do NOT remove)
    print(f"\nWorktree left at: {wt_path}")
    print("Inspect manually, then `git worktree remove <path>` when done.")
    return 0


def _run_args_for_issue(args: argparse.Namespace, issue_num: int) -> argparse.Namespace:
    """Build a cmd_run namespace from watch args for one issue."""
    return argparse.Namespace(
        issue=issue_num,
        model=args.model,
        provider=args.provider,
        dry_run=args.dry_run,
        base=args.base,
        jcode_timeout=args.jcode_timeout,
        test_cmd=args.test_cmd,
        test_timeout=args.test_timeout,
        commit=args.commit,
        pr=args.pr,
        comment=args.comment,
        label_status=args.label_status,
    )


def cmd_watch(args: argparse.Namespace) -> int:
    """Poll ready issues and run Autoforge with bounded iterations."""
    if args.pr and not args.commit:
        print(
            "[ERROR] --pr requires --commit so the branch has a commit "
            "to publish.",
            file=sys.stderr,
        )
        return 1

    runs = 0
    polls = 0
    print(
        "Watching for GitHub issues labeled status:ready "
        f"every {args.interval}s."
    )
    while True:
        polls += 1
        try:
            issues = _list_ready_issues()
        except RuntimeError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1

        if issues:
            issue = issues[0]
            issue_num = issue["number"]
            print(f"Starting run for issue #{issue_num}: {issue['title']}")
            ret = cmd_run(_run_args_for_issue(args, issue_num))
            runs += 1
            if ret != 0:
                print(
                    f"[ERROR] run for issue #{issue_num} failed with {ret}",
                    file=sys.stderr,
                )
                return ret
        else:
            print("No ready issues found.")

        if args.once:
            return 0
        if args.max_runs is not None and runs >= args.max_runs:
            print(f"Reached max runs: {args.max_runs}")
            return 0
        if args.max_polls is not None and polls >= args.max_polls:
            print(f"Reached max polls: {args.max_polls}")
            return 0

        time.sleep(args.interval)


# ---- argument parsing ----


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="autoforge",
        description="Autoforge - a lightweight autonomous engineering "
                    "orchestrator.",
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s 0.1.0"
    )
    sub = parser.add_subparsers(dest="command")

    # doctor
    sub.add_parser("doctor", help="Check that required tools are installed")

    # issues
    sub.add_parser("issues", help="List issues labeled status:ready")

    # run
    run_parser = sub.add_parser(
        "run",
        help="Pick a ready issue, create a worktree, and run jcode",
    )
    run_parser.add_argument(
        "--issue", type=int, default=None,
        help="Issue number to implement (default: first status:ready)",
    )
    run_parser.add_argument(
        "--model", type=str, default="qwen/qwen3.6-35b-a3b",
        help="Model to use (default: qwen/qwen3.6-35b-a3b)",
    )
    run_parser.add_argument(
        "--provider", type=str, default="openrouter",
        help="Provider to use (default: openrouter)",
    )
    run_parser.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Build prompt and print it without calling jcode",
    )
    run_parser.add_argument(
        "--base", type=str, default="master",
        help="Base branch/ref for the worktree (default: master)",
    )
    run_parser.add_argument(
        "--jcode-timeout", type=int, default=1800,
        help="Timeout for jcode run in seconds (default: 1800)",
    )
    run_parser.add_argument(
        "--test-cmd", type=str, default=None,
        help="Optional test command to run inside the worktree",
    )
    run_parser.add_argument(
        "--test-timeout", type=int, default=900,
        help="Timeout for --test-cmd in seconds (default: 900)",
    )
    run_parser.add_argument(
        "--commit", action="store_true", default=False,
        help="Commit successful changes in the worktree",
    )
    run_parser.add_argument(
        "--pr", action="store_true", default=False,
        help="Create a GitHub PR after a successful committed run",
    )
    run_parser.add_argument(
        "--comment", action="store_true", default=False,
        help="Comment run status back to the GitHub issue",
    )
    run_parser.add_argument(
        "--label-status", action="store_true", default=False,
        help="Move GitHub issue labels between ready/in-progress/review/blocked",
    )

    # watch
    watch_parser = sub.add_parser(
        "watch",
        help="Poll status:ready issues and run Autoforge automatically",
    )
    watch_parser.add_argument(
        "--interval", type=int, default=60,
        help="Seconds between polls (default: 60)",
    )
    watch_parser.add_argument(
        "--once", action="store_true", default=False,
        help="Poll once and run at most one issue",
    )
    watch_parser.add_argument(
        "--max-runs", type=int, default=None,
        help="Stop after this many successful/attempted runs",
    )
    watch_parser.add_argument(
        "--max-polls", type=int, default=None,
        help="Stop after this many polling iterations",
    )
    watch_parser.add_argument(
        "--model", type=str, default="qwen/qwen3.6-35b-a3b",
        help="Model to use (default: qwen/qwen3.6-35b-a3b)",
    )
    watch_parser.add_argument(
        "--provider", type=str, default="openrouter",
        help="Provider to use (default: openrouter)",
    )
    watch_parser.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Build prompt and print it without calling jcode",
    )
    watch_parser.add_argument(
        "--base", type=str, default="master",
        help="Base branch/ref for the worktree (default: master)",
    )
    watch_parser.add_argument(
        "--jcode-timeout", type=int, default=1800,
        help="Timeout for jcode run in seconds (default: 1800)",
    )
    watch_parser.add_argument(
        "--test-cmd", type=str, default=None,
        help="Optional test command to run inside each worktree",
    )
    watch_parser.add_argument(
        "--test-timeout", type=int, default=900,
        help="Timeout for --test-cmd in seconds (default: 900)",
    )
    watch_parser.add_argument(
        "--commit", action="store_true", default=False,
        help="Commit successful changes in each worktree",
    )
    watch_parser.add_argument(
        "--pr", action="store_true", default=False,
        help="Create a GitHub PR after each successful committed run",
    )
    watch_parser.add_argument(
        "--comment", action="store_true", default=False,
        help="Comment run status back to each GitHub issue",
    )
    watch_parser.add_argument(
        "--label-status", action="store_true", default=False,
        help="Move GitHub issue labels between ready/in-progress/review/blocked",
    )

    parsed = parser.parse_args()

    if parsed.command == "doctor":
        return cmd_doctor(parsed)
    if parsed.command == "issues":
        return cmd_issues(parsed)
    if parsed.command == "run":
        return cmd_run(parsed)
    if parsed.command == "watch":
        return cmd_watch(parsed)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
