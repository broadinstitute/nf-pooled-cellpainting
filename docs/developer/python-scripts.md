# Python Scripts

Documentation of Python scripts used for data staging and quality control.

## Overview

The pipeline includes several Python scripts in the `bin/` directory:

- `generate_load_data_csv.py`: Universal CSV generator for CellProfiler
- `generate_combined_load_data.py`: Specialized CSV for combined analysis
- `qc_barcode_align.py`: Barcode alignment quality control

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

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--pipeline_type` | Yes | Pipeline stage: `illumcalc`, `illumapply`, `segcheck`, `analysis`, `preprocess`, `combined` |
| `--channels` | Yes | Comma-separated channel names (e.g., `DAPI,GFP,RFP`) |
| `--frames` | No | Comma-separated frame indices (e.g., `0,1,2,3`) |
| `--cycles` | No | Comma-separated cycle numbers (e.g., `1,2,3`) - barcoding only |
| `--output` | Yes | Output CSV file path |

### Pipeline Types

#### 1. `illumcalc` - Illumination Calculation

Stages original multi-channel images for illumination function calculation.

**Output columns**:
```
Metadata_Plate, Metadata_Well, Metadata_Site, Metadata_Frame,
FileName_<Channel>, PathName_<Channel>
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
FileName_Orig<Channel>, PathName_Orig<Channel>,
FileName_Illum<Channel>, PathName_Illum<Channel>
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
Metadata_Plate, Metadata_Well, Metadata_Site, Metadata_Frame,
FileName_Corr<Channel>, PathName_Corr<Channel>
```

#### 4. `preprocess` - Barcoding Preprocessing

Stages cycle-based images for barcode calling.

**Output columns**:
```
Metadata_Plate, Metadata_Well, Metadata_Site, Metadata_Frame, Metadata_Cycle,
FileName_Cycle<N>_<Channel>, PathName_Cycle<N>_<Channel>
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
FileName_Corr<Channel>, PathName_Corr<Channel>,
FileName_Cycle<N>_<Channel>, PathName_Cycle<N>_<Channel>
```

### Implementation Details

The script:

1. **Scans directories** for TIFF images matching expected patterns
2. **Parses filenames** to extract metadata:
    - Plate, well, site, frame
    - Channel name
    - Cycle (for barcoding)
3. **Groups images** by metadata keys
4. **Generates CSV** with proper CellProfiler column names

### Filename Parsing

Expected filename patterns:

```python
# Original images
{plate}_{well}_{site}_{frame}_{channel}.tif

# Corrected images
{plate}_{well}_{site}_Corr{channel}.tif

# Illumination functions
{plate}_Illum{channel}.npy

# Cycle images
{plate}_{well}_{site}_{frame}_Cycle{cycle}_{channel}.tif
```

### Error Handling

The script validates:

- File existence
- Metadata completeness
- Channel consistency
- Frame/cycle ranges

## generate_combined_load_data.py

### Purpose

Specialized script for combined analysis that merges painting and barcoding data.

### Usage

```python
generate_combined_load_data.py \
    --painting_dir /path/to/corrected/ \
    --barcoding_dir /path/to/preprocessed/ \
    --channels DAPI,GFP,RFP \
    --barcode_channels Cy3,Cy5 \
    --cycles 1,2,3 \
    --output combined_load_data.csv
```

### Key Features

1. **Dual directory scanning**: Reads from both painting and barcoding outputs
2. **Metadata alignment**: Matches images by `(plate, well, site)`
3. **Mixed column generation**: Creates both `Corr` and `Cycle` columns

### Output Format

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,Metadata_Frame,FileName_CorrDAPI,PathName_CorrDAPI,FileName_Cycle1_Cy3,PathName_Cycle1_Cy3,...
P001,A01,1,0,P001_A01_1_CorrDAPI.tif,/painting/corrected/,P001_A01_1_0_Cycle1_Cy3.tif,/barcoding/preprocessed/,...
```

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
            f'FileName_{channel}': img.filename,
            f'PathName_{channel}': img.path
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

### Path Issues

**Symptom**: CellProfiler can't find images

**Solution**: Use absolute paths or ensure relative paths are correct:
```python
PathName = os.path.abspath(image_dir)
```

## Next Steps

- [Architecture](architecture.md) - Understand where scripts are called
- [CellProfiler Integration](cellprofiler.md) - How CSV files are used
- [Testing](testing.md) - Test script integration
