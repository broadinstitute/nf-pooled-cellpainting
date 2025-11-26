# Architecture

Technical overview of the pipeline architecture and implementation.

## Workflow Design

### Main Workflow

The main workflow (`main.nf`) orchestrates two parallel subworkflows:

<!-- ```groovy
workflow NF_POOLED_CELLPAINTING {
    // Split samplesheet into painting and barcoding arms
    ch_samplesheet
        .branch { meta, files ->
            painting: meta.arm == 'painting'
            barcoding: meta.arm == 'barcoding'
        }
        .set { ch_branched }

    // Process painting arm
    CELLPAINTING(ch_branched.painting, ...)

    // Process barcoding arm
    BARCODING(ch_branched.barcoding, ...)

    // Combined analysis (conditional)
    if (qc_painting_passed && qc_barcoding_passed) {
        CELLPROFILER_COMBINEDANALYSIS(
            CELLPAINTING.out.stitched_cropped,
            BARCODING.out.stitched_cropped,
            ...
        )
    }
}
``` -->

### Cell Painting Subworkflow

Located in `subworkflows/local/cellpainting/main.nf`. The workflow is organized into three logical phases:

**1. Illumination Correction**

- **ILLUMCALC**: Calculate illumination corrections per plate (outputs `.npy`).
  - _Groups by:_ `[batch, plate]`
- **QC_MONTAGEILLUM**: Generate illumination QC montages.
- **ILLUMAPPLY**: Apply illumination corrections per site.
  - _Groups by:_ `[batch, plate, well, site]`

**2. Segmentation Quality Control**

- **SEGCHECK**: Segmentation quality check (subsampled by `range_skip`).
  - _Groups by:_ `[batch, plate, well]`
- **QC_MONTAGE_SEGCHECK**: Segmentation QC visualizations.

**3. Image Stitching (Conditional)**

- **FIJI_STITCHCROP**: Stitch and crop images (enabled when `qc_painting_passed`).
  - _Groups by:_ `[batch, plate, well]`
- **QC_MONTAGE_STITCHCROP**: Stitching QC visualizations.

### Barcoding Subworkflow

Located in `subworkflows/local/barcoding/main.nf`. The workflow is organized into three logical phases:

**1. Illumination Correction**

- **ILLUMCALC**: Calculate cycle-specific illumination corrections.
  - _Groups by:_ `[batch, plate, cycle]`
- **QC_MONTAGEILLUM**: Illumination QC montages.
- **ILLUMAPPLY**: Apply illumination corrections.
  - _Groups by:_ `[batch, plate, well]`

**2. Barcode Quality Control and Preprocessing**

- **QC_BARCODEALIGN**: Barcode alignment QC.
  - Checks pixel shifts and correlation between cycles.
  - Validates against `barcoding_shift_threshold` and `barcoding_corr_threshold`.
- **PREPROCESS**: Barcode calling and preprocessing.
  - Uses CellProfiler plugins (`callbarcodes`, `compensatecolors`).
  - _Groups by:_ `[batch, plate, well,site]`
- **QC_PREPROCESS**: Preprocessing QC visualizations.

**3. Image Stitching (Conditional)**

- **FIJI_STITCHCROP**: Stitch and crop images.
  - Enabled when `qc_barcoding_passed == true`.
  - _Groups by:_ `[batch, plate, well]`

## Channel Architecture

### Data Flow

Nextflow channels carry metadata and file references.

```groovy
[meta, files]
```

Where `meta` contains:

```groovy
meta = [
    batch: 'batch1',
    plate: 'P001',
    well: 'A01',
    site: 1,
    cycle: 1,          // barcoding only
    channels: ['DAPI', 'GFP', 'RFP'],
    n_frames: 4,
    arm: 'painting'
]
```

### Grouping Strategy

During the workflow execution, the input channels are grouped based on the parallelization granularity we chose for each pipeline step. The currently implemented grouping strategy is as follows:]

- **CELLPROFILER_ILLUMCALC**:
  - painting: Grouped by plate
  - barcoding: Grouped by plate, cycle
- **CELLPROFILER_ILLUMAPPLY**:
  - painting: Parallelized per site
  - barcoding: Parallelized per well
- **CELLPROFILER_STITCHCROP**:
  - painting: Parallelized per well
  - barcoding: Parallelized per well
- **CELLPROFILER_COMBINEDANALYSIS**:
  - painting: Parallelized per site
  - barcoding: Parallelized per site

The channel grouping is implemented throughout workflow and subworkflows.

```groovy
// Group images by batch and plate for illumination calculation
// Keep metadata for each image to generate load_data.csv
ch_illumcalc_input = ch_samplesheet_cp
    .map { meta, image ->

        def group_id = "${meta.batch}_${meta.plate}"
        def group_key = meta.subMap(['batch', 'plate']) + [id: group_id]

        // Preserve full metadata for each image
        def image_meta = meta + [filename: image.name]
        [group_key, image_meta, image]
    }
    .groupTuple()
    .map { meta, images_meta_list, images_list ->
        def all_channels = images_meta_list[0].channels
        // Return tuple: (shared_meta, channels, cycles, images, per-image metadata)
        [meta, all_channels, null, images_list, images_meta_list]
    }
```

We specifically pass along the per-image metadata to the illumination correction process to efficiently generate the load_data.csv file within the process script block. These channel rewirings will look different depending on the grouping that is desired. A concrete example of two different levels of parallelization is implemented for CELLPROFILER_ILLUMAPPLY_BARCODING, which can be parallelized at the site or well level, which is controlled by a parameter (`--barcoding_illumapply_grouping`):

```
// Group images for ILLUMAPPLY based on parameter setting
// Two modes:
//   - "site": Group by site - each site is processed separately
//   - "well": Group by well (default) - all sites in a well are processed together
// Site information is always preserved in image metadata for downstream preprocessing
ch_images_by_site = ch_samplesheet_sbs
    .map { meta, image ->
        // Determine grouping key based on parameter
        def group_key
        def group_id

        if (barcoding_illumapply_grouping == "site") {
            // Site-level grouping
            group_key = meta.subMap(['batch', 'plate', 'well', 'site', 'arm'])
            group_id = "${meta.batch}_${meta.plate}_${meta.well}_Site${meta.site}"
        }
        else {
            // Well-level grouping (default)
            // Site is NOT in the grouping key, but preserved in image metadata
            group_key = meta.subMap(['batch', 'plate', 'well', 'arm'])
            group_id = "${meta.batch}_${meta.plate}_${meta.well}"
        }

        // Preserve full metadata for each image (including site)
        def image_meta = meta.clone()
        image_meta.filename = image.name

        [group_key + [id: group_id], image_meta, image]
    }
    .groupTuple()
    .map { group_meta, images_meta_list, images_list ->
        // Get unique cycles and channels for this group
        // For barcoding, we expect multiple cycles
        def all_cycles = images_meta_list.collect { m -> m.cycle }.findAll { c -> c != null }.unique().sort()
        def unique_cycles = all_cycles.size() > 1 ? all_cycles : null
        def all_channels = images_meta_list[0].channels

        // Return tuple: (shared meta, channels, cycles, images, per-image metadata)
        [group_meta, all_channels, unique_cycles, images_list, images_meta_list]
    }
```

## Process Design

### Standard Process Structure

```groovy
process EXAMPLE_PROCESS {
    tag "${meta.batch}_${meta.plate}_${meta.well}"
    label 'process_medium'
    container 'wave.seqera.io/cellprofiler/cellprofiler:4.2.8'

    input:
    tuple val(meta), path(images)
    path(cppipe)

    output:
    tuple val(meta), path("output/*"), emit: images
    path("*.csv"), emit: csv

    script:
    """
    # Generate load_data.csv
    generate_load_data_csv.py \\
        --pipeline_type example \\
        --output load_data.csv

    # Run CellProfiler
    cellprofiler \\
        -c -r \\
        -p ${cppipe} \\
        -o output/ \\
        --data-file=load_data.csv
    """
}
```

### Key Conventions

1. **Tagging**: Use image metadata for process identification (allows easier understanding which site / well / plate is being processed by a task)
2. **Labels**: Apply resource labels to specify resource needs (`qc`,`cellprofiler_basic`, `cellprofiler_medium`, `fiji`)
3. **Containers**: Specify container images explicitly
4. **Output channels**: Name channels with `emit:`
5. **Scripts**: Use Python helper script to generate load_data.csv for cellprofiler processes

## QC Gate Implementation

### Conditional Execution

As previously described, there are two parameters that control progression of the painting and barcoding arms: `qc_painting_passed` and `qc_barcoding_passed`. These parameters are `false` by default and can be set to `true` if the QC checks have passed or if the user is certain that the images and QC are of high quality.

```groovy
if (params.qc_painting_passed) {
    FIJI_STITCHCROP(
        CELLPROFILER_ILLUMAPPLY.out.corrected,
        ...
    )
}
```

Importantly, only setting `if else` statements to control the gating behaviour is not sufficient because Nextflow uses the dataflow paradigm and will still process all sites / wells / plates even if the QC checks fail. To prevent this, we use the [when](https://github.com/seqera-services/nf-pooled-cellpainting/blob/025098a756da05ae1948fa94a74dd9747af90a88/modules/local/fiji/stitchcrop/main.nf#L33-L34) parameter inside the `FIJI_STITCHCROP` process to control the execution of the process. This `when` parameter will only let the process be executed if the `qc_painting_passed` or `qc_barcoding_passed` parameter respectively are set to `true`.

### Manual Review Workflow

1. Run pipeline with default QC parameters (`false`)
2. Pipeline stops after initial QC checks
3. Review QC outputs in `results/qc/`
4. Re-run with `--qc_painting_passed true` if QC passes
5. Pipeline resumes from cached results (`-resume`)

## Data Staging

### Load Data CSV Generation

All CellProfiler processes require `load_data.csv` files:

```python
generate_load_data_csv.py \
    --pipeline_type illumcalc \
    --channels DAPI,GFP,RFP \
    --output load_data.csv
```

Supported pipeline types:

- `illumcalc`: Multi-channel raw images
- `illumapply`: Corrected images + illumination functions
- `segcheck`: Corrected images for QC
- `preprocess`: Cycle-based barcoding images
- `combined`: Painting + barcoding merged images

For more details about the `load_data.csv` file, see the [Cellprofiler Integration](cellprofiler.md) document.

## Plugin Integration

### CellProfiler Plugins

Cellprofiler plugins are downloaded and staged by Nextflow from the Cellprofiler plugin repository by default: [https://github.com/seqera-services/nf-pooled-cellpainting/blob/025098a756da05ae1948fa94a74dd9747af90a88/nextflow.config#L83-L84](https://github.com/seqera-services/nf-pooled-cellpainting/blob/025098a756da05ae1948fa94a74dd9747af90a88/nextflow.config#L83-L84)

## Error Handling

### Retry Strategy

Error and retry strategies are defined in the base.config file in the `/conf` directory. The pipeline supports retrying failed processes in case of insufficient memory or other defined error codes. The specific parameters and exit codes for retry behaviour can be modified via nextflow configuration:
[base.config](https://github.com/seqera-services/nf-pooled-cellpainting/blob/dev/conf/base.config)

## Next Steps

- [CellProfiler Integration](cellprofiler.md) - Deep dive into CellProfiler usage
- [Python Scripts](python-scripts.md) - Understand data staging scripts
- [Testing](testing.md) - Learn testing strategies
