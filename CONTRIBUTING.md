# Contributing

AgentFlow uses a small but explicit Git workflow so feature work, fixes, and release-ready code stay reviewable.

## Branch Model

- `main`: stable branch. It should pass `python scripts/checks.py`.
- `feature/<name>`: user-facing or runtime capability, for example `feature/replay-comparison`.
- `fix/<name>`: bug fix or regression coverage, for example `fix/chinese-stats-routing`.
- `docs/<name>`: documentation-only work.
- `chore/<name>`: CI, tooling, repository maintenance.

For Codex-assisted work in this workspace, branches may also use the `codex/<name>` prefix.

## Daily Commands

Create a branch from the latest `main`:

```powershell
git fetch origin
git switch main
git pull --ff-only
git switch -c feature/my-change
```

Switch to an existing local branch:

```powershell
git switch feature/my-change
```

Fetch and switch to a branch that only exists on GitHub:

```powershell
git fetch origin
git switch -c feature/my-change --track origin/feature/my-change
```

Inspect history:

```powershell
git log --oneline --decorate --graph --all
```

Check what changed before committing:

```powershell
git status --short
git diff
```

Commit a focused change:

```powershell
git add src tests
git commit -m "Add replay comparison metrics"
```

Push the current branch:

```powershell
git push -u origin HEAD
```

## Quality Gate

Run the local check script before pushing:

```powershell
python scripts/checks.py
```

The script runs:

- Python syntax checks.
- Unit tests.
- Local-only evaluation smoke test.
- Frontend JavaScript syntax check when Node.js is installed.

The evaluation step passes `--local-only`, so CI does not depend on an external LLM provider or spend API quota.

## Recovering Files

Restore one file from the latest committed version:

```powershell
git restore path\to\file.py
```

Restore one file from another branch:

```powershell
git checkout main -- path\to\file.py
```

Look at a file from a specific commit without changing the working tree:

```powershell
git show <commit_hash>:src/generator.py
```
