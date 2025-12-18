# CellProfiler Integration

[CellProfiler](https://cellprofiler.org/) is the workhorse of this pipeline. It's an open-source tool designed specifically for high-throughput image analysis in biology. If you're new to CellProfiler, think of it as a flexible image processing engine that you configure using "pipeline" files (`.cppipe`).

This page explains how the pipeline uses CellProfiler and how to customize the integration for your own data.

## Overview

The pipeline uses CellProfiler v4.2.8 for image analysis tasks:

- Illumination correction calculation and application
- Image preprocessing
- Cell segmentation
- Feature extraction
- Barcode calling

## CellProfiler Processes

### Process Modules

All CellProfiler processes follow a similar pattern:

```groovy
process CELLPROFILER_ILLUMCALC {
    container 'wave.seqera.io/cellprofiler/cellprofiler:4.2.8'

    input:
    tuple val(meta), path(images)
    path(cppipe)

    script:
    """
    # Generate load_data.csv
    generate_load_data_csv.py \\
        --pipeline_type illumcalc \\
        --channels ${meta.channels.join(',')} \\
        --output load_data.csv

    # Run CellProfiler
    cellprofiler \\
        -c -r \\
        -p ${cppipe} \\
        -o . \\
        --data-file=load_data.csv
    """
}
```

### Key Processes

| Process            | Purpose                          | Grouping                   | Key Outputs             |
| ------------------ | -------------------------------- | -------------------------- | ----------------------- |
| `ILLUMCALC`        | Calculate illumination functions | Per plate (or plate+cycle) | `.npy` files            |
| `ILLUMAPPLY`       | Apply corrections                | Per well or site           | Corrected TIFF images   |
| `SEGCHECK`         | Segmentation QC                  | Per well (subsampled)      | PNG previews, CSV stats |
| `PREPROCESS`       | Barcode calling                  | Per site                   | Preprocessed TIFF, CSV  |
| `COMBINEDANALYSIS` | Final segmentation               | Per site                   | Masks, overlays, CSV    |

## Pipeline Files (.cppipe)

### Structure

CellProfiler pipelines are text files (`.cppipe`) files defining:

- Input modules (LoadData, LoadImages)
- Processing modules (CorrectIlluminationCalculate, ApplyIllumination)
- Output modules (SaveImages, ExportToSpreadsheet)

### Example Pipelines

The pipeline requires these `.cppipe` files (names of the actual files can be different!):

1. **painting_illumcalc.cppipe**: Calculate painting illumination
    - Inputs: Multi-channel raw images
    - Outputs: `.npy` illumination functions per channel

2. **painting_illumapply.cppipe**: Apply painting illumination
    - Inputs: Raw images + illumination functions
    - Outputs: Corrected TIFF images

3. **painting_segcheck.cppipe**: Segmentation QC
    - Inputs: Corrected images
    - Outputs: Segmentation previews

4. **barcoding_illumcalc.cppipe**: Calculate barcoding illumination
    - Inputs: Multi-cycle raw images
    - Outputs: Cycle-specific illumination functions

5. **barcoding_illumapply.cppipe**: Apply barcoding illumination
    - Inputs: Raw cycle images + illumination functions
    - Outputs: Corrected cycle images

6. **barcoding_preprocess.cppipe**: Barcode calling
    - Inputs: Corrected cycle images
    - Outputs: Barcode-called images
    - Requires: `callbarcodes` and `compensatecolors` plugins

7. **combinedanalysis.cppipe**: Final analysis
    - Inputs: Painting corrected + barcoding preprocessed images
    - Outputs: Segmentation masks, feature measurements
    - Requires: `callbarcodes` plugin

## Load Data CSV Generation

### Purpose

CellProfiler requires `load_data.csv` files that specify:

- Image file paths
- Metadata (plate, well, site, frame, channel, cycle)
- Image grouping for processing

### Generation Script

The `generate_load_data_csv.py` script creates these files:

```python
generate_load_data_csv.py \
    --pipeline_type illumcalc \
    --channels DAPI,GFP,RFP,Cy5,Cy3 \
    --frames 0,1,2,3 \
    --output load_data.csv
```

### Pipeline Types

Different CellProfiler stages require different CSV formats:

#### 1. `illumcalc` - Illumination Calculation

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,Metadata_Frame,FileName_DAPI,PathName_DAPI,...
P001,A01,1,0,P001_A01_1_0_DAPI.tif,/path/to/images,...
```

#### 2. `illumapply` - Illumination Correction

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,Metadata_Frame,FileName_OrigDAPI,PathName_OrigDAPI,FileName_IllumDAPI,PathName_IllumDAPI,...
P001,A01,1,0,P001_A01_1_0_DAPI.tif,/orig/,P001_IllumDAPI.npy,/illum/,...
```

#### 3. `preprocess` - Barcoding with Cycles

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,Metadata_Frame,Metadata_Cycle,FileName_Cycle1_Cy3,PathName_Cycle1_Cy3,...
P001,A01,1,0,1,P001_A01_1_0_Cycle1_Cy3.tif,/path/,...
```

#### 4. `combined` - Painting + Barcoding

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,Metadata_Frame,FileName_CorrDAPI,PathName_CorrDAPI,FileName_Cycle1_Cy3,PathName_Cycle1_Cy3,...
P001,A01,1,0,P001_A01_1_CorrDAPI.tif,/painting/,P001_A01_1_0_Cycle1_Cy3.tif,/barcoding/,...
```

## Execution Details

### Command-Line Invocation

CellProfiler is run in headless mode:

```bash
cellprofiler \
    -c \                    # Run without GUI
    -r \                    # Run pipeline
    -p pipeline.cppipe \    # Pipeline file
    -o output_dir/ \        # Output directory
    --data-file=load_data.csv  # Input CSV
```

### Plugin Loading

For processes requiring plugins, Nextflow stages plugins into the process based on the plugin path provided.
Default plugins are loaded from https://github.com/CellProfiler/CellProfiler-plugins via raw github links but local or other sources for the plugins can be specified if required. 

```bash
# Stage plugins in nf-pooled-cellpainting.nf
file(params.callbarcodes_plugin)

# Stage plugins as input into process
path plugins, stageAs: "plugins/"

# use plugins in process with cellprofiler
cellprofiler -c -r \\
    -p combinedanalysis_patched.cppipe \\
    -o . \\
    --data-file=load_data.csv \\
    --image-directory ./images/ \\
    --plugins-directory=./plugins/
```

## Output Organization

### File Naming Conventions

CellProfiler outputs follow structured naming:

```
# Corrected images
{plate}_{well}_{site}_Corr{channel}.tif

# Illumination functions
{plate}_Illum{channel}.npy

# Preprocessed barcoding
{plate}_{well}_{site}_Cycle{cycle}_{channel}.tif

# Segmentation masks
{plate}_{well}_{site}_Nuclei.tif
{plate}_{well}_{site}_Cells.tif
```

### CSV Outputs

Feature measurements are saved as CSV:

- `Image.csv`: Per-image measurements
- `Nuclei.csv`: Per-nucleus measurements
- `Cells.csv`: Per-cell measurements
- `Experiment.csv`: Pipeline metadata

## Troubleshooting

### Common Issues

#### 1. Load Data CSV Errors

**Symptom**: CellProfiler fails with "Unable to load image"

**Solution**: Validate CSV paths are accessible:

```bash
# Check CSV format
head load_data.csv

# Verify image paths exist
cat load_data.csv | cut -d',' -f5 | xargs -I {} test -f {} && echo "OK"
```

#### 2. Plugin Not Found

**Symptom**: "Plugin 'callbarcodes' not found"

**Solution**: Ensure plugin URL is accessible and pipeline has access to the internet if plugin is loaded from an online source.

#### 3. Memory Errors

**Symptom**: CellProfiler crashes with out-of-memory

**Solution**: Increase process memory or reduce image size:

```groovy
process {
    withName: 'CELLPROFILER_.*' {
        memory = { task.attempt == 1 ? 32.GB : 64.GB }
        errorStrategy = 'retry'
    }
}
```

## Best Practices

1. **Validate pipelines**: Test `.cppipe` files in CellProfiler GUI first
2. **Test on subset data first**: Test your dataset on 1 well first, since well is the smallest unit we can use for the pipeline. If the pipeline works on 1 well, it should work on a full plate.
3. **Resource tuning**: Profile memory usage and adjust allocation (to save time and cost)
4. **Plugin versioning**: Pin plugin versions for reproducibility
5. **Output validation**: Check output file counts match expectations

## Next Steps

- [Python Scripts](python-scripts.md) - Understand CSV generation
- [Architecture](architecture.md) - Overall pipeline design
- [Testing](testing.md) - Test CellProfiler integration
