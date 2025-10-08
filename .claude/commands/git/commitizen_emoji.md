---
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git commit:*), Bash(git diff:*), Bash(git branch:*), Bash(git log:*), Bash(cz:*)
description: Create a git commit using commitizen with gitmoji
---

## Context

- Current git status: !`git status`
- Unstaged changes: !`git diff`
- Staged changes: !`git diff --staged`
- Current branch: !`git branch --show-current`
- Recent commits: !`git log --oneline -10`

## Your task

Based on the above changes, create a single git commit using commitizen with gitmoji.

Use `git add` to stage files if needed, then use `cz --name cz_gitmoji commit` to create the commit interactively.
