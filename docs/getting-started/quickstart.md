# Quick Start

This guide walks through running the pipeline with example data.

## Basic Execution

### Minimal Command

```bash
nextflow run main.nf \
  --input samplesheet.csv \
  --barcodes barcodes.csv \
  --outdir results \
  --painting_illumcalc_cppipe pipelines/painting_illumcalc.cppipe \
  --painting_illumapply_cppipe pipelines/painting_illumapply.cppipe \
  --painting_segcheck_cppipe pipelines/painting_segcheck.cppipe \
  --barcoding_illumcalc_cppipe pipelines/barcoding_illumcalc.cppipe \
  --barcoding_illumapply_cppipe pipelines/barcoding_illumapply.cppipe \
  --barcoding_preprocess_cppipe pipelines/barcoding_preprocess.cppipe \
  --combinedanalysis_cppipe pipelines/combinedanalysis.cppipe \
  --callbarcodes_plugin 'https://example.com/callbarcodes.py' \
  --compensatecolors_plugin 'https://example.com/compensatecolors.py' \
  -profile docker
```

### With Resume

Nextflow caches completed tasks. Resume after interruption:

```bash
nextflow run main.nf --input samplesheet.csv ... -resume
```

## Typical Workflow

### 1. Initial QC Run

Run without QC gates enabled (default):

```bash
nextflow run main.nf \
  --input samplesheet.csv \
  --barcodes barcodes.csv \
  --outdir results \
  [... pipeline paths ...] \
  -profile docker
```

This executes through illumination correction and QC checks but **stops before stitching**.

### 2. Review QC Outputs

Check the QC montages and statistics in the `results/` directory:

- `qc/montage_illum/`: Illumination correction previews
- `qc/montage_segcheck/`: Segmentation quality checks
- `qc/barcode_align/`: Barcode alignment metrics

### 3. Enable QC Gates

After manual review, enable progression:

```bash
nextflow run main.nf \
  --input samplesheet.csv \
  --barcodes barcodes.csv \
  --outdir results \
  [... pipeline paths ...] \
  --qc_painting_passed true \
  --qc_barcoding_passed true \
  -profile docker \
  -resume
```

This continues from where it stopped and runs:

- Image stitching and cropping
- Combined analysis
- Final outputs

## Example Samplesheet

Create `samplesheet.csv`:

```csv
path,arm,batch,plate,well,channels,site,cycle,n_frames
/data/painting/,painting,batch1,P001,A01,DAPI-GFP-RFP-Cy5-Cy3,1,,4
/data/painting/,painting,batch1,P001,A01,DAPI-GFP-RFP-Cy5-Cy3,2,,4
/data/barcoding/,barcoding,batch1,P001,A01,Cy3-Cy5,1,1,4
/data/barcoding/,barcoding,batch1,P001,A01,Cy3-Cy5,1,2,4
/data/barcoding/,barcoding,batch1,P001,A01,Cy3-Cy5,1,3,4
```

!!! note - `painting` rows have empty `cycle` column - `barcoding` rows must have `cycle` values - `path` should point to directory containing TIFF images

## Understanding Outputs

After successful execution, find outputs in `results/`:

```
results/
├── painting/
│   ├── illum/              # Illumination functions (.npy)
│   ├── corrected/          # Corrected TIFF images
│   └── stitched_cropped/   # Stitched images
├── barcoding/
│   ├── illum/
│   ├── corrected/
│   ├── preprocessed/       # Barcode-called images
│   └── stitched_cropped/
├── combined/
│   └── analysis/           # Final segmentation and measurements
├── qc/
│   ├── montage_illum/
│   ├── montage_segcheck/
│   ├── montage_preprocess/
│   ├── montage_stitchcrop/
│   └── barcode_align/
└── csvs/
    └── load_data/          # All generated load_data.csv files
```

## Common Issues

### Container Not Found

Ensure Docker/Singularity is running:

```bash
docker ps  # For Docker
singularity --version  # For Singularity
```

### Out of Memory

Increase JVM memory:

```bash
export NXF_OPTS='-Xms1g -Xmx4g'
```

### Plugin Download Failures

Check plugin URLs are accessible:

```bash
curl -I https://example.com/callbarcodes.py
```

## Next Steps

- [Parameters Guide](../usage/parameters.md) - Fine-tune pipeline behavior
- [Running on Seqera Platform](../usage/seqera-platform.md) - Scale to cloud/HPC
- [Architecture](../developer/architecture.md) - Understand pipeline internals
