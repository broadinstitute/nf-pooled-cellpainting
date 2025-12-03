# Python Scripts

The pipeline includes helper Python scripts that handle data preparation and quality control. You generally don't need to modify these scripts, but understanding what they do helps with debugging when things go wrong.

## Overview

These scripts live in the `bin/` directory and are automatically available to all pipeline processes:

- `generate_load_data_csv.py`: Universal CSV generator for CellProfiler
- `qc_barcode_align.py`: Barcode alignment quality control
- `qc_barcode_preprocess.py`: Barcode preprocessing quality control

These scripts are automatically available in the process `PATH` and are called during pipeline execution.

## generate_load_data_csv.py

### Purpose

Generates `load_data.csv` files required by CellProfiler processes. This is the **primary data staging script** used throughout the pipeline. 

### Usage

```python
generate_load_data_csv.py \
    --pipeline_type <type> \
    --channels <channel_list> \
    --frames <frame_list> \
    --cycles <cycle_list> \
    --output load_data.csv
```

### Parameters

| Parameter         | Required | Description                                                                                 |
| ----------------- | -------- | ------------------------------------------------------------------------------------------- |
| `--pipeline_type` | Yes      | Pipeline stage: `illumcalc`, `illumapply`, `segcheck`, `analysis`, `preprocess`, `combined` |
| `--channels`      | Yes      | Comma-separated channel names (e.g., `DAPI,GFP,RFP`)                                        |
| `--frames`        | No       | Comma-separated frame indices (e.g., `0,1,2,3`)                                             |
| `--cycles`        | No       | Comma-separated cycle numbers (e.g., `1,2,3`) - barcoding only                              |
| `--output`        | Yes      | Output CSV file path                                                                        |

### Pipeline Types

#### 1. `illumcalc` - Illumination Calculation

Stages original multi-channel images for illumination function calculation.

**Output columns**:

```
Metadata_Plate, Metadata_Well, Metadata_Site, Metadata_Frame, FileName_<Channel>
```

**Example**:

```python
generate_load_data_csv.py \
    --pipeline_type illumcalc \
    --channels DAPI,GFP,RFP \
    --frames 0,1,2,3 \
    --output load_data.csv
```

#### 2. `illumapply` - Illumination Application

Stages original images alongside illumination functions for correction.

**Output columns**:

```
Metadata_Plate, Metadata_Well, Metadata_Site, Metadata_Frame,
FileName_Orig<Channel>, FileName_Illum<Channel>
```

**Example**:

```python
generate_load_data_csv.py \
    --pipeline_type illumapply \
    --channels DAPI,GFP,RFP \
    --frames 0,1,2,3 \
    --output load_data.csv
```

#### 3. `segcheck` - Segmentation Check

Stages corrected images for segmentation quality control.

**Output columns**:

```
Metadata_Plate, Metadata_Well, Metadata_Site, Metadata_Frame, FileName_Corr<Channel>
```

#### 4. `preprocess` - Barcoding Preprocessing

Stages cycle-based images for barcode calling.

**Output columns**:

```
Metadata_Plate, Metadata_Well, Metadata_Site, Metadata_Frame, Metadata_Cycle,
FileName_Cycle<N>_<Channel>
```

**Example**:

```python
generate_load_data_csv.py \
    --pipeline_type preprocess \
    --channels Cy3,Cy5 \
    --cycles 1,2,3 \
    --frames 0,1,2,3 \
    --output load_data.csv
```

#### 5. `combined` - Combined Analysis

Stages both painting (corrected) and barcoding (preprocessed) images.

**Output columns**:

```
Metadata_Plate, Metadata_Well, Metadata_Site, Metadata_Frame,
FileName_Corr<Channel>, FileName_Cycle<N>_<Channel>
```

### Metadata Flow

Metadata originates from the input samplesheet and flows through Nextflow channels to the Python scripts. The scripts use two approaches:

**Pattern A: Metadata-Driven** (ILLUMCALC, ILLUMAPPLY)

Metadata is passed as CLI arguments from the Nextflow `meta` map:

```bash
generate_load_data_csv.py \
    --pipeline-type illumcalc \
    --images-dir ./images \
    --plate ${meta.plate} \      # from samplesheet
    --channels "${channels}" \   # from meta.channels
    --output load_data.csv
```

**Pattern B: Filename-Driven** (PREPROCESS, COMBINEDANALYSIS)

All metadata is extracted from standardized filenames:

```bash
generate_load_data_csv.py \
    --pipeline-type preprocess \
    --images-dir ./images \
    --output load_data.csv
```

### Filename Patterns

The script parses different filename patterns depending on the pipeline stage:

| Image Type | Pattern | Example |
| :--------- | :------ | :------ |
| Original | `Well{well}_Point{site}_{frame}_Channel{channels}_Seq*.ome.tiff` | `WellA1_PointA1_0000_ChannelDNA,GFP_Seq0000.ome.tiff` |
| Corrected | `Plate_{plate}_Well_{well}_Site_{site}_Corr{channel}.tiff` | `Plate_Plate1_Well_A1_Site_1_CorrDNA.tiff` |
| Illumination | `{plate}_Illum{channel}.npy` | `Plate1_IllumDNA.npy` |
| Cycle | `Plate_{plate}_Well_{well}_Site_{site}_Cycle{cycle}_{channel}.tiff` | `Plate_Plate1_Well_A1_Site_1_Cycle01_A.tiff` |

### CSV Output Structures

Different pipeline types produce different CSV structures:

**Standard (Cell Painting)**:

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,FileName_OrigDNA,Frame_OrigDNA,FileName_IllumDNA,...
Plate1,A1,1,WellA1_Point_0000.ome.tiff,0,Plate1_IllumDNA.npy,...
```

**With Cycles (Barcoding)**:

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,Metadata_Cycle,FileName_Cycle01_OrigA,Frame_Cycle01_OrigA,...
Plate1,A1,1,1,filename.ome.tiff,0,...
```

**Combined Analysis**:

```csv
Metadata_Plate,Metadata_Site,Metadata_Well,FileName_CorrDNA,FileName_Cycle01_A,...
Plate1,1,A1,corrected.tiff,cycle1.tiff,...
```

### Implementation Details

The script:

1. **Scans directories** for TIFF images matching expected patterns
2. **Parses filenames** to extract metadata (plate, well, site, frame, channel, cycle)
3. **Groups images** by metadata keys
4. **Generates CSV** with proper CellProfiler column names

### Error Handling

The script validates:

- File existence
- Metadata completeness
- Channel consistency
- Frame/cycle ranges

## qc_barcode_align.py

### Purpose

Jupyter notebook for analyzing barcode alignment quality across cycles.

### Functionality

1. **Load cycle images**: Reads corrected images from all cycles
2. **Calculate pixel shifts**: Measures X/Y displacement between cycles
3. **Compute correlations**: Calculates Pearson correlation between cycles
4. **Generate visualizations**:
    - Scatter plots of pixel shifts
    - Correlation heatmaps
    - Spatial shift maps
5. **Validate thresholds**: Checks against `barcoding_shift_threshold` and `barcoding_corr_threshold`

### Usage

```python
# In Jupyter or as script
qc_barcode_align.py \
    --input_dir /path/to/corrected/cycles/ \
    --shift_threshold 50 \
    --corr_threshold 0.9 \
    --output_dir qc/barcode_align/
```

### Output Files

- `shift_summary.csv`: Per-site shift statistics
- `correlation_matrix.csv`: Cycle-to-cycle correlations
- `shift_spatial_plot.png`: Spatial distribution of shifts
- `correlation_heatmap.png`: Correlation visualization
- `qc_report.html`: Interactive QC report

### QC Criteria

**Pass criteria**:

- Mean pixel shift < `barcoding_shift_threshold`
- Mean correlation > `barcoding_corr_threshold`

**Fail criteria**:

- Any site exceeds shift threshold
- Any cycle pair below correlation threshold

## Development Guide

### Adding New Pipeline Types

To support a new CellProfiler stage:

1. **Update `generate_load_data_csv.py`**:

```python
def generate_newtype_csv(images, channels, output):
    rows = []
    for img in images:
        row = {
            'Metadata_Plate': img.plate,
            'Metadata_Well': img.well,
            # ... additional metadata
            f'FileName_{channel}': img.filename
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(output, index=False)
```

2. **Add to pipeline type switch**:

```python
if pipeline_type == 'newtype':
    generate_newtype_csv(images, channels, output)
```

3. **Update process module**:

```groovy
script:
"""
generate_load_data_csv.py \
    --pipeline_type newtype \
    --channels ${meta.channels.join(',')} \
    --output load_data.csv
"""
```

### Testing Scripts

Test scripts in isolation:

```bash
# Create test data
mkdir -p test_images
touch test_images/P001_A01_1_0_DAPI.tif
touch test_images/P001_A01_1_0_GFP.tif

# Run script
python bin/generate_load_data_csv.py \
    --pipeline_type illumcalc \
    --channels DAPI,GFP \
    --frames 0 \
    --output test_load_data.csv

# Validate output
head test_load_data.csv
```

### Debugging

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Best Practices

1. **Validate inputs**: Check file existence before processing
2. **Handle edge cases**: Empty directories, missing frames, etc.
3. **Consistent naming**: Follow established filename conventions
4. **Error messages**: Provide clear, actionable error messages
5. **Logging**: Log key operations for debugging
6. **Testing**: Write unit tests for parsing logic

## Common Issues

### Missing Images

**Symptom**: CSV has fewer rows than expected

**Solution**: Check filename patterns match exactly:

```bash
ls test_images/ | grep -E "P[0-9]+_[A-Z][0-9]+_[0-9]+_[0-9]+_.*\.tif"
```

### Metadata Mismatches

**Symptom**: CellProfiler can't group images properly

**Solution**: Ensure metadata columns are populated correctly:

```python
df[['Metadata_Plate', 'Metadata_Well', 'Metadata_Site']].drop_duplicates()
```

## Next Steps

- [Architecture](architecture.md) - Understand where scripts are called
- [CellProfiler Integration](cellprofiler.md) - How CSV files are used
- [Testing](testing.md) - Test script integration
