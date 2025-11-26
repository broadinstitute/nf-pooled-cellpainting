# Frequently Asked Questions (FAQ)

## How do I resume a failed run?

Nextflow has a built-in resume feature. Simply add `-resume` to your command line. Nextflow will check the cache and only run the steps that haven't completed successfully or have changed.

```bash
nextflow run seqera-services/nf-pooled-cellpainting ... -resume
```

## How much memory and cpu do I need?

This depends heavily on the size of your images and the number of tiles. Some Cellprofiler steps of the pipeline operate serially on images and therefore don't increase memory usage linearly with the number of images. Others do load multiple images into memory at once, which can be a problem for large wells. In general the pipeline has relatively low resource demands, with most processes request 1 cpu (since cellprofiler isn't multithreaded in headless mode) and 2 GB of memory.

- **Illumination correction**: Generally low memory (~4-8 GB).
- **Stitching**: High memory. For large wells (e.g., 10x10 grids), you might need 32GB+ RAM.
- **Combined Analysis**: Moderate memory, but CPU intensive.

If you encounter exit codes 137 (`OutOfMemoryError`) frequently and task get resubmitted with more memory, try increasing the memory for the specific process in a custom config file. Here is an example for the stitching process. Include this snippet into your Nextflow config (either on Seqera Platform, a local config file or even in your repository config if you want it applied to all pipeline runs):

```groovy
process {
    withName: 'FIJI_STITCHCROP' {
        memory = '64.GB'
    }
}
```

## How long does a typical run take?

The runtime depends on the number of images and the number of tiles. It's difficult to give specific numbers as this is dataset specific, but here are some numbers for datasets we have tested:

- `-profile test`: This small test dataset takes around 5-10 minutes on AWS Batch and around XX minutes locally.
- `-profile test_full`: This dataset consists of 1 well and 1025 sites. It takes around ... TODO
- `-profile test_cpg0032`: This dataset consists of 2 full wells and 12 cycles of barcoding and is substantially larger than the other two datasets shown here.

## My images are not being found. Why?

Check your `samplesheet.csv`. The `path` column must be an **absolute path** or a valid URI to cloud storage. Relative paths often cause issues, especially when running with Docker or Singularity where volume mounts might differ.

## Can I run the pipeline with only Cell Painting data?

Yes! The pipeline is designed to be modular. If you only provide Cell Painting entries in your samplesheet, the Barcoding arm will simply not run. However, the final "Combined Analysis" step which links barcodes to cells will obviously not happen.

## The pipeline stops after QC. Is it broken?

No, this is a feature, not a bug! The pipeline is designed to stop after generating QC images so you can verify them before proceeding to the expensive stitching steps. To continue, you must explicitly set:

```bash
--qc_painting_passed --qc_barcoding_passed
```

## I see "command not found" errors.

Ensure you are using the docker profile if running locally `-profile docker`. On AWS docker is the default container engine and you don't need to specify the docker profile explicitly.
