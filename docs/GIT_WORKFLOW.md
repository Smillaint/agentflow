# Git Workflow Notes

This document is mainly for interview review. It explains how AgentFlow is managed as a normal engineering project rather than a one-shot script repository.

## Current Repository Shape

- `main` is the stable branch.
- Feature and tooling work should happen on short-lived branches.
- Each commit should represent one reviewable intent: runtime feature, test coverage, documentation, or tooling.
- CI runs the same local quality gate through `scripts/checks.py`.

## Example Development Flow

```powershell
git fetch origin
git switch main
git pull --ff-only
git switch -c feature/new-tool

# edit code and tests
python scripts/checks.py

git status --short
git diff
git add src tests docs
git commit -m "Add new tool execution path"
git push -u origin HEAD
```

## How To Get A Specific Branch

If the branch already exists locally:

```powershell
git switch feature/new-tool
```

If it only exists on GitHub:

```powershell
git fetch origin
git switch -c feature/new-tool --track origin/feature/new-tool
```

If you only need to inspect it temporarily:

```powershell
git fetch origin
git switch --detach origin/feature/new-tool
```

## How To Inspect A Specific Commit

Show the full commit:

```powershell
git show <commit_hash>
```

Show only changed files:

```powershell
git show --stat <commit_hash>
```

Open one file from a commit:

```powershell
git show <commit_hash>:src/generator.py
```

## How To Explain This In Interview

I use `main` as the stable branch and implement changes on short-lived feature or fix branches. Before pushing, I run `python scripts/checks.py`, which performs syntax checks, unit tests, local-only evaluation smoke tests, and frontend JavaScript syntax checks. GitHub Actions runs the same gate on push and pull request, so local and remote checks stay consistent.

For a branch that already exists remotely, I first run `git fetch origin`, then use `git switch -c <local_branch> --track origin/<remote_branch>`. For inspecting a commit or file without changing the working tree, I use `git show`.

The reason I avoid dumping unrelated changes into one commit is reviewability. If a regression appears, smaller commits make it easier to identify whether the issue came from retrieval, generation, trace persistence, evaluation, or frontend changes.
