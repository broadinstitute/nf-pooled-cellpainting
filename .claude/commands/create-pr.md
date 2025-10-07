---
description: Create a PR with emoji-rich, concise messages
---

Create a pull request for the current branch with these requirements:

1. Analyze all commits and changes in the current branch vs dev
2. Generate a concise PR title with conventional commits emoji prefix:
   - ✨ feat: for new features
   - 🐛 fix: for bug fixes
   - 📝 docs: for documentation
   - 💄 style: for formatting/style changes
   - ♻️ refactor: for code refactoring
   - ⚡️ perf: for performance improvements
   - ✅ test: for tests
   - 🔧 chore: for maintenance/tooling
   - 🔨 build: for build system changes
   - 👷 ci: for CI/CD changes
   - ⏪️ revert: for reverts

3. Create a PR body with:
   - **Summary**: 2-3 concise bullet points explaining what changed and why
   - **Changes**: Brief list of key modifications
   - **Test Plan**: Simple checklist for testing

4. Keep the entire PR message concise but informative - aim for clarity over verbosity

5. Create the PR using `gh pr create --base dev`
