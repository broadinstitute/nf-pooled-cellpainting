# Load Data CSV Generation - Current Implementation

**Last Updated**: 2025-11-12
**Purpose**: Documentation of current approach for generating `load_data.csv` files for CellProfiler processes

---

## Overview

The pipeline generates `load_data.csv` files for CellProfiler using Python scripts. Metadata (Batch, Plate, Well, Site) originates from the input samplesheet and flows through Nextflow channels, with different processes using either metadata-driven or filename-driven approaches.

---

## Metadata Sources

### Input Samplesheet

**Location**: User-provided CSV (e.g., `assets/samplesheet.csv`)
**Schema**: `assets/schema_input.json`

**Required Columns**:

```csv
path,arm,batch,plate,well,site,channels,cycle,n_frames
```

**Example**:

```csv
s3://bucket/WellA1_PointA1_0000_ChannelPhalloidin,CHN2,DNA_Seq0000.ome.tiff,painting,Batch1,Plate1,A1,1,"Phalloidin,CHN2,DNA",1,3
```

### Metadata Flow Through Pipeline

**Entry Point**: `main.nf:57-70`

- Parses samplesheet using `samplesheetToList()` plugin
- Creates channels with structure: `[meta, image_path]`

**Meta Map Structure**:

```groovy
[
    batch: "Batch1",
    plate: "Plate1",
    well: "A1",
    site: 1,
    cycle: 1,  // barcoding only
    channels: "Phalloidin,CHN2,DNA",
    arm: "painting" | "barcoding",
    id: "Batch1_Plate1_A1"  // auto-generated
]
```

---

## Python Scripts

### 1. generate_load_data_csv.py

**Location**: `bin/generate_load_data_csv.py`
**Purpose**: General-purpose CSV generator for all pipeline stages

**Supported Pipeline Types**:

- `illumcalc` - Illumination calculation
- `illumapply` - Illumination correction
- `segcheck` - Segmentation QC
- `analysis` - Full analysis
- `preprocess` - Barcoding preprocessing
- `combined` - Combined painting + barcoding

**Key Functions**:

| Function                    | Lines   | Purpose                                                                    |
| --------------------------- | ------- | -------------------------------------------------------------------------- |
| `parse_original_image()`    | 83-138  | Parse: `WellA1_PointA1_0000_ChannelCHN1,CHN2_Seq0000.ome.tiff`             |
| `parse_corrected_image()`   | 141-159 | Parse: `Plate_{plate}_Well_{well}_Site_{site}_Corr{channel}.tiff`          |
| `parse_preprocess_image()`  | 162-197 | Parse: `Plate_{plate}_Well_{well}_Site_{site}_Cycle{cycle}_{channel}.tiff` |
| `collect_and_group_files()` | 408-676 | Group files by (plate, well, site)                                         |
| `generate_csv_rows()`       | 679-897 | Create CSV rows with metadata columns                                      |

### 2. generate_combined_load_data.py

**Location**: `bin/generate_combined_load_data.py`
**Purpose**: Specialized CSV for combined analysis (painting + barcoding)

**Key Functions**:

| Function                    | Lines   | Purpose                                        |
| --------------------------- | ------- | ---------------------------------------------- |
| `parse_combined_image()`    | 20-60   | Parse both corrected and cycle-specific images |
| `collect_and_group_files()` | 90-187  | Group and separate barcoding vs cellpainting   |
| `generate_csv_rows()`       | 190-257 | Create unified CSV with both image types       |

---

## Process Implementations

### Pattern A: Metadata-Driven

**Processes**: ILLUMCALC, ILLUMAPPLY
**Approach**: Pass metadata as CLI arguments to Python script

#### CELLPROFILER_ILLUMCALC

**File**: `modules/local/cellprofiler/illumcalc/main.nf:28-36`

```bash
generate_load_data_csv.py \
    --pipeline-type illumcalc \
    --images-dir ./images \
    --output load_data.csv \
    --channels "${channels}" \        # from meta.channels
    --cycle ${cycle} \                # from meta.cycle (if barcoding)
    --plate ${meta.plate} \           # SOURCE: meta.plate
    --has-cycles                      # if barcoding
```

**Metadata Passed**:

- `meta.plate` → `--plate` → `Metadata_Plate` column
- `meta.channels` → `--channels` → column headers
- `meta.cycle` → `--cycle` → `Metadata_Cycle` column

**Parsed from Filenames**:

- Well (e.g., "A1" from "WellA1\_...")
- Site (numeric from "Point{site}\_...")

---

#### CELLPROFILER_ILLUMAPPLY

**File**: `modules/local/cellprofiler/illumapply/main.nf:28-36`

```bash
generate_load_data_csv.py \
    --pipeline-type illumapply \
    --images-dir ./images \
    --illum-dir ./images \
    --output load_data.csv \
    --channels "${channels}" \        # from meta.channels
    --cycles ${cycles.join(',')} \    # from meta (if multi-cycle)
    --plate ${meta.plate} \           # SOURCE: meta.plate
    --has-cycles                      # if barcoding
```

**Metadata Passed**:

- `meta.plate` → `Metadata_Plate`
- `meta.channels` → column headers

**Parsed from Filenames**:

- Well
- Site

---

### Pattern B: Filename-Driven

**Processes**: PREPROCESS, COMBINEDANALYSIS
**Approach**: Extract ALL metadata from standardized filenames

#### CELLPROFILER_PREPROCESS

**File**: `modules/local/cellprofiler/preprocess/main.nf:30-33`

```bash
generate_load_data_csv.py \
    --pipeline-type preprocess \
    --images-dir ./images \
    --output load_data.csv
```

**All Metadata Parsed from Filename**:

- Pattern: `Plate_{plate}_Well_{well}_Site_{site}_Cycle{cycle}_{channel}.tiff`
- Example: `Plate_Plate1_Well_A1_Site_1_Cycle01_A.tiff`

---

#### CELLPROFILER_COMBINEDANALYSIS

**File**: `modules/local/cellprofiler/combinedanalysis/main.nf:34-36`

```bash
generate_combined_load_data.py \
    --images-dir ./images \
    --output load_data.csv
```

**Handles Two Filename Patterns**:

1. Cell Painting: `Plate_{plate}_Well_{well}_Site_{site}_Corr{channel}.tiff`
2. Barcoding: `Plate_{plate}_Well_{well}_Site_{site}_Cycle{cycle}_{channel}.tiff`

---

## Metadata Field Sources

| Field        | Primary Source                                   | Fallback                             | Used In CSV           | Code Location                        |
| ------------ | ------------------------------------------------ | ------------------------------------ | --------------------- | ------------------------------------ |
| **Batch**    | Samplesheet → `meta.batch`                       | -                                    | No (grouping only)    | `main.nf:69`                         |
| **Plate**    | Samplesheet → `meta.plate` → `--plate` arg       | Parsed from filename/path            | Yes: `Metadata_Plate` | `generate_load_data_csv.py:492, 736` |
| **Well**     | Parsed from filename                             | Samplesheet `meta.well` (not passed) | Yes: `Metadata_Well`  | `parse_*_image()` functions          |
| **Site**     | Parsed from filename                             | Samplesheet `meta.site` (not passed) | Yes: `Metadata_Site`  | `parse_*_image()` functions          |
| **Cycle**    | Samplesheet → `meta.cycle` → `--cycle` arg       | Parsed from filename                 | Yes: `Metadata_Cycle` | `generate_load_data_csv.py:745-748`  |
| **Channels** | Samplesheet → `meta.channels` → `--channels` arg | Parsed from filename                 | Yes: Column headers   | `generate_load_data_csv.py:813, 766` |

---

## CSV Output Structures

### Standard (Cell Painting ILLUMAPPLY)

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,FileName_OrigDNA,Frame_OrigDNA,FileName_IllumDNA,...
Plate1,A1,1,WellA1_Point_0000.ome.tiff,0,Plate1_IllumDNA.npy,...
```

### With Cycles (Barcoding ILLUMAPPLY)

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,Metadata_Cycle,FileName_Cycle01_OrigA,Frame_Cycle01_OrigA,...
Plate1,A1,1,1,filename.ome.tiff,0,...
```

### Preprocess

```csv
Metadata_Plate,Metadata_Site,Metadata_Well,Metadata_Well_Value,FileName_Cycle01_A,FileName_Cycle01_C,...
Plate1,1,A1,A1,file1.tiff,file2.tiff,...
```

### Combined Analysis

```csv
Metadata_Plate,Metadata_Site,Metadata_Well,Metadata_Well_Value,FileName_CorrDNA,FileName_Cycle01_A,...
Plate1,1,A1,A1,corrected.tiff,cycle1.tiff,...
```

---

## Data Flow Example

### Input

**Samplesheet Row**:

```csv
s3://bucket/WellA1_Point_0000.ome.tiff,painting,Batch1,Plate1,A1,"DNA,Phalloidin",1,1,3
```

### Processing

**Channel Element** (after parsing):

```groovy
[
    [batch: "Batch1", plate: "Plate1", well: "A1", site: 1,
     channels: "DNA,Phalloidin", arm: "painting"],
    "s3://bucket/WellA1_Point_0000.ome.tiff"
]
```

**After ILLUMCALC** (outputs per plate):

```
Plate1_IllumDNA.npy
Plate1_IllumPhalloidin.npy
```

**After ILLUMAPPLY** (outputs per well+site):

```
Plate_Plate1_Well_A1_Site_1_CorrDNA.tiff
Plate_Plate1_Well_A1_Site_1_CorrPhalloidin.tiff
```

### Output

**ILLUMAPPLY load_data.csv**:

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,FileName_OrigDNA,Frame_OrigDNA,FileName_IllumDNA,FileName_OrigPhalloidin,Frame_OrigPhalloidin,FileName_IllumPhalloidin
Plate1,A1,1,WellA1_Point_0000.ome.tiff,0,Plate1_IllumDNA.npy,WellA1_Point_0000.ome.tiff,1,Plate1_IllumPhalloidin.npy
```

---

## Channel Grouping Strategies

### Cellpainting Subworkflow

**File**: `subworkflows/local/cellpainting/main.nf`

**For ILLUMCALC** (lines 30-46):

```groovy
group_key = [
    batch: meta.batch,
    plate: meta.plate,
    id: "${meta.batch}_${meta.plate}"
]
// Groups all images from same batch+plate
```

**For ILLUMAPPLY** (lines 84-101):

```groovy
group_key = [
    batch: meta.batch,
    plate: meta.plate,
    well: meta.well,
    arm: meta.arm,
    id: "${meta.batch}_${meta.plate}_${meta.well}"
]
// Groups all sites from same well
```

### Barcoding Subworkflow

**File**: `subworkflows/local/barcoding/main.nf`

**For ILLUMCALC** (lines 30-47):

```groovy
group_key = [
    batch: meta.batch,
    plate: meta.plate,
    cycle: meta.cycle,
    id: "${meta.batch}_${meta.plate}_${meta.cycle}"
]
// Groups all images from same batch+plate+cycle
```

**For ILLUMAPPLY** (lines 82-102):

```groovy
site_key = [
    batch: meta.batch,
    plate: meta.plate,
    well: meta.well,
    site: meta.site,
    arm: meta.arm,
    id: "${meta.batch}_${meta.plate}_${meta.well}_Site${meta.site}"
]
// Groups by individual site
```

---

## Current Approach Analysis

### Advantages

1. **Flexible**: Can work with or without explicit metadata CLI args
2. **Resilient**: Falls back to filename parsing when metadata not provided
3. **Traceable**: Metadata flows from samplesheet through channels
4. **Modular**: Separate scripts for different use cases

### Inconsistencies

1. **Mixed Approach**: Some processes pass metadata as args, others parse from filenames
2. **Redundancy**: Well and Site parsed from filenames even when available in `meta` map
3. **Coupling**: Plate name must match between samplesheet and filenames for combined analysis
4. **Two Scripts**: Separate scripts for standard vs combined analysis

### Potential Refactoring Goals

1. Standardize on single approach (prefer metadata-driven)
2. Pass all available metadata from `meta` map to scripts
3. Use filename parsing only as fallback validation
4. Consolidate scripts if possible
5. Ensure consistent filename generation across all processes
6. Add validation that samplesheet metadata matches filename-parsed metadata

---

## Key Code Locations

| Component                    | File                                                  | Lines  | Description                 |
| ---------------------------- | ----------------------------------------------------- | ------ | --------------------------- |
| **Samplesheet Entry**        | `main.nf`                                             | 69     | Parse input CSV             |
| **Schema Validation**        | `assets/schema_input.json`                            | -      | Define required columns     |
| **Main Script**              | `bin/generate_load_data_csv.py`                       | -      | General CSV generation      |
| **Combined Script**          | `bin/generate_combined_load_data.py`                  | -      | Combined analysis CSV       |
| **ILLUMCALC Module**         | `modules/local/cellprofiler/illumcalc/main.nf`        | 28-36  | Pass plate from meta        |
| **ILLUMAPPLY Module**        | `modules/local/cellprofiler/illumapply/main.nf`       | 28-36  | Pass plate+cycles from meta |
| **PREPROCESS Module**        | `modules/local/cellprofiler/preprocess/main.nf`       | 30-33  | No metadata args            |
| **COMBINEDANALYSIS Module**  | `modules/local/cellprofiler/combinedanalysis/main.nf` | 34-36  | No metadata args            |
| **Cellpainting Subworkflow** | `subworkflows/local/cellpainting/main.nf`             | 30-101 | Channel grouping logic      |
| **Barcoding Subworkflow**    | `subworkflows/local/barcoding/main.nf`                | 30-102 | Channel grouping logic      |

---

## Testing Reference

**Test File**: `modules/local/cellprofiler/preprocess/tests/main.nf.test`
**Snapshot**: `modules/local/cellprofiler/preprocess/tests/main.nf.test.snap`

**Example Test Metadata**:

```groovy
meta = [
    id: "Batch1_Plate1_barcoding_A1",
    batch: "Batch1",
    plate: "Plate1",
    well: "A1",
    arm: "barcoding"
]
```

**Expected Output Filename**:

```
Plate_Plate1_Well_A1_Site0_Cycle01_A.tiff
```

This confirms metadata flows: Samplesheet → meta map → output filenames → CSV parsing
