"""Comprehensive tests for autoforge CLI, worktree, prompt, and jcode_run."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

from autoforge.cli import (
    check_tool,
    cmd_doctor,
    cmd_issues,
    cmd_run,
    main,
    run_cmd,
    _list_ready_issues,
    _view_issue,
)
from autoforge.worktree import (
    branch_name,
    create_worktree,
    remove_worktree,
    worktree_path,
)
from autoforge.prompt import build_prompt, load_workflow_md
from autoforge.jcode_run import invoke_jcode


# ---- helpers ----


class MockCompletedProcess:
    """Fake subprocess.CompletedProcess for testing."""

    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


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


# ---- check_tool ----


def test_check_tool_exists():
    """check_tool returns True for existing tools."""
    assert check_tool("python3") is True


def test_check_tool_missing():
    """check_tool returns False for non-existent tools."""
    assert check_tool("nonexistent_tool_xyz") is False


# ---- doctor ----


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


# ---- main dispatch ----


def test_main_help(capsys, monkeypatch):
    """main with no args prints help."""
    monkeypatch.setattr(sys, "argv", ["autoforge"])
    ret = main()
    captured = capsys.readouterr()
    assert "autoforge" in captured.out
    assert ret == 0


def test_main_issues_command(capsys, monkeypatch):
    """main dispatches to cmd_issues when 'issues' subcommand is given."""
    monkeypatch.setattr(sys, "argv", ["autoforge", "issues"])
    mock = MockCompletedProcess(stdout=SAMPLE_ISSUES_JSON)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with patch("autoforge.cli.check_tool", return_value=True):
            ret = main()
    captured = capsys.readouterr()
    assert "Found 2 ready issue" in captured.out
    assert ret == 0


def test_main_run_command(capsys, monkeypatch):
    """main dispatches to cmd_run when 'run' subcommand is given."""
    monkeypatch.setattr(sys, "argv", ["autoforge", "run", "--dry-run", "--issue", "42"])
    issue_json = json.dumps({
        "number": 42,
        "title": "Test issue",
        "body": "Test body",
        "labels": [],
        "url": "https://example.com/42",
    })
    mock = MockCompletedProcess(stdout=issue_json)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with patch("autoforge.cli.check_tool", return_value=True):
            ret = main()
    captured = capsys.readouterr()
    assert "Selected issue #42" in captured.out
    assert ret == 0


# ---- issues command tests ----


@pytest.mark.parametrize("stdout,stderr,returncode", [
    (json.dumps([{"number": 1}]), "auth failed", 1),
    ("", "exit 1", 2),
])
def test_issues_gh_error(capsys, stdout, stderr, returncode):
    """cmd_issues returns 1 when gh command fails."""
    mock = MockCompletedProcess(stdout=stdout, stderr=stderr,
                                returncode=returncode)
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
    assert "invalid JSON" in captured.out + captured.err


def test_issues_missing_gh(capsys):
    """cmd_issues returns 1 when gh is not installed."""
    with patch("autoforge.cli.check_tool", return_value=False):
        ret = cmd_issues(argparse.Namespace())
    captured = capsys.readouterr()
    assert ret == 1
    assert "gh not found" in captured.out + captured.err


# ---- _list_ready_issues ----


def test_list_ready_issues_parses_json():
    """_list_ready_issues returns parsed JSON list."""
    mock = MockCompletedProcess(stdout=SAMPLE_ISSUES_JSON)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        issues = _list_ready_issues()
    assert len(issues) == 2
    assert issues[0]["number"] == 42


def test_list_ready_issues_raises_on_failure():
    """_list_ready_issues raises RuntimeError on non-zero exit."""
    mock = MockCompletedProcess(stdout="", stderr="auth failed",
                                returncode=1)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with pytest.raises(RuntimeError, match="gh failed"):
            _list_ready_issues()


# ---- _view_issue ----


def test_view_issue_parses_json():
    """_view_issue returns parsed issue dict."""
    issue_json = json.dumps({
        "number": 7,
        "title": "Bug report",
        "body": "Something is broken",
        "labels": [],
        "url": "https://github.com/example/repo/issues/7",
    })
    mock = MockCompletedProcess(stdout=issue_json)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        issue = _view_issue(7)
    assert issue["number"] == 7
    assert issue["title"] == "Bug report"


def test_view_issue_not_found():
    """_view_issue raises when gh returns null."""
    mock = MockCompletedProcess(stdout="null")
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with pytest.raises(RuntimeError, match="not found"):
            _view_issue(999)


def test_view_issue_command_error():
    """_view_issue raises when gh fails."""
    mock = MockCompletedProcess(stdout="", stderr="bad repo", returncode=1)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with pytest.raises(RuntimeError, match="gh issue view"):
            _view_issue(999)


# ---- worktree module tests ----


def test_worktree_path_format():
    """worktree_path returns the expected Path."""
    assert worktree_path(42) == Path(".autoforge/work/42")
    assert worktree_path(1) == Path(".autoforge/work/1")


def test_branch_name_format():
    """branch_name returns the expected string."""
    assert branch_name(42) == "autoforge/issue-42"
    assert branch_name(1) == "autoforge/issue-1"


def test_create_worktree_calls_git_correctly(tmp_path, monkeypatch):
    """create_worktree invokes git with correct arguments."""
    # Create a minimal .git repo at tmp_path so git worktree add succeeds
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], capture_output=True, check=True)
    # Create a commit so we have something to branch from
    (tmp_path / "README.md").write_text("hi\n")
    subprocess.run(
        ["git", "add", "README.md"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        [
            "git", "config", "user.email", "test@test.com",
        ],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        [
            "git", "config", "user.name", "Test",
        ],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        capture_output=True,
        check=True,
    )

    with patch("autoforge.cli.run_cmd") as mock_run:
        mock_run.side_effect = [
            MockCompletedProcess(stderr="no remote\n", returncode=1),
            MockCompletedProcess(),  # success
        ]
        result = create_worktree(7)

    assert result == Path(".autoforge/work/7")

    # Assert that git worktree add was called with correct args
    calls = mock_run.call_args_list
    add_call = calls[1]
    add_cmd = add_call[0][0]
    assert "git" in add_cmd
    assert "worktree" in add_cmd
    assert "add" in add_cmd
    assert "-b" in add_cmd
    assert "autoforge/issue-7" in add_cmd
    assert "master" in add_cmd


def test_create_worktree_errors_if_path_exists(tmp_path, monkeypatch):
    """create_worktree raises RuntimeError when worktree path exists."""
    monkeypatch.chdir(tmp_path)
    # Create the path manually
    worktree_dir = tmp_path / ".autoforge" / "work" / "42"
    worktree_dir.mkdir(parents=True)
    (worktree_dir / "placeholder").write_text("x")

    with pytest.raises(RuntimeError, match="already exists"):
        create_worktree(42)


def test_remove_worktree_calls_git(tmp_path, monkeypatch):
    """remove_worktree invokes git worktree remove --force."""
    monkeypatch.chdir(tmp_path)
    with patch("autoforge.cli.run_cmd") as mock_run:
        remove_worktree(tmp_path / ".autoforge/work/99")
    mock_run.assert_called_once_with(
        ["git", "worktree", "remove", "--force",
         str(tmp_path / ".autoforge/work/99")]
    )


def test_create_worktree_writes_repo_gitignore(
    tmp_path, monkeypatch,
):
    """create_worktree writes .autoforge/ into the repo .gitignore."""
    monkeypatch.chdir(tmp_path)
    # Initialise a git repo so worktree add works
    subprocess.run(["git", "init"], capture_output=True, check=True)
    (tmp_path / "README.md").write_text("hi\n")
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        capture_output=True,
        check=True,
    )
    # Stage and commit before creating .gitignore
    subprocess.run(["git", "add", "README.md"], capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        capture_output=True,
        check=True,
    )
    # Pre-create a .gitignore with existing content
    (tmp_path / ".gitignore").write_text("existing\n")

    with patch("autoforge.cli.run_cmd") as mock_run:
        mock_run.side_effect = [
            MockCompletedProcess(stderr="no remote\n", returncode=1),
            MockCompletedProcess(),  # success
        ]
        create_worktree(5)

    # Repo-level .gitignore should contain .autoforge/
    gitignore_text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".autoforge/" in gitignore_text

    # .autoforge/.gitignore must NOT exist (we write to repo .gitignore only)
    assert (tmp_path / ".autoforge" / ".gitignore").exists() is False


# ---- prompt module tests ----


def test_build_prompt_includes_issue_body_and_workflow():
    """build_prompt includes issue number, title, body and workflow."""
    issue = {
        "number": 42,
        "title": "Add a feature",
        "body": "Please add feature Z.\n\nDetails here.",
    }
    workflow = "Rule 1: be good.\nRule 2: test things.\n"
    prompt = build_prompt(issue, workflow)

    assert "Issue #42: Add a feature" in prompt
    assert "Please add feature Z." in prompt
    assert "Details here." in prompt
    assert "Rule 1: be good." in prompt
    assert "Rule 2: test things." in prompt
    assert "Working Rules" in prompt
    assert "Acceptance" in prompt
    assert "Stop when done. Do not commit." in prompt


def test_build_prompt_handles_empty_body():
    """build_prompt handles missing or empty body gracefully."""
    issue = {"number": 1, "title": "No body", "body": ""}
    workflow = "rules\n"
    prompt = build_prompt(issue, workflow)
    assert "Issue #1: No body" in prompt
    assert "Issue Description" in prompt


def test_build_prompt_handles_missing_body_key():
    """build_prompt handles issue dict without body key."""
    issue = {"number": 1, "title": "No body key"}
    workflow = "rules\n"
    prompt = build_prompt(issue, workflow)
    assert "Issue #1: No body key" in prompt


def test_load_workflow_md_found(tmp_path):
    """load_workflow_md returns content when WORKFLOW.md exists."""
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text("do things\n")
    result = load_workflow_md(tmp_path)
    assert "do things" in result


def test_load_workflow_md_missing_raises_clear_error(tmp_path):
    """load_workflow_md raises FileNotFoundError with clear message."""
    with pytest.raises(FileNotFoundError, match="WORKFLOW.md"):
        load_workflow_md(tmp_path)


# ---- jcode_run module tests ----


def test_invoke_jcode_builds_correct_command(
    tmp_path, monkeypatch,
):
    """invoke_jcode builds the correct jcode command."""
    monkeypatch.chdir(tmp_path)
    prompt_text = "Run this task"
    worktree = tmp_path / ".autoforge/work/42"
    worktree.mkdir(parents=True)

    mock_result = MockCompletedProcess(
        stdout='{"exit_code": 0}',
        stderr=""
    )
    with patch(
        "autoforge.jcode_run.run_cmd", return_value=mock_result,
    ) as mock_run:
        result = invoke_jcode(
            prompt=prompt_text,
            cwd=worktree,
            model="custom/model",
            provider="custom-provider",
        )

    # Check the command that was built
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert mock_run.call_args.kwargs["timeout"] == 1800
    assert cmd[0] == "jcode"
    assert cmd[1] == "run"
    assert "--provider" in cmd
    assert "custom-provider" in cmd
    assert "--model" in cmd
    assert "custom/model" in cmd
    assert "--cwd" in cmd
    assert str(worktree) in cmd
    assert "--quiet" in cmd
    assert "--json" in cmd


def test_invoke_jcode_uses_defaults(tmp_path, monkeypatch):
    """invoke_jcode uses default model and provider when not specified."""
    monkeypatch.chdir(tmp_path)
    worktree = tmp_path / ".autoforge/work/1"
    worktree.mkdir(parents=True)

    mock_result = MockCompletedProcess(stdout="{}")
    with patch(
        "autoforge.jcode_run.run_cmd", return_value=mock_result,
    ) as mock_run:
        invoke_jcode(prompt="test", cwd=worktree)

    cmd = mock_run.call_args[0][0]
    assert mock_run.call_args.kwargs["timeout"] == 1800
    idx_provider = cmd.index("--provider")
    assert cmd[idx_provider + 1] == "openrouter"
    idx_model = cmd.index("--model")
    assert cmd[idx_model + 1] == "qwen/qwen3.6-35b-a3b"


def test_invoke_jcode_redacts_api_key_in_output(
    tmp_path, monkeypatch,
):
    """invoke_jcode redacts OPENROUTER_API_KEY from stdout/stderr."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-12345")
    worktree = tmp_path / ".autoforge/work/1"
    worktree.mkdir(parents=True)

    mock_result = MockCompletedProcess(
        stdout='{"output": "sk-secret-12345"}',
        stderr="error with sk-secret-12345",
    )
    with patch(
        "autoforge.jcode_run.run_cmd", return_value=mock_result,
    ):
        result = invoke_jcode(prompt="test", cwd=worktree)

    assert "sk-secret-12345" not in result["stdout_raw"]
    assert "***REDACTED***" in result["stdout_raw"]
    assert "***REDACTED***" in result["stderr_tail"]


def test_invoke_jcode_returns_parsed_json_when_valid(
    tmp_path, monkeypatch,
):
    """invoke_jcode parses valid JSON from stdout."""
    monkeypatch.chdir(tmp_path)
    worktree = tmp_path / ".autoforge/work/1"
    worktree.mkdir(parents=True)

    expected = {"exit_code": 0, "output": "done"}
    mock_result = MockCompletedProcess(stdout=json.dumps(expected))
    with patch(
        "autoforge.jcode_run.run_cmd", return_value=mock_result,
    ):
        result = invoke_jcode(prompt="test", cwd=worktree)

    assert result["parsed"] == expected
    assert result["exit_code"] == 0


def test_invoke_jcode_returns_none_parsed_on_invalid_json(
    tmp_path, monkeypatch,
):
    """invoke_jcode returns None for parsed when JSON is invalid."""
    monkeypatch.chdir(tmp_path)
    worktree = tmp_path / ".autoforge/work/1"
    worktree.mkdir(parents=True)

    mock_result = MockCompletedProcess(stdout="not valid json!!!")
    with patch(
        "autoforge.jcode_run.run_cmd", return_value=mock_result,
    ):
        result = invoke_jcode(prompt="test", cwd=worktree)

    assert result["parsed"] is None


def test_invoke_jcode_returns_none_on_empty_output(
    tmp_path, monkeypatch,
):
    """invoke_jcode returns None when stdout is empty."""
    monkeypatch.chdir(tmp_path)
    worktree = tmp_path / ".autoforge/work/1"
    worktree.mkdir(parents=True)

    mock_result = MockCompletedProcess(stdout="", stderr="nothing")
    with patch(
        "autoforge.jcode_run.run_cmd", return_value=mock_result,
    ):
        result = invoke_jcode(prompt="test", cwd=worktree)

    assert result["parsed"] is None
    assert result["stdout_raw"] == ""


def test_invoke_jcode_writes_debug_file(
    tmp_path, monkeypatch,
):
    """invoke_jcode writes .autoforge/last-run.json."""
    monkeypatch.chdir(tmp_path)
    worktree = tmp_path / ".autoforge/work/1"
    worktree.mkdir(parents=True)

    mock_result = MockCompletedProcess(stdout='{}')
    with patch(
        "autoforge.jcode_run.run_cmd", return_value=mock_result,
    ):
        invoke_jcode(prompt="test", cwd=worktree)

    debug_file = tmp_path / ".autoforge" / "last-run.json"
    assert debug_file.exists()
    data = json.loads(debug_file.read_text(encoding="utf-8"))
    assert data["cwd"] == str(worktree)
    assert "elapsed_seconds" in data


def test_invoke_jcode_stderr_truncated(tmp_path, monkeypatch):
    """invoke_jcode keeps stderr to last 50 lines."""
    monkeypatch.chdir(tmp_path)
    worktree = tmp_path / ".autoforge/work/1"
    worktree.mkdir(parents=True)

    # 60 lines of stderr
    long_stderr = "\n".join(f"line {i}" for i in range(60))
    mock_result = MockCompletedProcess(
        stdout="{}",
        stderr=long_stderr,
    )
    with patch(
        "autoforge.jcode_run.run_cmd", return_value=mock_result,
    ):
        result = invoke_jcode(prompt="test", cwd=worktree)

    # Should have last 50 lines (lines 10-59)
    assert len(result["stderr_tail"].splitlines()) == 50
    assert "line 10" in result["stderr_tail"]
    assert "line 59" in result["stderr_tail"]


# ---- cmd_run integration-ish tests ----


def test_cmd_run_dry_run_skips_jcode(capsys, monkeypatch):
    """cmd_run --dry-run does not call jcode or create worktree."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["autoforge", "run", "--dry-run", "--issue", "42"],
    )
    issue_json = json.dumps({
        "number": 42,
        "title": "Dry run test",
        "body": "This is a test body",
        "labels": [],
        "url": "https://example.com/42",
    })
    mock = MockCompletedProcess(stdout=issue_json)

    with patch("autoforge.cli.run_cmd", return_value=mock):
        with patch("autoforge.cli.check_tool", return_value=True):
            ret = main()

    captured = capsys.readouterr()
    assert ret == 0
    assert "Selected issue #42" in captured.out
    assert "DRY-RUN" in captured.out
    assert "Dry run test" in captured.out
    # Should NOT have worktree creation or jcode output
    assert "Worktree created" not in captured.out


def test_cmd_run_no_issue_picks_first_ready(capsys, monkeypatch):
    """cmd_run without --issue picks the first ready issue."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["autoforge", "run", "--dry-run"],
    )
    # Only one call: list ready issues
    mock = MockCompletedProcess(stdout=SAMPLE_ISSUES_JSON)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with patch("autoforge.cli.check_tool", return_value=True):
            ret = main()
    captured = capsys.readouterr()
    assert ret == 0
    assert "Selected issue #42: Add feature X" in captured.out


def test_cmd_run_no_issues_found(capsys, monkeypatch):
    """cmd_run returns 0 and prints message when no issues are ready."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["autoforge", "run", "--dry-run"],
    )
    mock = MockCompletedProcess(stdout=SAMPLE_EMPTY_JSON)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with patch("autoforge.cli.check_tool", return_value=True):
            ret = main()
    captured = capsys.readouterr()
    assert ret == 0
    assert "No ready issues found" in captured.out


def test_cmd_run_missing_gh(capsys, monkeypatch):
    """cmd_run returns 1 when gh is not found."""
    monkeypatch.setattr(sys, "argv", ["autoforge", "run", "--dry-run"])
    with patch("autoforge.cli.check_tool", return_value=False):
        ret = main()
    captured = capsys.readouterr()
    assert ret == 1
    assert "gh not found" in captured.out + captured.err


def test_cmd_run_missing_git(capsys, monkeypatch):
    """cmd_run returns 1 when git is not found for real runs."""
    monkeypatch.setattr(sys, "argv", ["autoforge", "run"])
    def fake_check(name):
        return name != "git"
    with patch("autoforge.cli.check_tool", side_effect=fake_check):
        ret = main()
    captured = capsys.readouterr()
    assert ret == 1
    assert "git not found" in captured.out + captured.err


def test_cmd_run_missing_jcode(capsys, monkeypatch):
    """cmd_run returns 1 when jcode is not found for real runs."""
    monkeypatch.setattr(sys, "argv", ["autoforge", "run"])
    def fake_check(name):
        return name != "jcode"
    with patch("autoforge.cli.check_tool", side_effect=fake_check):
        ret = main()
    captured = capsys.readouterr()
    assert ret == 1
    assert "jcode not found" in captured.out + captured.err


def test_cmd_run_dry_run_does_not_require_jcode(capsys, monkeypatch):
    """cmd_run --dry-run only needs gh because it does not invoke jcode/git."""
    monkeypatch.setattr(sys, "argv", ["autoforge", "run", "--dry-run", "--issue", "42"])
    issue_json = json.dumps({
        "number": 42,
        "title": "Dry without jcode",
        "body": "body",
        "labels": [],
        "url": "https://example.com/42",
    })
    mock = MockCompletedProcess(stdout=issue_json)

    def fake_check(name):
        return name != "jcode"

    with patch("autoforge.cli.run_cmd", return_value=mock):
        with patch("autoforge.cli.check_tool", side_effect=fake_check):
            ret = main()
    captured = capsys.readouterr()
    assert ret == 0
    assert "DRY-RUN" in captured.out


def test_cmd_run_missing_workflow(capsys, monkeypatch, tmp_path):
    """cmd_run fails when WORKFLOW.md is missing."""
    monkeypatch.setattr(
        sys, "argv", ["autoforge", "run", "--dry-run", "--issue", "42"]
    )
    monkeypatch.chdir(tmp_path)
    issue_json = json.dumps({
        "number": 42,
        "title": "Test",
        "body": "body",
        "labels": [],
        "url": "https://example.com/42",
    })
    mock = MockCompletedProcess(stdout=issue_json)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with patch("autoforge.cli.check_tool", return_value=True):
            ret = main()
    assert ret == 1


def test_cmd_run_nonzero_exit_gh_list(capsys, monkeypatch):
    """cmd_run fails when gh list returns an error."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["autoforge", "run", "--dry-run"],
    )
    mock = MockCompletedProcess(stdout="", stderr="unauthorized",
                                returncode=1)
    with patch("autoforge.cli.run_cmd", return_value=mock):
        with patch("autoforge.cli.check_tool", return_value=True):
            ret = main()
    captured = capsys.readouterr()
    assert ret == 1
    assert "gh failed" in captured.out + captured.err


# ---- arg parsing tests ----


def test_run_parser_has_expected_args(monkeypatch):
    """The run subparser accepts all expected arguments."""
    from autoforge.cli import main
    monkeypatch.setattr(sys, "argv", [
        "autoforge", "run",
        "--issue", "100",
        "--model", "anthropic/claude-3-5-sonnet",
        "--provider", "anthropic",
        "--dry-run",
    ])
    with patch("autoforge.cli.check_tool", return_value=True):
        with patch("autoforge.cli._view_issue") as mock_view:
            mock_view.return_value = {
                "number": 100, "title": "Test", "body": "",
                "labels": [], "url": "",
            }
            main()
    mock_view.assert_called_once_with(100)


# ---- watch command tests ----


def test_cmd_watch_once_no_ready_issues(capsys):
    """watch --once exits cleanly when no issues are ready."""
    args = argparse.Namespace(
        once=True,
        interval=0,
        max_runs=None,
        max_polls=None,
        max_seconds=None,
        max_errors=5,
        pr=False,
        commit=False,
    )
    with patch("autoforge.cli._list_ready_issues", return_value=[]):
        ret = __import__("autoforge.cli", fromlist=["cmd_watch"]).cmd_watch(args)
    captured = capsys.readouterr()
    assert ret == 0
    assert "No ready issues found" in captured.out


def test_cmd_watch_runs_first_ready_issue(capsys):
    """watch --once dispatches the first ready issue to cmd_run."""
    from autoforge.cli import cmd_watch
    args = argparse.Namespace(
        once=True,
        interval=0,
        max_runs=None,
        max_polls=None,
        max_seconds=None,
        max_errors=5,
        model="m",
        provider="p",
        dry_run=True,
        base="master",
        jcode_timeout=1,
        test_cmd=None,
        test_timeout=1,
        commit=False,
        pr=False,
        comment=False,
        label_status=False,
    )
    issue = {"number": 42, "title": "Do thing"}
    with patch("autoforge.cli._list_ready_issues", return_value=[issue]):
        with patch("autoforge.cli.cmd_run", return_value=0) as mock_run:
            ret = cmd_watch(args)
    captured = capsys.readouterr()
    assert ret == 0
    assert "Starting run for issue #42" in captured.out
    mock_run.assert_called_once()
    assert mock_run.call_args.args[0].issue == 42


def test_cmd_watch_pr_requires_commit(capsys):
    """watch rejects --pr without --commit."""
    from autoforge.cli import cmd_watch
    args = argparse.Namespace(pr=True, commit=False, max_errors=5)
    ret = cmd_watch(args)
    captured = capsys.readouterr()
    assert ret == 1
    assert "--pr requires --commit" in captured.out + captured.err
