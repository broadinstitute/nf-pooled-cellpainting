#!/usr/bin/env python3
"""
Claude Code hook: Run pre-commit and nf-core lint before git commits
Executes both 'pre-commit run --all-files' and 'nf-core lint' before allowing git commit operations
"""

import json
import sys
import subprocess
from pathlib import Path


def main():
    # Read JSON input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        # No input or invalid JSON - exit gracefully
        sys.exit(0)

    # Extract relevant fields
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    cwd = input_data.get("cwd", ".")

    # Only run for Bash commands
    if tool_name != "Bash":
        sys.exit(0)

    # Get the command being run
    command = tool_input.get("command", "")

    # Check if this is a git commit command
    if not is_git_commit(command):
        sys.exit(0)

    # Run pre-commit first
    print("🔍 Running pre-commit checks before commit...")
    if not run_precommit(cwd):
        sys.exit(1)

    # Then run nf-core lint
    print("\n🔬 Running nf-core lint checks before commit...")
    if not run_nfcore_lint(cwd):
        sys.exit(1)

    print("\n✅ All checks passed! Proceeding with commit...")
    sys.exit(0)


def run_precommit(cwd: str) -> bool:
    """Run pre-commit and return True if successful."""
    try:
        result = subprocess.run(
            ["pre-commit", "run", "--all-files"],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
            cwd=cwd
        )

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        if result.returncode == 0:
            print("✅ Pre-commit checks passed!")
            return True
        else:
            print("❌ Pre-commit checks failed! Please fix the issues before committing.")
            print("\nTip: Run 'pre-commit run --all-files' manually to see and fix all issues.")
            return False

    except FileNotFoundError:
        print("⚠️  pre-commit not found. Install with: pip install pre-commit")
        print("Skipping pre-commit checks...")
        return True
    except subprocess.TimeoutExpired:
        print("⏱️  Pre-commit checks timed out (5 minutes)")
        return False
    except Exception as e:
        print(f"❌ Error running pre-commit: {e}")
        return False


def run_nfcore_lint(cwd: str) -> bool:
    """Run nf-core lint and return True if successful."""
    try:
        result = subprocess.run(
            ["nf-core", "pipelines" , "lint"],
            capture_output=True,
            text=True,
            timeout=120,  # 2 minutes timeout
            cwd=cwd
        )

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        if result.returncode == 0:
            print("✅ nf-core lint checks passed!")
            return True
        else:
            print("❌ nf-core lint checks failed! Please fix the issues before committing.")
            print("\nTip: Run 'nf-core pipelines lint' manually to see detailed issues.")
            return False

    except FileNotFoundError:
        print("⚠️  nf-core not found. Install with: pip install nf-core")
        print("Skipping nf-core lint checks...")
        return True
    except subprocess.TimeoutExpired:
        print("⏱️  nf-core lint checks timed out (2 minutes)")
        return False
    except Exception as e:
        print(f"❌ Error running nf-core lint: {e}")
        return False


def is_git_commit(command: str) -> bool:
    """Check if the command is a git commit operation."""
    # Look for git commit commands
    git_commit_patterns = [
        "git commit",
        "git-commit"
    ]

    command_lower = command.lower().strip()

    for pattern in git_commit_patterns:
        if pattern in command_lower:
            return True

    return False


if __name__ == "__main__":
    main()
