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

## MVP

1. Poll GitHub Issues labeled `status:ready`
2. Create isolated git worktree
3. Run jcode against issue + WORKFLOW.md
4. Run tests
5. Commit branch
6. Open PR
7. Comment status back to GitHub

## Constraints

- No auto merge
- No unrestricted loops
- No autonomous deployment
- Human review required