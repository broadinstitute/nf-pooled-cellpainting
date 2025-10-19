#!/usr/bin/env python3
import json
import subprocess
import sys
import os
from pathlib import Path

def find_repo_root(file_path: str) -> str:
    """Find git repository root from file path"""
    current = Path(file_path).parent.absolute()

    while current != current.parent:
        if (current / '.git').exists():
            return str(current)
        current = current.parent

    return None

def has_precommit_config(repo_root: str) -> bool:
    """Check if .pre-commit-config.yaml exists"""
    config_path = Path(repo_root) / '.pre-commit-config.yaml'
    return config_path.exists()

def run_precommit(file_path: str, repo_root: str) -> dict:
    """Run pre-commit on specific file"""
    try:
        # Change to repo root to run pre-commit
        result = subprocess.run(
            ['pre-commit', 'run', '--files', file_path],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False
        )

        return {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        }

    except FileNotFoundError:
        return {'error': 'pre-commit command not found. Install with: pip install pre-commit'}
    except Exception as e:
        return {'error': f'Failed to run pre-commit: {str(e)}'}

def parse_precommit_output(output: str) -> list:
    """Parse pre-commit output to extract hook results"""
    lines = output.strip().split('\n')
    issues = []

    for line in lines:
        if 'Failed' in line or 'Passed' in line or 'Skipped' in line:
            issues.append(line.strip())

    return issues

try:
    input_data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
    sys.exit(1)

tool_name = input_data.get("tool_name", "")
tool_input = input_data.get("tool_input", {})
file_path = tool_input.get("file_path", "")

# Only process Write/Edit/MultiEdit tools
if tool_name not in ["Write", "Edit", "MultiEdit"]:
    sys.exit(0)

# Skip if no file path
if not file_path or not os.path.exists(file_path):
    sys.exit(0)

# Find repository root
repo_root = find_repo_root(file_path)
if not repo_root:
    # Not in a git repository, skip
    sys.exit(0)

# Check for pre-commit config
if not has_precommit_config(repo_root):
    # No pre-commit config, skip silently
    sys.exit(0)

# Run pre-commit
filename = os.path.basename(file_path)
result = run_precommit(file_path, repo_root)

if 'error' in result:
    # Pre-commit not available, just warn
    print(json.dumps({
        "reason": f"⚠️  {filename}: {result['error']}",
        "suppressOutput": False,
        "continue": True
    }))
    sys.exit(0)

# Check results
if result['returncode'] == 0:
    # All hooks passed
    print(f"✅ {filename}: pre-commit checks passed")
    print(json.dumps({
        "suppressOutput": True,
        "continue": True
    }))
    sys.exit(0)
else:
    # Some hooks failed
    hook_results = parse_precommit_output(result['stdout'])

    feedback_parts = [f"❌ {filename}: pre-commit checks failed"]

    if hook_results:
        feedback_parts.append("\nHook Results:")
        for hook_result in hook_results:
            feedback_parts.append(f"  • {hook_result}")

    if result['stderr']:
        feedback_parts.append(f"\nErrors:\n{result['stderr']}")

    feedback = "\n".join(feedback_parts)

    # Block the operation
    print(json.dumps({
        "decision": "block",
        "reason": feedback,
        "continue": True
    }))
    sys.exit(2)
