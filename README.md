# Autoforge

Autoforge is a lightweight autonomous engineering orchestrator inspired by OpenAI Symphony.

## Goal

Turn GitHub Issues into isolated implementation runs using jcode agents.

## Installation

```bash
pip install -e .
```

## Usage

```bash
autoforge --help
autoforge doctor
autoforge issues
```

### `autoforge issues`

Lists GitHub issues labeled `status:ready`:

```bash
autoforge issues
```

Output:

```
Found 2 ready issue(s):

  #42 [open] Add feature X
       labels: status:ready, bug
       https://github.com/example/repo/issues/42

  #43 [open] Fix typo Y
       labels: status:ready
       https://github.com/example/repo/issues/43
```

### `autoforge run`

Pick a ready issue, create an isolated git worktree, and run jcode headlessly
against it:

```bash
# Pick the first status:ready issue
autoforge run

# Target a specific issue
autoforge run --issue 42

# Custom model / provider
autoforge run --model anthropic/claude-3-5-sonnet --provider anthropic

# Build the prompt without executing jcode
autoforge run --dry-run --issue 42

# Run tests after jcode completes
autoforge run --issue 42 --test-cmd "python3 -m pytest"

# Commit successful changes and open a PR
autoforge run --issue 42 --test-cmd "python3 -m pytest" --commit --pr

# Comment/label issue status as the run progresses
autoforge run --issue 42 --comment --label-status
```

**How it works:**

1. `autoforge` fetches issues labeled `status:ready` via the GitHub CLI (`gh`).
2. A git worktree is created under `.autoforge/work/<N>/` on branch
   `autoforge/issue-<N>`.
3. The issue body and `WORKFLOW.md` are combined into a prompt.
4. `jcode run` is invoked headlessly against the worktree.
5. If `--test-cmd` is provided, the command runs inside the worktree.
6. If `--commit` is provided, all successful changes are committed.
7. If `--pr` is provided, a pull request is created with `gh pr create`.
8. If `--comment` or `--label-status` are provided, the issue is updated.
9. The worktree is left in place for manual inspection; run
   `git worktree remove <path>` when done.

Useful options:

- `--base <ref>` chooses the base branch/ref for `git worktree add`.
- `--jcode-timeout <seconds>` bounds the headless agent run.
- `--test-timeout <seconds>` bounds `--test-cmd`.
- `--pr` requires `--commit` so there is a commit to publish.

## Architecture

```
gh issue list ──▶ issue dict
gh issue view  ──▶ issue dict  ──┐
                                   ├──▶ WORKFLOW.md ──▶ prompt
jcode run (headless) ──▶ worktree changes
```

The `run` subcommand chains three tools:

1. **gh** fetches issue metadata from GitHub.
2. **git worktree** creates an isolated working copy under
   `.autoforge/work/<N>/`.
3. **jcode** receives the combined prompt (issue + workflow) and writes
   implementation changes into the worktree.
4. Optional validation, commit, PR, comment, and label steps finish the MVP
   loop while preserving human review before merge.

The worktree is intentionally left in place after the run so the user can
inspect the changes before manually cleaning up with
`git worktree remove <path>`.

## Constraints

- No auto merge
- No unrestricted loops
- No autonomous deployment
- Human review required
