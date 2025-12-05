# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

nf-pooled-cellpainting is a Nextflow pipeline for processing optical pooled screening (OPS) data, combining Cell Painting phenotypic analysis with sequencing-by-synthesis barcoding. The pipeline processes microscopy images through two parallel arms and produces phenotypic measurements for each identified cell.

## Build and Test Commands

```bash
# Run the pipeline with test profile
nextflow run main.nf -profile test,docker --outdir results

# Run all nf-test tests
nf-test test --profile debug,test,docker --verbose

# Run a specific test file
nf-test test tests/main.nf.test --profile debug,test,docker --verbose

# Run tests for a specific module
nf-test test modules/local/cellprofiler/illumcalc/tests/main.nf.test --profile debug,test,docker

# Run stub tests (faster, no actual processing)
nf-test test tests/main.nf.test --profile debug,test,docker -stub

# Lint the pipeline
nf-core pipelines lint .

# Update schema after adding parameters
nf-core pipelines schema build
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
- Use `-stub` for faster tests that skip actual image processing
- Test data is fetched from S3: `s3://nf-pooled-cellpainting-sandbox/`

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
