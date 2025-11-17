# Architecture

Technical overview of the pipeline architecture and implementation.

## Pipeline Structure

```
nf-pooled-cellpainting/
├── main.nf                          # Entry point
├── nextflow.config                  # Main configuration
├── workflows/
│   └── nf-pooled-cellpainting.nf   # Main workflow logic
├── subworkflows/
│   └── local/
│       ├── cellpainting/           # Cell painting processing arm
│       ├── barcoding/              # Barcoding processing arm
│       └── utils*/                 # Utility subworkflows
├── modules/
│   ├── local/
│   │   ├── cellprofiler/          # CellProfiler processes
│   │   │   ├── illumcalc/         # Illumination calculation
│   │   │   ├── illumapply/        # Illumination application
│   │   │   ├── preprocess/        # Barcode preprocessing
│   │   │   ├── segcheck/          # Segmentation QC
│   │   │   └── combinedanalysis/  # Combined analysis
│   │   ├── fiji/                  # Fiji image processing
│   │   │   └── stitchcrop/        # Image stitching & cropping
│   │   └── qc/                    # QC processes
│   └── nf-core/                   # nf-core modules (MultiQC)
├── bin/                            # Python scripts & tools
├── conf/                           # Configuration files
├── assets/                         # CellProfiler pipelines & resources
├── lib/                            # Groovy library functions
├── docs/                           # Documentation source
└── tests/                          # nf-test test cases
```

## Workflow Design

### Main Workflow

The main workflow (`workflows/nf-pooled-cellpainting.nf`) orchestrates two parallel processing arms:

```groovy
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
```

### Cell Painting Subworkflow

Located in `subworkflows/local/cellpainting/main.nf`:

1. **ILLUMCALC**: Calculate illumination corrections
   - Groups by: `[batch, plate]`
   - Outputs: `.npy` illumination functions per plate
2. **QC_MONTAGEILLUM**: Generate illumination QC montages
3. **ILLUMAPPLY**: Apply illumination corrections
   - Groups by: `[batch, plate, well, site]`
   - Parallelized per site
4. **SEGCHECK**: Segmentation quality check
   - Subsampled by `range_skip` parameter
5. **QC_MONTAGE_SEGCHECK**: Segmentation QC visualizations
6. **FIJI_STITCHCROP**: Stitch and crop images (conditional)
   - Groups by: `[batch, plate, well]`
   - Enabled when `qc_painting_passed == true`
7. **QC_MONTAGE_STITCHCROP**: Stitching QC visualizations

### Barcoding Subworkflow

Located in `subworkflows/local/barcoding/main.nf`:

1. **ILLUMCALC**: Calculate cycle-specific illumination corrections
   - Groups by: `[batch, plate, cycle]`
2. **QC_MONTAGEILLUM**: Illumination QC montages
3. **ILLUMAPPLY**: Apply illumination corrections
   - Groups by: `[batch, plate, well, site]`
   - Parallelized per site
4. **QC_BARCODEALIGN**: Barcode alignment QC
   - Checks pixel shifts and correlation between cycles
   - Validates against `barcoding_shift_threshold` and `barcoding_corr_threshold`
5. **PREPROCESS**: Barcode calling and preprocessing
   - Uses CellProfiler plugins (`callbarcodes`, `compensatecolors`)
6. **QC_PREPROCESS**: Preprocessing QC visualizations
7. **FIJI_STITCHCROP**: Stitch and crop (conditional)
   - Enabled when `qc_barcoding_passed == true`

## Channel Architecture

### Data Flow

Nextflow channels carry metadata and file references:

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

Processes group inputs at optimal granularity:

```groovy
// Illumination calculation: per plate
ch_input
    .map { meta, files ->
        def key = [meta.batch, meta.plate]
        [key, meta, files]
    }
    .groupTuple(by: 0)

// Illumination correction: per well
ch_input
    .map { meta, files ->
        def key = [meta.batch, meta.plate, meta.well]
        [key, meta, files]
    }
    .groupTuple(by: 0)
```

### Parallelization

The pipeline implements fine-grained parallelization:

- **Illumination calculation**: Grouped by plate (or plate+cycle for barcoding)
- **Illumination correction**: Parallelized per site
- **Stitching**: Parallelized per well
- **Combined analysis**: Parallelized per site
- **Result**: Optimal resource utilization and throughput

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

1. **Tagging**: Use metadata for process identification
2. **Labels**: Apply resource labels (`process_low`, `process_medium`, `process_high`)
3. **Containers**: Specify container images explicitly
4. **Output channels**: Name channels with `emit:`
5. **Scripts**: Use Python helpers for CSV generation

## QC Gate Implementation

### Conditional Execution

QC gates control progression:

```groovy
if (params.qc_painting_passed) {
    FIJI_STITCHCROP(
        CELLPROFILER_ILLUMAPPLY.out.corrected,
        ...
    )
}
```

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

### File Organization

Output files follow consistent naming:

```
# Painting corrected images
Plate_{plate}_Well_{well}_Site_{site}_Corr{channel}.tiff

# Barcoding corrected images
Plate_{plate}_Well_{well}_Site_{site}_Cycle{cycle}_{channel}.tiff

# Stitched/cropped images
Plate_{plate}_Well_{well}_Site_{site}_*.tiff

# Illumination functions
{plate}_Illum{channel}.npy
```

## Plugin Integration

### CellProfiler Plugins

Plugins are downloaded and staged before CellProfiler execution:

```groovy
script:
"""
# Download plugins
wget -O callbarcodes.py ${params.callbarcodes_plugin}
wget -O compensatecolors.py ${params.compensatecolors_plugin}

# Run CellProfiler with plugin directory
cellprofiler \\
    -c -r \\
    -p ${cppipe} \\
    --plugins-directory=.
"""
```

### Plugin Requirements

- `callbarcodes.py`: Barcode calling logic
- `compensatecolors.py`: Color compensation for barcoding

## Error Handling

### Retry Strategy

```groovy
process {
    errorStrategy = 'retry'
    maxRetries = 3

    withLabel: 'process_high' {
        memory = { task.attempt == 1 ? 32.GB : 64.GB }
    }
}
```

### Debugging

Enable trace and debugging:

```bash
nextflow run main.nf -with-trace -with-dag dag.png
```

## Performance Considerations

### Resource Allocation

Optimize based on process characteristics:

- **ILLUMCALC**: High memory (processes all images per plate)
- **ILLUMAPPLY**: Medium resources (processes per well)
- **PREPROCESS**: Medium resources with plugin overhead
- **STITCHCROP**: Medium CPU for Fiji operations

### Caching Strategy

Nextflow caches completed tasks. Key factors:

- Input files (content-based hashing)
- Script changes
- Container changes
- Parameter changes

Use `-resume` to leverage caching after failures or parameter tweaks.

## Next Steps

- [CellProfiler Integration](cellprofiler.md) - Deep dive into CellProfiler usage
- [Python Scripts](python-scripts.md) - Understand data staging scripts
- [Testing](testing.md) - Learn testing strategies
