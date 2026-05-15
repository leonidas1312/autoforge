"""Autoforge CLI - lightweight autonomous engineering orchestrator."""

import argparse
import json
import shutil
import subprocess
import sys


def check_tool(name: str) -> bool:
    """Check if a tool exists on PATH."""
    return shutil.which(name) is not None


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def cmd_issues(args: argparse.Namespace) -> int:
    """List GitHub issues labeled status:ready."""
    if not check_tool("gh"):
        print("[ERROR] gh not found on PATH. Install GitHub CLI first.", file=sys.stderr)
        return 1

    result = run_cmd([
        "gh", "issue", "list",
        "--label", "status:ready",
        "--json", "number,title,state,labels,url",
    ])

    if result.returncode != 0:
        print(f"[ERROR] gh failed: {result.stderr.strip()}", file=sys.stderr)
        return 1

    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Failed to parse gh output: {exc}", file=sys.stderr)
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


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="autoforge",
        description="Autoforge - a lightweight autonomous engineering orchestrator.",
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s 0.1.0"
    )
    sub = parser.add_subparsers(dest="command")

    # doctor
    sub.add_parser("doctor", help="Check that required tools are installed")

    # issues
    sub.add_parser("issues", help="List issues labeled status:ready")

    parsed = parser.parse_args()

    if parsed.command == "doctor":
        return cmd_doctor(parsed)
    if parsed.command == "issues":
        return cmd_issues(parsed)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())