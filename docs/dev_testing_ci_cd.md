# Testing and CI/CD

## GitHub Actions Workflow

The pipeline uses GitHub Actions for continuous integration. Tests run automatically on pull requests (`.github/workflows/nf-test.yml`):

- **Trigger**: Pull requests (excluding docs, markdown, and image changes)
- **Container profile**: Docker only (Singularity is not tested)
- **Sharding**: Dynamically calculated as `min(affected_tests, 7)` - if your PR only changes one module, only that module's tests run
- **Change detection**: Only tests affected by changed files are executed (`nf-test --changed-since HEAD^`)

## NF-test Structure

Tests are organized at two levels:

| Level | Location | Purpose |
|-------|----------|---------|
| **Module tests** | `modules/local/*/tests/main.nf.test` | Unit tests for individual processes |
| **Pipeline tests** | `tests/main.nf.test` | End-to-end integration tests |

Each test file contains multiple test cases. Most include both a "real" test and a "stub" test:

- **Real tests**: Run actual containers (CellProfiler, Fiji) and process images
- **Stub tests**: Skip containers entirely—each process has a `stub:` block that creates empty output files with correct names, allowing fast validation of workflow wiring and conditional logic

| Module | Test Cases | Container |
|--------|------------|-----------|
| `cellprofiler/illumcalc` | 2 | CellProfiler |
| `cellprofiler/illumapply` | 2 | CellProfiler |
| `cellprofiler/segcheck` | 2 | CellProfiler |
| `cellprofiler/preprocess` | 2 | CellProfiler |
| `cellprofiler/combinedanalysis` | 2 | CellProfiler |
| `fiji/stitchcrop` | 3 | Fiji |
| `qc/montageillum` | 4 | Python (numpy/pillow) |
| `qc/barcodealign` | 2 | Python (pandas) |
| `qc/preprocess` | 2 | Python (pandas) |
| `tests/main.nf.test` | 5 | Full pipeline |
| **Total** | **26** | |

The pipeline tests in `tests/main.nf.test` cover different QC gate scenarios:

- `qc_passed`: Full run with both QC flags true
- `stub`: Workflow logic without containers
- `stub_painting_qc_false`: Verifies combined analysis is skipped
- `stub_barcoding_qc_false`: Verifies combined analysis is skipped
- `stub_both_qc_false`: Verifies pipeline stops at QC phase

## Handling Non-Reproducible Outputs

Image processing outputs (CellProfiler, Fiji) have non-reproducible checksums due to floating point operations, compression variations, and metadata differences. The pipeline handles this in two ways:

**1. Global ignore file** (`tests/.nftignore`):

```text
# Ignore all image types with unstable checksums
*.tiff
*.tif
*.npy
*.png
*.csv
*.html
```

**2. File existence assertions** in test files (see `modules/local/cellprofiler/combinedanalysis/tests/main.nf.test`):

```groovy
// Exclude specific files from snapshot, check existence instead
process.out.csv_stats.get(0).get(1).findAll {
    file(it).name != "Experiment.csv" &&
    file(it).name != "Image.csv"
}
// Then assert file exists separately
{ assert process.out.csv_stats.get(0).get(1).any { file(it).name == "Experiment.csv" } }
```

## Updating Snapshots

**When to update snapshots:**

- Adding/removing output files or directories
- Changing output file structure or naming
- Modifying which processes run (affects task counts)
- Upgrading tools that change output format

**When you DON'T need to update snapshots:**

- Version bumps (Nextflow and pipeline versions are excluded from comparison)
- Refactoring code that doesn't change outputs
- Documentation changes

When intentionally changing outputs, update snapshots using **GitHub Codespaces** (recommended for macOS users):

```bash
# Create a codespace with enough resources (need 3+ CPUs for FIJI processes)
gh codespace create --repo broadinstitute/nf-pooled-cellpainting --branch dev --machine largePremiumLinux

# Open in browser
gh codespace code --codespace <name> --web

# Inside the codespace, run tests with snapshot update
nf-test test tests/main.nf.test --profile debug,test,docker --update-snapshot

# Review changes, commit, and push
git diff tests/main.nf.test.snap
git add tests/main.nf.test.snap
git commit -m "fix: regenerate snapshots"
git push

# Delete codespace when done (to avoid charges)
gh codespace delete --codespace <name>
```

!!! warning "Local macOS Limitations"
    Running `nf-test test --update-snapshot` locally on macOS may fail due to `workflow.trace` not being populated correctly with Nextflow edge versions. Use GitHub Codespaces instead.

This overwrites existing `.nf.test.snap` files. Review the diff carefully before committing.
