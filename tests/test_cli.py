"""Minimal tests for autoforge CLI."""

import argparse
import json
import subprocess
import sys
from unittest.mock import patch

import pytest

from autoforge.cli import check_tool, cmd_doctor, cmd_issues, main


def test_check_tool_exists():
    """check_tool returns True for existing tools."""
    assert check_tool("python3") is True


def test_check_tool_missing():
    """check_tool returns False for non-existent tools."""
    assert check_tool("nonexistent_tool_xyz") is False


def test_doctor_all_ok(capsys):
    """doctor reports OK when all tools are found."""
    with patch("autoforge.cli.check_tool", return_value=True):
        ret = cmd_doctor(argparse.Namespace())
    captured = capsys.readouterr()
    assert "git" in captured.out
    assert "gh" in captured.out
    assert "All checks passed" in captured.out
    assert ret == 0


def test_doctor_missing(capsys):
    """doctor reports failure when a tool is missing."""
    def fake_check(name):
        return name == "git"  # gh is missing
    with patch("autoforge.cli.check_tool", side_effect=fake_check):
        ret = cmd_doctor(argparse.Namespace())
    captured = capsys.readouterr()
    assert "MISSING" in captured.out
    assert ret == 1


def test_main_help(capsys, monkeypatch):
    """main with no args prints help."""
    monkeypatch.setattr(sys, "argv", ["autoforge"])
    ret = main()
    captured = capsys.readouterr()
    assert "autoforge" in captured.out
    assert ret == 0


# ---- issues command tests ----

SAMPLE_ISSUES_JSON = json.dumps([
    {
        "number": 42,
        "title": "Add feature X",
        "state": "open",
        "labels": [{"name": "status:ready"}, {"name": "bug"}],
        "url": "https://github.com/example/repo/issues/42",
    },
    {
        "number": 43,
        "title": "Fix typo Y",
        "state": "open",
        "labels": [{"name": "status:ready"}],
        "url": "https://github.com/example/repo/issues/43",
    },
])

SAMPLE_EMPTY_JSON = "[]"

SAMPLE_INVALID_JSON = "not json at all"


class MockCompletedProcess:
    """Fake subprocess.CompletedProcess for testing."""
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


@pytest.mark.parametrize("stdout,stderr,returncode", [
    (json.dumps([{"number": 1}]), "auth failed", 1),
    ("", "exit 1", 2),
])
def test_issues_gh_error(capsys, stdout, stderr, returncode):
    """cmd_issues returns 1 when gh command fails."""
    mock = MockCompletedProcess(stdout=stdout, stderr=stderr, returncode=returncode)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with patch("autoforge.cli.check_tool", return_value=True):
            ret = cmd_issues(argparse.Namespace())
    captured = capsys.readouterr()
    assert ret == 1
    assert "[ERROR]" in captured.out + captured.err


def test_issues_no_ready(capsys):
    """cmd_issues prints 'No ready issues found.' when the list is empty."""
    mock = MockCompletedProcess(stdout=SAMPLE_EMPTY_JSON)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with patch("autoforge.cli.check_tool", return_value=True):
            ret = cmd_issues(argparse.Namespace())
    captured = capsys.readouterr()
    assert "No ready issues found." in captured.out
    assert ret == 0


def test_issues_with_issues(capsys):
    """cmd_issues prints a readable list when issues exist."""
    mock = MockCompletedProcess(stdout=SAMPLE_ISSUES_JSON)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with patch("autoforge.cli.check_tool", return_value=True):
            ret = cmd_issues(argparse.Namespace())
    captured = capsys.readouterr()
    assert "Found 2 ready issue" in captured.out
    assert "#42 [open] Add feature X" in captured.out
    assert "#43 [open] Fix typo Y" in captured.out
    assert "status:ready" in captured.out
    assert "bug" in captured.out
    assert "https://github.com/example/repo/issues/42" in captured.out
    assert ret == 0


def test_issues_invalid_json(capsys):
    """cmd_issues returns 1 when gh output is not valid JSON."""
    mock = MockCompletedProcess(stdout=SAMPLE_INVALID_JSON)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with patch("autoforge.cli.check_tool", return_value=True):
            ret = cmd_issues(argparse.Namespace())
    captured = capsys.readouterr()
    assert ret == 1
    assert "[ERROR]" in captured.out + captured.err
    assert "Failed to parse" in captured.out + captured.err


def test_issues_missing_gh(capsys):
    """cmd_issues returns 1 when gh is not installed."""
    with patch("autoforge.cli.check_tool", return_value=False):
        ret = cmd_issues(argparse.Namespace())
    captured = capsys.readouterr()
    assert ret == 1
    assert "gh not found" in captured.out + captured.err


def test_main_issues_command(capsys, monkeypatch):
    """main dispatches to cmd_issues when 'issues' subcommand is given."""
    monkeypatch.setattr(
        sys, "argv", ["autoforge", "issues"]
    )
    mock = MockCompletedProcess(stdout=SAMPLE_ISSUES_JSON)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with patch("autoforge.cli.check_tool", return_value=True):
            ret = main()
    captured = capsys.readouterr()
    assert "Found 2 ready issue" in captured.out
    assert ret == 0