"""Minimal tests for autoforge CLI."""

import argparse
import sys
from unittest.mock import patch

import pytest

from autoforge.cli import check_tool, cmd_doctor, main


def test_check_tool_exists():
    """check_tool returns True for existing tools."""
    assert check_tool("python") is True


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