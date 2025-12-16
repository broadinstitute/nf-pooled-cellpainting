# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

nf-pooled-cellpainting is a Nextflow pipeline for processing optical pooled screening (OPS) data, combining Cell Painting phenotypic analysis with sequencing-by-synthesis barcoding. The pipeline processes microscopy images through two parallel arms and produces phenotypic measurements for each identified cell.

## Development Setup

**Note**: The pipeline runs entirely in Docker containers (CellProfiler, Fiji, etc.). End users only need Nextflow + Docker. This section covers the **developer environment** for working on the pipeline code.

This project uses [pixi](https://pixi.sh) to manage developer tools (nextflow, nf-test, nf-core, mkdocs). Install pixi, then:

```bash
pixi install          # Install developer tools
pixi shell            # Activate environment (recommended for interactive work)
```

## Build and Test Commands

All commands assume you're in a `pixi shell` or prefixed with `pixi run`.

```bash
# Quick local tests (recommended for development)
pixi run test-illumcalc  # Illumination calculation module (~1 min)
pixi run test-segcheck   # Segmentation check module (~45s)

# Run all nf-test tests (modules + full pipeline, slow)
pixi run test

# Dry-run to check workflow logic without running containers
pixi run preview

# Run the pipeline with test profile
pixi run pipeline

# Lint the pipeline
pixi run lint

# Update schema after adding parameters
pixi run build-schema

# Clean up work directories
pixi run clean-work      # Remove work, results, .nextflow
pixi run clean-all-work  # Also remove .nf-test cache

# Documentation
pixi run serve-docs      # Serve docs locally
pixi run build-docs      # Build docs

# List all available tasks
pixi task list
```

### Without pixi (direct commands)

```bash
nextflow run main.nf -profile test,docker --outdir results -preview
nf-test test modules/local/cellprofiler/illumcalc/tests/main.nf.test --profile debug,test,docker
nf-core pipelines lint
```

## Architecture

### Pipeline Structure

The pipeline has two parallel processing arms that run independently:

1. **Cell Painting arm** (`subworkflows/local/cellpainting/main.nf`):
   - Illumination calculation → Illumination apply → Segmentation check → Stitch & crop
   - Uses CellProfiler for image processing and Fiji for stitching
   - Outputs QC montages at each step

2. **Barcoding arm** (`subworkflows/local/barcoding/main.nf`):
   - Illumination calculation → Illumination apply → Barcode preprocessing → Stitch & crop
   - Additional QC for barcode alignment and cycle correlation
   - Groups images by cycle for illumination correction

3. **Combined analysis** (`workflows/nf-pooled-cellpainting.nf:118`):
   - Only runs when both `qc_painting_passed` and `qc_barcoding_passed` are `true`
   - Merges cropped images from both arms for final analysis

### Key Entry Points

- `main.nf` - Pipeline entry point, handles initialization and completion
- `workflows/nf-pooled-cellpainting.nf` - Main workflow orchestration
- `nextflow.config` - Global parameters and profile definitions

### Module Organization

- `modules/local/cellprofiler/` - CellProfiler processing steps (illumcalc, illumapply, segcheck, preprocess, combinedanalysis)
- `modules/local/fiji/stitchcrop/` - Image stitching and cropping with Fiji
- `modules/local/qc/` - QC modules (montageillum, barcodealign, preprocess)
- `modules/nf-core/multiqc/` - MultiQC reporting

### Data Flow Patterns

Channels are grouped by different keys depending on the processing step:

- **Illumination calculation**: Groups by `batch_plate` (painting) or `batch_plate_cycle` (barcoding)
- **Illumination apply**: Groups by site or well (controlled by `barcoding_illumapply_grouping`)
- **Stitch & crop**: Regroups all sites back to well level

### QC Checkpoints

The pipeline supports manual QC review at checkpoints. Set these parameters to proceed past QC:

- `--qc_painting_passed true` - Continue past painting QC to stitching/cropping
- `--qc_barcoding_passed true` - Continue past barcoding QC to stitching/cropping

Both must be true for combined analysis to run.

## Testing Notes

- Image processing outputs (CellProfiler, Fiji) have non-reproducible checksums due to floating point operations
- Snapshot tests verify file names and task counts rather than file contents
- Module tests (`modules/local/*/tests/`) are faster than full pipeline tests
- Full pipeline test (`tests/main.nf.test`) takes 5-10+ minutes as it runs actual CellProfiler/Fiji processing
- Test data is fetched from S3: `s3://nf-pooled-cellpainting-sandbox/`
- NullPointerException warnings from nf-test on macOS are expected (workflow.trace issue)
- Tests must be tagged `fast` or `slow` (nf-test doesn't support negation like `!slow`)
- New tests need `tag "fast"` or they won't run in CI fast mode

## Configuration

- `conf/base.config` - Default resource allocations
- `conf/modules.config` - Module-specific publish directories and options
- `conf/test.config` - Test profile with minimal dataset
- Container profiles: `docker`, `singularity`, `podman`, `apptainer`
- Use `-profile arm` with docker for Apple Silicon Macs

## Required Inputs

- `--input` - Samplesheet CSV with image paths and metadata
- `--barcodes` - Barcode reference CSV
- `--outdir` - Output directory
- CellProfiler pipeline files (`.cppipe`) for each processing step

## nf-core Conventions

This pipeline follows nf-core conventions. See [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md) for contribution guidelines and coding standards.

**Quick checklist** (verify before PR):

- [ ] Pinned containers, no host dependencies
- [ ] Resource labels used (not hard-coded cpus/memory)
- [ ] Schema updated (`pixi run build-schema`)
- [ ] Lint passes (`pixi run lint`)
- [ ] Tests pass (`pixi run test`)
