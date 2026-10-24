# Frequently Asked Questions (FAQ)

## How do I resume a failed run?

Nextflow has a built-in resume feature. Simply add `-resume` to your command line. Nextflow will check the cache and only run the steps that haven't completed successfully or have changed.

```bash
nextflow run broadinstitute/nf-pooled-cellpainting ... -resume
```

## How much memory and cpu do I need?

This depends heavily on the size of your images and the number of tiles. Some Cellprofiler steps of the pipeline operate serially on images and therefore don't increase memory usage linearly with the number of images. Others do load multiple images into memory at once, which can be a problem for large wells. In general the pipeline has relatively low resource demands, with most processes request 1 CPU and 2 GB of memory.

Memory-intensive tasks are:

| Process | Memory Needed |
|---------|---------------|
| FIJI_STITCHCROP | 36+ GB |
| CELLPROFILER_PREPROCESS | 8 GB |
| CELLPROFILER_COMBINEDANALYSIS | 32+ GB |

The `STITCH_ALIGN_CROP` entrypoint does not use Fiji. Its processes request: `STITCH` and `CROP` 6 CPUs / 12 GB, `ALIGN_INTRAARM` and `ALIGN_COMBINED` 4 CPUs / 12 GB, `CELLPROFILER_PREPROCESS_STITCHALIGNCROP` 12 GB and `CELLPROFILER_COMBINEDANALYSIS_STITCHALIGNCROP` 40 GB (see `conf/base.config`). Override them with `withName:` the same way as below.

All of these processes require increased amounts of memory, with COMBINEDANALYSIS needing the most. In our tests with cpg0032, CELLPROFILER_COMBINEDANALYSIS needed 32GB of RAM provisioned to not fail. If you encounter exit codes 137 (`OutOfMemoryError`) frequently and tasks get resubmitted with more memory, try increasing the memory for the specific process in a custom config file. Here is an example for the stitching process. Include this snippet into your Nextflow config (either on Seqera Platform, a local config file or even in your repository config if you want it applied to all pipeline runs). Be aware that increasing resource configuration for your pipeline on AWS will generally lead to provisioning of larger and more expensive EC2 instances!

```groovy
process {
    withName: 'FIJI_STITCHCROP' {
        memory = '64.GB'
    }
}
```

## How long does a typical run take?

The runtime depends on the number of images and the number of tiles. It's difficult to give specific numbers as this is dataset specific, but here are some numbers for datasets we have tested:

| Profile | Description | Runtime |
|---------|-------------|---------|
| `test` | Minimal dataset | 5-10 minutes |
| `test_full` | 1 well, multiple sites | Several hours |
| `test_cpg0032` | 2 wells, 12 cycles | 9-10 hours |

## My images are not being found. Why?

Check your `samplesheet.csv`. The `path` column must be an **absolute path** or a valid URI to cloud storage. Relative paths often cause issues, especially when running with Docker or Singularity where volume mounts might differ. Paths must be:

- Absolute paths (not relative)
- Valid S3 URIs for cloud execution
- Accessible from the execution environment

## The pipeline stops after QC. Is it broken?

No, this is a feature, not a bug! The pipeline is designed to stop after generating QC images so you can verify them before proceeding to the expensive stitching steps. To continue, you must explicitly set:

```bash
--qc_painting_passed --qc_barcoding_passed
```

## I see "command not found" errors

Ensure you are using the docker profile if running locally `-profile docker`. On AWS, Docker is the default container engine and you don't need to specify the docker profile explicitly.

## I get "Missing output file(s) expected by process"

If you see an error like:

```
Caused by:
  Missing output file(s) `stitched_images/*.tiff` expected by process `POOLED_CELLPAINTING:CELLPAINTING:FIJI_STITCHCROP (Batch1_Plate1_A1)`
```

This means the process ran (exit code 0) but didn't produce the files Nextflow expected. Unlike a crash, the tool finished without error but simply didn't create any output. Common causes:

- **Tool-specific problems**: The underlying tool (CellProfiler, FIJI, etc.) ran but had nothing to process or encountered a silent failure. In CellProfiler this is sometimes caused when images are flagged. Check the `.command.log` file in the task work directory for warnings.

To debug, navigate to the failed task's work directory (shown in the error) and inspect:

- `.command.log` - stdout/stderr from the tool
- `.command.sh` - the exact command that ran
- `.command.err` - any error output

The same applies to the `STITCH_ALIGN_CROP` entrypoint's processes (e.g. `STITCH_PAINTING`, `CROP_BARCODING`, `ALIGN_COMBINED`). `stitch.py` prints `WARNING:` lines to `.command.log` for sites missing from the well layout.

## How do I know if my QC passed?

After Phase 1 completes, check the QC outputs in `results/workspace/qc_reports/`. Look for:

- **Illumination montages**: Should show smooth, gradual intensity variations - not patchy or irregular patterns.
- **Segmentation previews**: Cell and nucleus outlines should accurately trace the boundaries of actual cells. Look for over-segmentation (one cell split into many) or under-segmentation (multiple cells merged).
- **Alignment reports** (barcoding): Check that pixel shifts are small and consistent across the field of view.

## Can I process just one arm (painting or barcoding)?

Yes. Simply omit the other arm from your samplesheet. If you only include painting images, the barcoding subworkflow won't run. However, the Combined Analysis step requires both arms, so you'll only get the intermediate outputs.

## Where can I find example CellProfiler pipelines?

The `test` profile and `cpg0032` profile both include working example pipelines. You can find these cppipe files in the `/assets/` subfolders `/cellprofiler` and `cpg0032_test_cppipes` respectively.
