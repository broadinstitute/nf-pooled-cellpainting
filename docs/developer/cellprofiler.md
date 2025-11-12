# CellProfiler Integration

Deep dive into how CellProfiler is integrated and executed within the pipeline.

## Overview

The pipeline uses [CellProfiler](https://cellprofiler.org/) v4.2.8 for image analysis tasks:

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

CellProfiler pipelines are XML-based `.cppipe` files defining:

- Input modules (LoadData, LoadImages)
- Processing modules (CorrectIlluminationCalculate, ApplyIllumination)
- Output modules (SaveImages, ExportToSpreadsheet)

### Template Support

Pipelines can use template variables:

```xml
<LoadData>
    <csv_file_name>load_data.csv</csv_file_name>
</LoadData>
```

The pipeline automatically populates:

- Channel names
- File paths
- Output directories

### Example Pipelines

The pipeline requires these `.cppipe` files:

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

For processes requiring plugins:

```bash
# Download plugins
wget -O callbarcodes.py ${PLUGIN_URL}
wget -O compensatecolors.py ${PLUGIN_URL}

# Run with plugin directory
cellprofiler \
    -c -r \
    -p pipeline.cppipe \
    --plugins-directory=. \
    --data-file=load_data.csv
```

### Resource Requirements

Typical resource allocation:

```groovy
process {
    withName: 'CELLPROFILER_ILLUMCALC' {
        cpus = 8
        memory = 32.GB
        time = 8.h
    }

    withName: 'CELLPROFILER_ILLUMAPPLY' {
        cpus = 4
        memory = 16.GB
        time = 4.h
    }

    withName: 'CELLPROFILER_PREPROCESS' {
        cpus = 4
        memory = 16.GB
        time = 4.h
    }
}
```

## Plugin Architecture

### callbarcodes Plugin

Implements barcode calling logic:

- Reads multi-cycle fluorescence images
- Identifies brightest channel per cycle
- Constructs barcode sequences
- Assigns barcodes to cells

Usage in pipeline:

```xml
<RunCellpose>
    <plugin_name>callbarcodes</plugin_name>
    <!-- Plugin-specific parameters -->
</RunCellpose>
```

### compensatecolors Plugin

Performs spectral unmixing:

- Corrects fluorescence bleed-through between channels
- Improves barcode calling accuracy

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

**Solution**: Ensure plugin URL is accessible:

```bash
wget -O callbarcodes.py ${PLUGIN_URL}
cellprofiler --plugins-directory=.
```

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

### Debugging

Enable CellProfiler debugging:

```bash
cellprofiler \
    -c -r \
    -p pipeline.cppipe \
    --log-level=DEBUG \
    --data-file=load_data.csv
```

## Best Practices

1. **Validate pipelines**: Test `.cppipe` files in CellProfiler GUI first
2. **Template metadata**: Use template variables for flexibility
3. **Resource tuning**: Profile memory usage and adjust allocation
4. **Plugin versioning**: Pin plugin versions for reproducibility
5. **Output validation**: Check output file counts match expectations

## Next Steps

- [Python Scripts](python-scripts.md) - Understand CSV generation
- [Architecture](architecture.md) - Overall pipeline design
- [Testing](testing.md) - Test CellProfiler integration
