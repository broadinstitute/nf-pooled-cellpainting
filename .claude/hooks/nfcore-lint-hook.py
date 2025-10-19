#!/usr/bin/env python3
import json
import subprocess
import sys
import os
from pathlib import Path

def is_nfcore_pipeline() -> bool:
    """Check if current directory is an nf-core pipeline"""
    # Check for nf-core specific files
    indicators = [
        '.nf-core.yml',
        'nf-core-pipeline.yml',
        '.github/workflows/ci.yml'  # nf-core CI
    ]

    for indicator in indicators:
        if os.path.exists(indicator):
            return True

    # Check if main.nf has nf-core comments
    if os.path.exists('main.nf'):
        try:
            with open('main.nf', 'r') as f:
                content = f.read()
                if 'nf-core' in content.lower():
                    return True
        except Exception:
            pass

    return False

def run_nfcore_lint() -> dict:
    """Run nf-core pipelines lint"""
    try:
        result = subprocess.run(
            ['nf-core', 'pipelines', 'lint', '.'],
            capture_output=True,
            text=True,
            timeout=60,
            check=False
        )

        return {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        }

    except subprocess.TimeoutExpired:
        return {'error': 'nf-core lint timed out after 60 seconds'}
    except FileNotFoundError:
        return {'error': 'nf-core command not found. Install with: pip install nf-core'}
    except Exception as e:
        return {'error': f'Failed to run nf-core lint: {str(e)}'}

def parse_lint_results(output: str) -> dict:
    """Parse nf-core lint output to extract summary"""
    summary = {
        'passed': 0,
        'warned': 0,
        'failed': 0,
        'issues': []
    }

    lines = output.split('\n')

    for line in lines:
        # Count test results
        if '✔' in line or 'PASSED' in line:
            summary['passed'] += 1
        elif '⚠' in line or 'WARNING' in line or 'WARN' in line:
            summary['warned'] += 1
            # Capture warning details
            if line.strip():
                summary['issues'].append(line.strip())
        elif '✗' in line or 'FAILED' in line or 'FAIL' in line:
            summary['failed'] += 1
            # Capture failure details
            if line.strip():
                summary['issues'].append(line.strip())

    return summary

try:
    input_data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
    sys.exit(1)

# Check if this is an nf-core pipeline
if not is_nfcore_pipeline():
    # Not an nf-core pipeline, skip silently
    sys.exit(0)

# Run nf-core lint
print("🔍 Running nf-core pipelines lint...", file=sys.stderr)

result = run_nfcore_lint()

if 'error' in result:
    # nf-core not available or failed, provide advisory
    print(json.dumps({
        "reason": f"⚠️  nf-core lint: {result['error']}",
        "suppressOutput": False,
        "continue": True
    }))
    sys.exit(0)

# Parse results
lint_summary = parse_lint_results(result['stdout'])

# Prepare feedback
feedback_parts = ["=== nf-core Lint Results ==="]

if lint_summary['passed'] > 0:
    feedback_parts.append(f"✅ Passed: {lint_summary['passed']} tests")
if lint_summary['warned'] > 0:
    feedback_parts.append(f"⚠️  Warnings: {lint_summary['warned']}")
if lint_summary['failed'] > 0:
    feedback_parts.append(f"❌ Failed: {lint_summary['failed']}")

# Show top issues (limit to avoid overwhelming output)
if lint_summary['issues']:
    feedback_parts.append("\nKey Issues:")
    for issue in lint_summary['issues'][:10]:
        feedback_parts.append(f"  • {issue}")

    if len(lint_summary['issues']) > 10:
        feedback_parts.append(f"\n... and {len(lint_summary['issues']) - 10} more issues")

feedback_parts.append("\n💡 Run 'nf-core pipelines lint' for full details")

feedback = "\n".join(feedback_parts)

# Provide advisory feedback (non-blocking)
if lint_summary['failed'] > 0 or lint_summary['warned'] > 0:
    print(json.dumps({
        "reason": feedback,
        "suppressOutput": False,
        "continue": True
    }))
else:
    # All tests passed
    print(json.dumps({
        "reason": "✅ nf-core lint: All tests passed!",
        "suppressOutput": False,
        "continue": True
    }))

sys.exit(0)
