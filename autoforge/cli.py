"""Autoforge CLI - lightweight autonomous engineering orchestrator."""

import argparse
import shutil
import subprocess
import sys


def check_tool(name: str) -> bool:
    """Check if a tool exists on PATH."""
    return shutil.which(name) is not None


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

    parsed = parser.parse_args()

    if parsed.command == "doctor":
        return cmd_doctor(parsed)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())