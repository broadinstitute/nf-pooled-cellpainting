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

Based on the above changes, create a single git commit with gitmoji using conventional commits format.

Steps:

1. Use `git add` to stage files if needed
2. Analyze the git diff to understand what changed
3. Determine the appropriate conventional commit type and matching gitmoji:
   - `✨ feat`: New feature or functionality added
   - `🐛 fix`: Bug fix
   - `📝 docs`: Documentation changes only
   - `💄 style`: Code style/formatting changes (UI/cosmetic)
   - `♻️ refactor`: Code refactoring without changing functionality
   - `⚡ perf`: Performance improvements
   - `✅ test`: Adding or updating tests
   - `👷 build`: Build system or dependency changes
   - `💚 ci`: CI/CD configuration changes
   - `🔧 chore`: Other changes (tooling, configs, etc.)
   - `🚧 wip`: Work in progress
   - `🔥 remove`: Removing code or files
4. Craft a concise, descriptive commit message with appropriate scope
5. Use `git commit` with the format: `<emoji> <type>(<scope>): <description>`

The commit message should:

- Start with the appropriate gitmoji emoji
- Have a clear scope (e.g., module name, component)
- Be concise but descriptive
- Focus on the "why" not the "what"
- Follow the format exactly as shown in recent commits

Example: `✨ feat(segcheck): Add visualization for segmentation quality`
