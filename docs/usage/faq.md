# Frequently Asked Questions (FAQ)

## General

### How do I resume a failed run?

Nextflow has a built-in resume feature. Simply add `-resume` to your command line. Nextflow will check the cache and only run the steps that haven't completed successfully or have changed.

```bash
nextflow run seqera-services/nf-pooled-cellpainting ... -resume
```

### How much memory do I need?

This depends heavily on the size of your images and the number of tiles.

- **Illumination correction**: Generally low memory (~4-8 GB).
- **Stitching**: High memory. For large wells (e.g., 10x10 grids), you might need 32GB+ RAM.
- **Combined Analysis**: Moderate memory, but CPU intensive.

If you encounter `OutOfMemoryError`, try increasing the memory for the specific process in a custom config file:

```groovy
process {
    withName: 'FIJI_STITCHCROP' {
        memory = '64.GB'
    }
}
```

## Input Data

### My images are not being found. Why?

Check your `samplesheet.csv`. The `path` column must be an **absolute path** or a valid S3 URI. Relative paths often cause issues, especially when running with Docker or Singularity where volume mounts might differ.

### Can I run the pipeline with only Cell Painting data?

Yes! The pipeline is designed to be modular. If you only provide Cell Painting entries in your samplesheet, the Barcoding arm will simply not run. However, the final "Combined Analysis" step which links barcodes to cells will obviously not happen.

## Troubleshooting

### The pipeline stops after QC. Is it broken?

No, this is a feature! The pipeline is designed to stop after generating QC images so you can verify them before proceeding to the expensive stitching steps. To continue, you must explicitly set:

```bash
--qc_painting_passed true --qc_barcoding_passed true
```

### I see "command not found" errors.

Ensure you are using a profile that provides the software dependencies, such as `-profile docker`, `-profile singularity`, or `-profile conda`. If running locally without containers, you must have all tools (CellProfiler, Fiji, etc.) installed in your PATH.
