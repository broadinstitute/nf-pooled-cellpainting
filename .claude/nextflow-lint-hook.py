#!/usr/bin/env python3
import json
import subprocess
import sys
import os

def should_lint_file(file_path: str) -> bool:
    """Check if file should be linted"""
    return file_path.endswith('.nf') or file_path.endswith('nextflow.config')

def run_nextflow_lint(file_path: str) -> dict:
    """Run nextflow lint and return structured results"""
    try:
        result = subprocess.run(
            ['nextflow', 'lint', '-o', 'json', file_path],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.stdout:
            return json.loads(result.stdout)
        return {"errors": [], "summary": {"errors": 0}}
        
    except subprocess.CalledProcessError:
        return {"error": "Failed to run nextflow lint"}
    except json.JSONDecodeError:
        return {"error": "Invalid JSON output from nextflow lint"}
    except FileNotFoundError:
        return {"error": "nextflow command not found"}

try:
    input_data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
    sys.exit(1)

tool_name = input_data.get("tool_name", "")
tool_input = input_data.get("tool_input", {})
file_path = tool_input.get("file_path", "")

# Only process relevant tools and file types
if tool_name not in ["Write", "Edit", "MultiEdit"] or not should_lint_file(file_path):
    sys.exit(0)

# Run lint
lint_result = run_nextflow_lint(file_path)

if "error" in lint_result:
    print(f"Nextflow lint error: {lint_result['error']}", file=sys.stderr)
    sys.exit(1)

# Process results
error_count = lint_result.get("summary", {}).get("errors", 0)
filename = os.path.basename(file_path)

if error_count == 0:
    print(f"✅ {filename}: Nextflow lint passed")
    # Use JSON output for structured feedback to Claude
    print(json.dumps({
        "suppressOutput": True,
        "continue": True
    }))
else:
    # Format errors for Claude with structured feedback
    error_summary = f"⚠️  {filename}: {error_count} lint error(s)"
    error_details = []
    
    for error in lint_result.get("errors", []):
        line = error.get("startLine", "?")
        col = error.get("startColumn", "?")
        msg = error.get("message", "Unknown error")
        error_details.append(f"  Line {line}:{col} - {msg}")
    
    feedback = error_summary + "\n" + "\n".join(error_details)
    
    # Use JSON output to provide structured feedback to Claude
    print(json.dumps({
        "decision": "block",
        "reason": feedback,
        "continue": True
    }))
    
    # Exit with code 2 to trigger Claude feedback
    sys.exit(2)