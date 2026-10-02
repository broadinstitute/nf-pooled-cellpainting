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

Generates `load_data.csv` files required by CellProfiler processes. This is the **primary data staging script** used throughout the pipeline, and it is the same script for all 5 CellProfiler modules (`illumcalc`, `illumapply`, `segcheck`, `preprocess`, `combinedanalysis`) - there is no per-module branching, filename parsing, or file discovery in the script itself.

### Usage

```bash
generate_load_data_csv.py \
    --metadata-json metadata.json \
    --images-dir ./images \
    --output load_data.csv \
    [--illum-dir ./images --include-illum-files] \
    [--range-skip N] \
    [--has-cycles] \
    [--cycle N] \
    [--cycle-metadata-name Cycle] \
    [--outdir <pipeline outdir>]
```

### Parameters

| Parameter               | Required | Description                                                                                          |
| ------------------------ | -------- | ------------------------------------------------------------------------------------------------------ |
| `--metadata-json`        | Yes      | Path to the canonical metadata JSON file (see below) built by the calling Nextflow module            |
| `--images-dir`           | No       | Directory containing input images (default: `./images`)                                              |
| `--output`               | No       | Output CSV file path (default: `load_data.csv`)                                                        |
| `--include-illum-files`  | No       | Also emit `FileName_Illum<Channel>` columns by scanning `--illum-dir` for `.npy` files (illumapply only) |
| `--illum-dir`            | No       | Directory containing illumination `.npy` files; required if `--include-illum-files` is set            |
| `--range-skip`           | No       | Subsample sites per well - keep every Nth site (default: 1 = all sites)                                |
| `--has-cycles`           | No       | Emit a `Metadata_<cycle-metadata-name>` column (barcoding workflows)                                    |
| `--cycle`                | No       | Override the cycle number used for the `Metadata_Cycle` column instead of the JSON metadata's `cycle`  |
| `--cycle-metadata-name`  | No       | Name for the cycle metadata column (default: `Cycle`, giving `Metadata_Cycle`)                          |
| `--outdir`               | No       | Pipeline `--outdir`, used to construct durable/original paths for illumination `.npy` files            |

### The canonical metadata JSON

Every caller builds the same top-level object, with one `image_metadata` entry per (physical file, channel) pair:

```json
{
  "plate": "Plate1", "batch": "Batch1", "cycles": [1, 2, 3],
  "image_metadata": [
    {
      "well": "A1", "site": 0, "arm": "painting",
      "cycle": 1, "channel": "DNA", "frame_index": 2, "column_prefix": "Orig",
      "filename": "...", "original_path": "...", "original_filename": "..."
    }
  ]
}
```

| Field                | Required | Description                                                                                          |
| --------------------- | -------- | ------------------------------------------------------------------------------------------------------ |
| `plate` / `batch`     | plate required | Top-level identifiers, stated once by the Nextflow caller                                      |
| `cycles`              | If any entry has a `cycle` | List of distinct cycle numbers present in `image_metadata`; must match exactly, or the script fails loudly |
| `well` / `site`       | Yes (per entry) | Grouping key for CSV rows, alongside `plate`                                                    |
| `arm`                 | Yes (per entry) | `painting` or `barcoding` - carried for debugging only, never branched on                        |
| `channel`             | Yes (per entry) | The channel name used to build the CellProfiler column name                                       |
| `column_prefix`       | Yes (per entry) | `""`, `"Orig"`, or `"Corr"` - the actual driver of the column name; determined by which cppipe stage will read the column, not by `arm` |
| `filename`            | Yes (per entry) | Path relative to `--images-dir`; trusted directly, joined and checked for existence - no glob or pattern matching |
| `cycle`               | Barcoding only | Cycle number this entry belongs to                                                                |
| `frame_index`         | Multichannel files only | Present iff this channel is one frame of a multi-frame/multichannel file; its presence is what makes the `Frame_<name>` column appear |
| `original_path` / `original_filename` | No | Used to populate `FinalFileName_<name>` with the pre-staging path                        |

One physical multi-frame file (e.g. a 3-frame OME-TIFF) contributes multiple `image_metadata` entries sharing one `filename`, differing in `channel`/`frame_index`. A single-channel file contributes one entry with `frame_index` omitted.

### Column naming

A single rule replaces the old per-pipeline-type branches:

```
name = f"{cycle_prefix}{column_prefix}{channel}"
cycle_prefix = f"Cycle{cycle:02d}_" if (cycle is not None and more than one distinct cycle across the plate) else ""
```

`FileName_<name>` and `FinalFileName_<name>` are always emitted; `Frame_<name>` is emitted only when the entry carries a `frame_index`. When `--include-illum-files` is set, a matching `FileName_Illum<name>` / `FinalFileName_Illum<name>` pair is added by looking up illumination `.npy` files collected from `--illum-dir` (these aren't part of `image_metadata` - they're still matched by scanning the directory and parsing `{plate}_Illum{channel}.npy` / `{plate}_Cycle{N}_Illum{channel}.npy` filenames).

### CSV Output Structures

**Standard (Cell Painting, illumcalc/illumapply)**:

|Metadata_Plate|Metadata_Well|Metadata_Site|FileName_OrigDNA          |Frame_OrigDNA|FileName_IllumDNA  |...|
|--------------|-------------|-------------|--------------------------|-------------|-------------------|---|
|Plate1        |A1           |1            |WellA1_Point_0000.ome.tiff|0            |Plate1_IllumDNA.npy|...|

**With Cycles (Barcoding, preprocess)**:

|Metadata_Plate|Metadata_Well|Metadata_Site|Metadata_Cycle|FileName_Cycle01_A|...|
|--------------|-------------|-------------|--------------|------------------|---|
|Plate1        |A1           |1            |1             |filename.tiff     |...|

**Combined Analysis**:

|Metadata_Plate|Metadata_Site|Metadata_Well|FileName_CorrDNA|FileName_Cycle01_A|...|
|--------------|-------------|-------------|----------------|------------------|---|
|Plate1        |1            |A1           |corrected.tiff  |cycle1.tiff       |...|

### Implementation Details

The script:

1. **Loads and validates** the metadata JSON, cross-checking declared `cycles` against the cycles actually present in `image_metadata`
2. **Joins and checks existence** of `images_dir + entry['filename']` directly for every entry - no directory glob, no filename regex, no substring search
3. **Groups entries** by `(plate, well, site)`, optionally subsampling sites per well via `--range-skip`
4. **Generates CSV rows** using the single column-naming rule above

### Error Handling

The script fails loudly (non-zero exit, descriptive `ValueError`) on:

- A metadata JSON entry referencing a file that doesn't exist under `--images-dir`
- Missing required per-entry fields (`well`, `site`, `arm`, `channel`, `column_prefix`, `filename`)
- An `arm` or `column_prefix` value outside the allowed set
- A mismatch between the declared top-level `cycles` and the cycles actually present in entries

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

### Adding a New CellProfiler Stage

Because every module already builds the same canonical metadata JSON, adding a new CellProfiler stage does **not** require touching `generate_load_data_csv.py` at all - the script has no per-stage branching left to extend. Instead:

1. **Build the metadata JSON in the new module's Groovy code**, using `expandImageChannels`/`buildLoadDataMetadata` from `subworkflows/local/utils_nfcore_nf-pooled-cellpainting_pipeline/main.nf` (or constructing the equivalent `{plate, batch, cycles, image_metadata}` shape by hand), choosing the right `column_prefix` (`""`/`"Orig"`/`"Corr"`) for whichever cppipe stage will read the resulting CSV.
2. **Call the script unchanged** from the new module's `script:` block:

```groovy
script:
def metadata_json_content = groovy.json.JsonOutput.toJson(image_metas)
def metadata_base64 = metadata_json_content.bytes.encodeBase64().toString()
"""
echo '${metadata_base64}' | base64 -d > metadata.json

generate_load_data_csv.py \
    --metadata-json metadata.json \
    --images-dir ./images \
    --output load_data.csv \
    --cycle-metadata-name "${params.cycle_metadata_name}"
"""
```

3. **Add a `modules/local/cellprofiler/<newstage>/tests/main.nf.test`** fixture using the same canonical schema as the other 5 modules' fixtures.

### Testing Scripts

Test the script in isolation with a hand-built metadata JSON:

```bash
# Create test data
mkdir -p test_images
touch test_images/WellA1_Site0_DAPI.tiff
touch test_images/WellA1_Site0_GFP.tiff

cat > metadata.json <<'EOF'
{
  "plate": "Plate1",
  "image_metadata": [
    {"well": "A1", "site": 0, "arm": "painting", "channel": "DAPI", "column_prefix": "Orig", "filename": "WellA1_Site0_DAPI.tiff"},
    {"well": "A1", "site": 0, "arm": "painting", "channel": "GFP", "column_prefix": "Orig", "filename": "WellA1_Site0_GFP.tiff"}
  ]
}
EOF

# Run script
python bin/generate_load_data_csv.py \
    --metadata-json metadata.json \
    --images-dir test_images \
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
