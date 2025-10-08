---
allowed-tools: Bash(nf-test:*)
description: Run nf-test for a Nextflow module/subworkflow with snapshot update
---

## Your task

Run nf-test for the specified Nextflow module or subworkflow with the docker profile and snapshot update.

**User provided test path:** {{prompt}}

### Steps:

1. Parse the user's input to extract the path to the main.nf file
2. Convert the main.nf path to the corresponding test file path:
   - If user provides: `modules/local/cellprofiler/segcheck/main.nf`
   - Test file should be: `modules/local/cellprofiler/segcheck/tests/main.nf.test`
   - Pattern: Replace `main.nf` with `tests/main.nf.test`
3. Run nf-test with the following command from the project root:
   ```bash
   nf-test test --profile="+docker" <test-file-path> --updateSnapshot
   ```

### Examples:

**User input:** `modules/local/cellprofiler/segcheck/main.nf`
**Command to run:** `nf-test test --profile="+docker" ./modules/local/cellprofiler/segcheck/tests/main.nf.test --updateSnapshot`

**User input:** `modules/local/mymodule`
**Command to run:** `nf-test test --profile="+docker" ./modules/local/mymodule/tests/main.nf.test --updateSnapshot`

**User input:** `subworkflows/local/myworkflow/main.nf`
**Command to run:** `nf-test test --profile="+docker" ./subworkflows/local/myworkflow/tests/main.nf.test --updateSnapshot`

### Notes:

- Always run from the project root directory
- Use the `+docker` profile (with the + prefix)
- Always include `--updateSnapshot` flag
- If the test file doesn't exist, inform the user
- Show the full output of the nf-test command
