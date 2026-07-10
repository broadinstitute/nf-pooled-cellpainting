# Using Your Own Data: Run

## Running the Pipeline with CLI

Once your inputs are ready, run the pipeline pointing to your files. At the minimum, you need to specify the following:

```bash
cd broadinstitute/nf-pooled-cellpainting # or your repository clone
nextflow run . \
    --input samplesheet.csv \
    --barcodes barcodes.csv \
    --outdir results \
    --painting_illumcalc_cppipe your_painting_illumcalc_cppipe.cppipe \
    --painting_illumapply_cppipe your_painting_illumapply_cppipe.cppipe \
    --painting_segcheck_cppipe your_painting_segcheck_cppipe.cppipe \
    --barcoding_illumcalc_cppipe your_barcoding_illumcalc_cppipe.cppipe \
    --barcoding_illumapply_cppipe your_barcoding_illumapply_cppipe.cppipe \
    --barcoding_preprocess_cppipe your_barcoding_preprocess_cppipe.cppipe \
    --combinedanalysis_cppipe your_combinedanalysis_cppipe.cppipe \
    -profile docker
```

Note that there are many configurable parameters to this workflow. The minimal specification above uses the default values for all of the parameters not passed which is unlikely to be appropriate for your custom data. Instead, there are two alternative approaches. You can pass in all of the parameters that you want to be non-default directly into the run command. It might look something like this:

```bash
cd broadinstitute/nf-pooled-cellpainting # or your repository clone
nextflow run . \
    --input samplesheet.csv \
    --barcodes barcodes.csv \
    --outdir results \
    --painting_illumcalc_cppipe your_painting_illumcalc_cppipe.cppipe \
    --painting_illumapply_cppipe your_painting_illumapply_cppipe.cppipe \
    --painting_segcheck_cppipe your_painting_segcheck_cppipe.cppipe \
    --barcoding_illumcalc_cppipe your_barcoding_illumcalc_cppipe.cppipe \
    --barcoding_illumapply_cppipe your_barcoding_illumapply_cppipe.cppipe \
    --barcoding_preprocess_cppipe your_barcoding_preprocess_cppipe.cppipe \
    --combinedanalysis_cppipe your_combinedanalysis_cppipe.cppipe \
    --range_skip 4 \
    --painting_quarter_if_round false \
    --barcoding_quarter_if_round false \
    --painting_imperwell 80 --barcoding_imperwell 21 \
    --painting_rows 10 --barcoding_columns 5 \
    --painting_columns 10 --barcoding_columns 5 \
    --tileperside 5 --final_tile_size 2500 \
    --first_site_index 0 --phenix true \
    -profile docker
```

Alternatively, you can create a configuration file with your specific parameters and pass that configuration into the run command as a profile.

```bash
cd broadinstitute/nf-pooled-cellpainting # or your repository clone
nextflow run . -profile docker,experiment
```

Note that you will also need to append your config to the end of the `profiles` section in your `nextflow.config` file:

```json
profiles{
    ...
    experiment {
        includeConfig 'conf/experiment.config'
    }
}

Example `conf/experiment.config`:

```json
params {
    config_profile_name         = 'experiment'
    config_profile_description  = 'For a specific experiment'

    input                       = "path/to/samplesheet.csv"
    outdir                      = "path/to/output"
    barcodes                    = "path/to/Barcodes.csv"
    painting_illumcalc_cppipe   = "path/to/painting_illumcalc_cppipe.template"
    painting_illumapply_cppipe  = "path/to/painting_illumapply.cppipe"
    painting_segcheck_cppipe    = "path/to/painting_segcheck.cppipe"
    barcoding_illumcalc_cppipe  = "path/to/barcoding_illumcalc_cppipe.template"
    barcoding_illumapply_cppipe = "path/to/barcoding_illumapply.cppipe"
    barcoding_preprocess_cppipe = "path/to/barcoding_preprocess.cppipe"
    combinedanalysis_cppipe     = "path/to/combined_analysis.cppipe"

    range_skip = 4
    painting_quarter_if_round = false
    barcoding_quarter_if_round = false
    painting_imperwell = 80
    barcoding_imperwell = 21
    painting_rows = 10
    barcoding_columns = 5
    painting_columns = 10
    barcoding_columns = 5
    tileperside = 5
    final_tile_size = 2500
    first_site_index = 0
    phenix = true
}
```

## Running the Pipeline with Seqera Platform

### Configuring the Pipeline in Seqera Platform

Navigate to **Launchpad** → **Add Pipeline**.

#### Pipeline Settings

| Setting | Value |
|---------|-------|
| **Name** | `nf-pooled-cellpainting` or a name describing your run |
| **Pipeline to launch** | `https://github.com/broadinstitute/nf-pooled-cellpainting` |
| **Revision** | `dev` (for latest updates), `main` (for latest versioned code), or a specific commit |
| **Compute environment** | Your AWS Batch environment |
| **Work directory** | `s3://your-bucket/prefix/to/scratch/output` |
| **Config profiles** | (leave empty for a custom run) |

#### Pipeline Parameters

In the Launchpad, select "Launch" for your pipeline.

In the "Run Parameters" tab, fill all of the required Input/Output options. You can manually enter each of the values in the "Input form view" or you can add the following parameters to the JSON or YAML in the "Params file view". Note that all of the other parameters have default values but **you may need to edit default values to match your dataset.**

```yaml
input: "s3://your-bucket/samplesheet.csv"
outdir: "s3://your-bucket/results"
barcodes: "s3://your-bucket/barcodes.csv"
painting_illumcalc_cppipe: "s3://your-bucket/pipelines/painting_illumcalc.cppipe"
painting_illumapply_cppipe: "s3://your-bucket/pipelines/painting_illumapply.cppipe"
painting_segcheck_cppipe: "s3://your-bucket/pipelines/painting_segcheck.cppipe"
barcoding_illumcalc_cppipe: "s3://your-bucket/pipelines/barcoding_illumcalc.cppipe"
barcoding_illumapply_cppipe: "s3://your-bucket/pipelines/barcoding_illumapply.cppipe"
barcoding_preprocess_cppipe: "s3://your-bucket/pipelines/barcoding_preprocess.cppipe"
combinedanalysis_cppipe: "s3://your-bucket/pipelines/combinedanalysis.cppipe"
```

:::important
Keep `qc_barcoding_passed: false` and `qc_painting_passed: false` for your first trigger of the pipeline. This will pause the pipeline after these important QC steps before the final steps are run.
:::

Select "Launch"

### Launching and Monitoring Runs

1. **Launch**: Click **Launch** from the pipeline page
2. **Monitor**: View real-time task execution in the **Runs** tab
3. **QC Review**: Check outputs in the S3 bucket or via the **Reports** tab
4. **Resume**: After QC review, click **Resume** (not Relaunch!) with updated parameters:

```yaml
qc_painting_passed: true
qc_barcoding_passed: true
```

:::{important} "Resume vs Relaunch"
**Resume** uses cached results; **Relaunch** starts from scratch. Always use Resume after QC review.
:::

### Cost Optimization Tips

1. **Use Spot Instances**: 60-90% cost savings for fault-tolerant workloads
2. **Enable Fusion Snapshots**: Automatically recover from spot interruptions
3. **Right-size Max CPUs**: Start with 500-1000, increase based on queue times
4. **Use Appropriate Instance Types**: Memory-optimized (`r6id`) for Combined Analysis; compute-optimized (`c6id`) for illumination steps
5. **Clean Up Work Directory**: Periodically delete old work directories from S3
6. **Route Long Tasks to On-Demand**: See below for avoiding spot reclaim losses on multi-hour tasks

### Routing Long-Running Tasks to On-Demand Instances

Long-running tasks like `FIJI_STITCHCROP` (up to 4-6 hours) and `CELLPROFILER_COMBINEDANALYSIS` risk losing hours of work if spot instances are reclaimed. To avoid this:

1. **Create an on-demand compute environment** in Seqera Platform (duplicate your spot environment, disable Fusion Snapshots since they're unnecessary for on-demand)

2. **Route specific processes** to the on-demand queue by adding to your Nextflow config:

```groovy
process {
    withName: 'FIJI_STITCHCROP' {
        queue = '<on-demand-queue-name>'
    }
    withName: 'CELLPROFILER_COMBINEDANALYSIS' {
        queue = '<on-demand-queue-name>'
    }
}
```

The queue name is visible in your Seqera Platform compute environment under "Manual config attributes".

:::{tip} When to use on-demand
Use on-demand for tasks that: (1) run longer than 1-2 hours, (2) have experienced repeated spot reclamations, or (3) are in the final stages of a critical run
:::

### Resource Requirements by Process

| Process | CPU | Memory | Notes |
|---------|-----|--------|-------|
| CELLPROFILER_ILLUMCALC | 1 | 2 GB | Per plate |
| CELLPROFILER_ILLUMAPPLY | 1-2 | 6 GB | Per well/site |
| CELLPROFILER_PREPROCESS | 4 | 8 GB | Per site |
| FIJI_STITCHCROP | 6 | 36 GB | Memory-intensive |
| CELLPROFILER_COMBINEDANALYSIS | 4 | 12-32 GB | Most demanding |

To override defaults, add to your Nextflow config:

```groovy
process {
    withName: 'CELLPROFILER_COMBINEDANALYSIS' {
        memory = '64.GB'
    }
}
```
