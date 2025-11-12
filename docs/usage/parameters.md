# Parameters Reference

Complete reference for all pipeline parameters.

## Required Parameters

### Input/Output

| Parameter    | Type   | Description                                                                                                    |
| ------------ | ------ | -------------------------------------------------------------------------------------------------------------- |
| `--input`    | `path` | Samplesheet CSV with columns: `path`, `arm`, `batch`, `plate`, `well`, `channels`, `site`, `cycle`, `n_frames` |
| `--barcodes` | `path` | CSV file with barcode definitions (`barcode_id`, `sequence`)                                                   |
| `--outdir`   | `path` | Output directory for results                                                                                   |

### CellProfiler Pipelines

| Parameter                       | Type   | Description                                           |
| ------------------------------- | ------ | ----------------------------------------------------- |
| `--painting_illumcalc_cppipe`   | `path` | Illumination calculation pipeline for Cell Painting   |
| `--painting_illumapply_cppipe`  | `path` | Illumination correction pipeline for Cell Painting    |
| `--painting_segcheck_cppipe`    | `path` | Segmentation QC pipeline                              |
| `--barcoding_illumcalc_cppipe`  | `path` | Illumination calculation pipeline for barcoding       |
| `--barcoding_illumapply_cppipe` | `path` | Illumination correction pipeline for barcoding        |
| `--barcoding_preprocess_cppipe` | `path` | Barcoding preprocessing pipeline with barcode calling |
| `--combinedanalysis_cppipe`     | `path` | Combined analysis pipeline                            |

### CellProfiler Plugins

| Parameter                   | Type     | Description                                 |
| --------------------------- | -------- | ------------------------------------------- |
| `--callbarcodes_plugin`     | `string` | URL or path to `callbarcodes.py` plugin     |
| `--compensatecolors_plugin` | `string` | URL or path to `compensatecolors.py` plugin |

## Cell Painting Parameters

### Image Properties

| Parameter                | Type     | Default   | Description                              |
| ------------------------ | -------- | --------- | ---------------------------------------- |
| `--cp_img_overlap_pct`   | `int`    | `10`      | Image overlap percentage for stitching   |
| `--cp_img_frame_type`    | `string` | `"round"` | Frame type: `round`, `square`, or custom |
| `--cp_acquisition_order` | `string` | `"snake"` | Acquisition order: `snake`, `raster`     |

### Quality Control

| Parameter              | Type      | Default | Description                                              |
| ---------------------- | --------- | ------- | -------------------------------------------------------- |
| `--range_skip`         | `int`     | `16`    | Sampling frequency for segmentation check (1 in N sites) |
| `--qc_painting_passed` | `boolean` | `false` | Enable progression to stitching after QC review          |

## Barcoding Parameters

### Image Properties

| Parameter                 | Type     | Default   | Description                              |
| ------------------------- | -------- | --------- | ---------------------------------------- |
| `--sbs_img_overlap_pct`   | `int`    | `10`      | Image overlap percentage for stitching   |
| `--sbs_img_frame_type`    | `string` | `"round"` | Frame type: `round`, `square`, or custom |
| `--sbs_acquisition_order` | `string` | `"snake"` | Acquisition order: `snake`, `raster`     |

### Acquisition Geometry

| Parameter                        | Type  | Default | Description                                    |
| -------------------------------- | ----- | ------- | ---------------------------------------------- |
| `--acquisition_geometry_rows`    | `int` | `2`     | Number of rows in acquisition geometry grid    |
| `--acquisition_geometry_columns` | `int` | `2`     | Number of columns in acquisition geometry grid |

### Quality Control

| Parameter                     | Type      | Default | Description                                         |
| ----------------------------- | --------- | ------- | --------------------------------------------------- |
| `--barcoding_shift_threshold` | `float`   | `50.0`  | Maximum allowed pixel shift between cycles (pixels) |
| `--barcoding_corr_threshold`  | `float`   | `0.9`   | Minimum correlation coefficient between cycles      |
| `--qc_barcoding_passed`       | `boolean` | `false` | Enable progression to stitching after QC review     |

## Execution Parameters

### Container Configuration

Use `-profile` to specify container engine:

```bash
-profile docker          # Docker
-profile singularity     # Singularity/Apptainer
-profile podman          # Podman
```

### Resource Configuration

Override default resources in a custom config:

```groovy
process {
    withName: 'CELLPROFILER_.*' {
        cpus = 4
        memory = 16.GB
        time = 4.h
    }
}
```

### Execution Backends

Configure executor in `nextflow.config`:

```groovy
executor {
    name = 'slurm'  // or 'sge', 'pbs', 'awsbatch', etc.
    queueSize = 100
}
```

## Parameter Files

Store parameters in a file for reproducibility:

```yaml
# params.yml
input: "samplesheet.csv"
barcodes: "barcodes.csv"
outdir: "results"

cp_img_overlap_pct: 15
range_skip: 8

qc_painting_passed: true
qc_barcoding_passed: true

painting_illumcalc_cppipe: "pipelines/painting_illumcalc.cppipe"
# ... additional parameters
```

Run with:

```bash
nextflow run main.nf -params-file params.yml
```

## Advanced Configuration

### Skip Specific Processes

Modify workflow in `workflows/nf-pooled-cellpainting.nf` to conditionally skip processes.

### Custom Channel Grouping

The pipeline automatically groups images by metadata. To customize, modify channel logic in subworkflows.

### Plugin Configuration

Plugins are downloaded once and cached. To update:

```bash
rm -rf work/
nextflow run main.nf ... -resume
```

## Examples

### High-throughput Run

```bash
nextflow run main.nf \
  --input large_samplesheet.csv \
  --range_skip 32 \
  --cp_img_overlap_pct 5 \
  --sbs_img_overlap_pct 5 \
  -profile docker \
  -resume
```

### Quick QC Check

```bash
nextflow run main.nf \
  --input subset_samplesheet.csv \
  --range_skip 4 \
  -profile docker
```

### Production Run with QC Gates

```bash
nextflow run main.nf \
  --input samplesheet.csv \
  --qc_painting_passed true \
  --qc_barcoding_passed true \
  -profile singularity \
  -resume
```

## See Also

- [Quick Start](../getting-started/quickstart.md) - Basic usage examples
- [Architecture](../developer/architecture.md) - Understanding parameter effects
- [Troubleshooting](../reference/troubleshooting.md) - Common parameter issues
