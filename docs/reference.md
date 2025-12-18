# Technical Reference

This document provides detailed technical information about the nf-pooled-cellpainting pipeline architecture, CellProfiler integration, Python scripts, and output formats.

## Table of Contents

- [Architecture](#architecture)
- [CellProfiler Integration](#cellprofiler-integration)
- [Python Scripts](#python-scripts)
- [Output Reference](#output-reference)

---

## Architecture

### Workflow Design

#### Main Workflow

The main workflow (`workflows/nf-pooled-cellpainting.nf`) orchestrates pipeline execution:

1. **Subworkflow Execution**: Runs CELLPAINTING and BARCODING subworkflows in parallel
2. **Combined Analysis**: Merges outputs from both arms (conditional on QC gates)
3. **MultiQC Report**: Generates unified QC report (conditional on QC gates)

#### Cell Painting Subworkflow

Located in `subworkflows/local/cellpainting/main.nf`. Organized into three logical phases:

**Phase 1: Illumination Correction**

| Process | Description | Grouping |
|---------|-------------|----------|
| ILLUMCALC | Calculate illumination corrections per plate | `[batch, plate]` |
| QC_MONTAGEILLUM | Generate illumination QC montages | |
| ILLUMAPPLY | Apply illumination corrections per site | `[batch, plate, well, site]` |

**Phase 2: Segmentation Quality Control**

| Process | Description | Grouping |
|---------|-------------|----------|
| SEGCHECK | Segmentation quality check (subsampled by `range_skip`) | `[batch, plate, well]` |
| QC_MONTAGE_SEGCHECK | Segmentation QC visualizations | |

**Phase 3: Image Stitching (Conditional)**

| Process | Description | Grouping |
|---------|-------------|----------|
| FIJI_STITCHCROP | Stitch and crop images (enabled when `qc_painting_passed`) | `[batch, plate, well]` |
| QC_MONTAGE_STITCHCROP | Stitching QC visualizations | |

#### Barcoding Subworkflow

Located in `subworkflows/local/barcoding/main.nf`. Organized into three logical phases:

**Phase 1: Illumination Correction**

| Process | Description | Grouping |
|---------|-------------|----------|
| ILLUMCALC | Calculate cycle-specific illumination corrections | `[batch, plate, cycle]` |
| QC_MONTAGEILLUM | Illumination QC montages | |
| ILLUMAPPLY | Apply illumination corrections | `[batch, plate, well]` |

**Phase 2: Barcode Quality Control and Preprocessing**

| Process | Description | Grouping |
|---------|-------------|----------|
| QC_BARCODEALIGN | Barcode alignment QC (validates against thresholds) | |
| PREPROCESS | Barcode calling and preprocessing | `[batch, plate, well, site]` |
| QC_PREPROCESS | Preprocessing QC visualizations | |

**Phase 3: Image Stitching (Conditional)**

| Process | Description | Grouping |
|---------|-------------|----------|
| FIJI_STITCHCROP | Stitch and crop images (enabled when `qc_barcoding_passed == true`) | `[batch, plate, well]` |

#### Combined Analysis (Conditional)

Located in `modules/local/cellprofiler/combinedanalysis/main.nf`. Executes when both `qc_painting_passed` and `qc_barcoding_passed` are `true`.

**Input Aggregation**: Combines cropped images from both arms, grouped by `[batch, plate, well, site]`:

- **From Cell Painting**: Corrected images (`CorrDNA`, `CorrPhalloidin`, `CorrCHN2`, etc.)
- **From Barcoding**: Preprocessed cycle images (`Cycle##_A`, `Cycle##_C`, `Cycle##_G`, `Cycle##_T`, `Cycle##_DNA`)

**Outputs**:

- Overlay images (PNG) showing segmentation results
- CSV statistics for Nuclei, Cells, Cytoplasm, Foci measurements
- Segmentation masks (TIFF)
- Consolidated `load_data.csv` for all samples

### Channel Architecture

#### Data Flow

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

#### Grouping Strategy

During workflow execution, input channels are grouped based on parallelization granularity. Example from painting illumination calculation:

```groovy
// Group images by batch and plate for illumination calculation
ch_illumcalc_input = ch_samplesheet_cp
    .map { meta, image ->
        def group_id = "${meta.batch}_${meta.plate}"
        def group_key = meta.subMap(['batch', 'plate']) + [id: group_id]
        def image_meta = meta + [filename: image.name]
        [group_key, image_meta, image]
    }
    .groupTuple()
    .map { meta, images_meta_list, images_list ->
        def all_channels = images_meta_list[0].channels
        [meta, all_channels, null, images_list, images_meta_list]
    }
```

For barcoding illumination apply, grouping can be at site or well level (controlled by `--barcoding_illumapply_grouping`):

```groovy
if (barcoding_illumapply_grouping == "site") {
    // Site-level grouping
    group_key = meta.subMap(['batch', 'plate', 'well', 'site', 'arm'])
    group_id = "${meta.batch}_${meta.plate}_${meta.well}_Site${meta.site}"
} else {
    // Well-level grouping (default)
    group_key = meta.subMap(['batch', 'plate', 'well', 'arm'])
    group_id = "${meta.batch}_${meta.plate}_${meta.well}"
}
```

### Process Design

#### Standard Process Structure

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
    generate_load_data_csv.py \\
        --pipeline_type example \\
        --output load_data.csv

    cellprofiler \\
        -c -r \\
        -p ${cppipe} \\
        -o output/ \\
        --data-file=load_data.csv
    """
}
```

#### Key Conventions

1. **Tagging**: Use image metadata for process identification
2. **Labels**: Apply resource labels (`qc`, `cellprofiler_basic`, `cellprofiler_medium`, `fiji`)
3. **Containers**: Specify container images explicitly
4. **Output channels**: Name channels with `emit:`
5. **Scripts**: Use Python helper script to generate load_data.csv

### QC Gate Implementation

#### Conditional Execution

Two parameters control progression: `qc_painting_passed` and `qc_barcoding_passed` (default: `false`).

```groovy
if (params.qc_painting_passed) {
    FIJI_STITCHCROP(
        CELLPROFILER_ILLUMAPPLY.out.corrected,
        ...
    )
}
```

The `when` parameter inside `FIJI_STITCHCROP` process prevents execution until the QC flag is `true`:

```groovy
process FIJI_STITCHCROP {
    when:
    params.qc_painting_passed  // or params.qc_barcoding_passed
    // ...
}
```

#### Manual Review Workflow

1. Run pipeline with default QC parameters (`false`)
2. Pipeline stops after initial QC checks
3. Review QC outputs in `results/workspace/qc_reports/`
4. Re-run with `--qc_painting_passed true` if QC passes
5. Pipeline resumes from cached results (`-resume`)

### Error Handling

#### Retry Strategy

Defined in `conf/base.config`:

```groovy
process {
    errorStrategy = { task.exitStatus in ((130..145) + 104 + 175) ? 'retry' : 'finish' }
    maxRetries    = 1
    maxErrors     = '-1'
}
```

Exit codes 130-145, 104, and 175 trigger automatic retry with increased resources.

### Testing and CI/CD

#### GitHub Actions Workflow

The pipeline uses GitHub Actions for continuous integration. Tests run automatically on pull requests (`.github/workflows/nf-test.yml`):

- **Trigger**: Pull requests (excluding docs, markdown, and image changes)
- **Container profile**: Docker only (Singularity is not tested)
- **Sharding**: Dynamically calculated as `min(affected_tests, 7)` - if your PR only changes one module, only that module's tests run
- **Change detection**: Only tests affected by changed files are executed (`nf-test --changed-since HEAD^`)

#### NF-test Structure

Tests are organized at two levels:

| Level | Location | Purpose |
|-------|----------|---------|
| **Module tests** | `modules/local/*/tests/main.nf.test` | Unit tests for individual processes |
| **Pipeline tests** | `tests/main.nf.test` | End-to-end integration tests |

Each test file contains multiple test cases. Most include both a "real" test and a "stub" test:

- **Real tests**: Run actual containers (CellProfiler, Fiji) and process images
- **Stub tests**: Skip containers entirely—each process has a `stub:` block that creates empty output files with correct names, allowing fast validation of workflow wiring and conditional logic

| Module | Test Cases | Container |
|--------|------------|-----------|
| `cellprofiler/illumcalc` | 2 | CellProfiler |
| `cellprofiler/illumapply` | 2 | CellProfiler |
| `cellprofiler/segcheck` | 2 | CellProfiler |
| `cellprofiler/preprocess` | 2 | CellProfiler |
| `cellprofiler/combinedanalysis` | 2 | CellProfiler |
| `fiji/stitchcrop` | 3 | Fiji |
| `qc/montageillum` | 4 | Python (numpy/pillow) |
| `qc/barcodealign` | 2 | Python (pandas) |
| `qc/preprocess` | 2 | Python (pandas) |
| `tests/main.nf.test` | 5 | Full pipeline |
| **Total** | **26** | |

The pipeline tests in `tests/main.nf.test` cover different QC gate scenarios:

- `qc_passed`: Full run with both QC flags true
- `stub`: Workflow logic without containers
- `stub_painting_qc_false`: Verifies combined analysis is skipped
- `stub_barcoding_qc_false`: Verifies combined analysis is skipped
- `stub_both_qc_false`: Verifies pipeline stops at QC phase

#### Handling Non-Reproducible Outputs

Image processing outputs (CellProfiler, Fiji) have non-reproducible checksums due to floating point operations, compression variations, and metadata differences. The pipeline handles this in two ways:

**1. Global ignore file** (`tests/.nftignore`):

```text
# Ignore all image types with unstable checksums
*.tiff
*.tif
*.npy
*.png
*.csv
*.html
```

**2. File existence assertions** in test files (see `modules/local/cellprofiler/combinedanalysis/tests/main.nf.test`):

```groovy
// Exclude specific files from snapshot, check existence instead
process.out.csv_stats.get(0).get(1).findAll {
    file(it).name != "Experiment.csv" &&
    file(it).name != "Image.csv"
}
// Then assert file exists separately
{ assert process.out.csv_stats.get(0).get(1).any { file(it).name == "Experiment.csv" } }
```

#### Updating Snapshots

**When to update snapshots:**

- Adding/removing output files or directories
- Changing output file structure or naming
- Modifying which processes run (affects task counts)
- Upgrading tools that change output format

**When you DON'T need to update snapshots:**

- Version bumps (Nextflow and pipeline versions are excluded from comparison)
- Refactoring code that doesn't change outputs
- Documentation changes

When intentionally changing outputs, update snapshots using **GitHub Codespaces** (recommended for macOS users):

```bash
# Create a codespace with enough resources (need 3+ CPUs for FIJI processes)
gh codespace create --repo broadinstitute/nf-pooled-cellpainting --branch dev --machine largePremiumLinux

# Open in browser
gh codespace code --codespace <name> --web

# Inside the codespace, run tests with snapshot update
nf-test test tests/main.nf.test --profile debug,test,docker --update-snapshot

# Review changes, commit, and push
git diff tests/main.nf.test.snap
git add tests/main.nf.test.snap
git commit -m "fix: regenerate snapshots"
git push

# Delete codespace when done (to avoid charges)
gh codespace delete --codespace <name>
```

!!! warning "Local macOS Limitations"
    Running `nf-test test --update-snapshot` locally on macOS may fail due to `workflow.trace` not being populated correctly with Nextflow edge versions. Use GitHub Codespaces instead.

This overwrites existing `.nf.test.snap` files. Review the diff carefully before committing.

---

## CellProfiler Integration

The pipeline uses CellProfiler v4.2.8 for image analysis tasks including illumination correction, image preprocessing, cell segmentation, feature extraction, and barcode calling.

### Process Modules

| Process | Purpose | Grouping | Key Outputs |
|---------|---------|----------|-------------|
| `ILLUMCALC` | Calculate illumination functions | Per plate (or plate+cycle) | `.npy` files |
| `ILLUMAPPLY` | Apply corrections | Per well or site | Corrected TIFF images |
| `SEGCHECK` | Segmentation QC | Per well (subsampled) | PNG previews, CSV stats |
| `PREPROCESS` | Barcode calling | Per site | Preprocessed TIFF, CSV |
| `COMBINEDANALYSIS` | Final segmentation | Per site | Masks, overlays, CSV |

### Pipeline Files (.cppipe)

CellProfiler pipelines are text files defining:

- Input modules (LoadData, LoadImages)
- Processing modules (CorrectIlluminationCalculate, ApplyIllumination)
- Output modules (SaveImages, ExportToSpreadsheet)

#### Required Pipeline Files

| File | Purpose | Inputs | Outputs |
|------|---------|--------|---------|
| `painting_illumcalc.cppipe` | Calculate painting illumination | Multi-channel raw images | `.npy` illumination functions |
| `painting_illumapply.cppipe` | Apply painting illumination | Raw images + illumination functions | Corrected TIFF images |
| `painting_segcheck.cppipe` | Segmentation QC | Corrected images | Segmentation previews |
| `barcoding_illumcalc.cppipe` | Calculate barcoding illumination | Multi-cycle raw images | Cycle-specific illumination functions |
| `barcoding_illumapply.cppipe` | Apply barcoding illumination | Raw cycle images + illumination functions | Corrected cycle images |
| `barcoding_preprocess.cppipe` | Barcode calling | Corrected cycle images | Barcode-called images (requires plugins) |
| `combinedanalysis.cppipe` | Final analysis | Painting + barcoding images | Segmentation masks, measurements |

### Load Data CSV Generation

CellProfiler requires `load_data.csv` files specifying image file paths, metadata, and image grouping.

#### CSV Formats by Pipeline Type

**illumcalc** - Illumination Calculation:

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,Metadata_Frame,FileName_DAPI,PathName_DAPI,...
P001,A01,1,0,P001_A01_1_0_DAPI.tif,/path/to/images,...
```

**illumapply** - Illumination Correction:

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,Metadata_Frame,FileName_OrigDAPI,PathName_OrigDAPI,FileName_IllumDAPI,PathName_IllumDAPI,...
P001,A01,1,0,P001_A01_1_0_DAPI.tif,/orig/,P001_IllumDAPI.npy,/illum/,...
```

**preprocess** - Barcoding with Cycles:

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,Metadata_Frame,Metadata_Cycle,FileName_Cycle1_Cy3,PathName_Cycle1_Cy3,...
P001,A01,1,0,1,P001_A01_1_0_Cycle1_Cy3.tif,/path/,...
```

**combined** - Painting + Barcoding:

```csv
Metadata_Plate,Metadata_Well,Metadata_Site,Metadata_Frame,FileName_CorrDAPI,PathName_CorrDAPI,FileName_Cycle1_Cy3,PathName_Cycle1_Cy3,...
P001,A01,1,0,P001_A01_1_CorrDAPI.tif,/painting/,P001_A01_1_0_Cycle1_Cy3.tif,/barcoding/,...
```

### CellProfiler Execution

CellProfiler runs in headless mode:

```bash
cellprofiler \
    -c \                    # Run without GUI
    -r \                    # Run pipeline
    -p pipeline.cppipe \    # Pipeline file
    -o output_dir/ \        # Output directory
    --data-file=load_data.csv  # Input CSV
```

For processes requiring plugins:

```bash
cellprofiler -c -r \
    -p combinedanalysis_patched.cppipe \
    -o . \
    --data-file=load_data.csv \
    --image-directory ./images/ \
    --plugins-directory=./plugins/
```

### Plugin Integration

CellProfiler plugins are downloaded from the CellProfiler-plugins repository:

- `callbarcodes.py` - Barcode calling
- `compensatecolors.py` - Color compensation

Default URLs are configured in `nextflow.config`:

```groovy
callbarcodes_plugin = "https://raw.githubusercontent.com/CellProfiler/CellProfiler-plugins/refs/heads/master/active_plugins/callbarcodes.py"
compensatecolors_plugin = "https://raw.githubusercontent.com/CellProfiler/CellProfiler-plugins/refs/heads/master/active_plugins/compensatecolors.py"
```

### Output File Naming

| Type | Pattern | Example |
|------|---------|---------|
| Corrected images | `{plate}_{well}_{site}_Corr{channel}.tif` | `Plate1_A01_1_CorrDNA.tif` |
| Illumination functions | `{plate}_Illum{channel}.npy` | `Plate1_IllumDNA.npy` |
| Preprocessed barcoding | `{plate}_{well}_{site}_Cycle{cycle}_{channel}.tif` | `Plate1_A01_1_Cycle01_A.tif` |
| Segmentation masks | `{plate}_{well}_{site}_Nuclei.tif` | `Plate1_A01_1_Nuclei.tif` |

---

## Python Scripts

Helper Python scripts in `bin/` handle data preparation and quality control.

### generate_load_data_csv.py

**Purpose**: Generate `load_data.csv` files required by CellProfiler processes.

**Usage**:

```bash
generate_load_data_csv.py \
    --pipeline_type <type> \
    --channels <channel_list> \
    --frames <frame_list> \
    --cycles <cycle_list> \
    --output load_data.csv
```

**Parameters**:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--pipeline_type` | Yes | `illumcalc`, `illumapply`, `segcheck`, `analysis`, `preprocess`, `combined` |
| `--channels` | Yes | Comma-separated channel names |
| `--frames` | No | Comma-separated frame indices |
| `--cycles` | No | Comma-separated cycle numbers (barcoding only) |
| `--output` | Yes | Output CSV file path |

**Metadata Flow**:

- **Pattern A (ILLUMCALC, ILLUMAPPLY)**: Metadata passed as CLI arguments from Nextflow `meta` map
- **Pattern B (PREPROCESS, COMBINEDANALYSIS)**: Metadata extracted from standardized filenames

**Filename Patterns**:

| Image Type | Pattern | Example |
|------------|---------|---------|
| Original | `Well{well}_Point{site}_{frame}_Channel{channels}_Seq*.ome.tiff` | `WellA1_PointA1_0000_ChannelDNA,GFP_Seq0000.ome.tiff` |
| Corrected | `Plate_{plate}_Well_{well}_Site_{site}_Corr{channel}.tiff` | `Plate_Plate1_Well_A1_Site_1_CorrDNA.tiff` |
| Illumination | `{plate}_Illum{channel}.npy` | `Plate1_IllumDNA.npy` |
| Cycle | `Plate_{plate}_Well_{well}_Site_{site}_Cycle{cycle}_{channel}.tiff` | `Plate_Plate1_Well_A1_Site_1_Cycle01_A.tiff` |

### qc_barcode_align.py

**Purpose**: Analyze barcode alignment quality across cycles.

**Functionality**:

1. Load cycle images from all cycles
2. Calculate pixel shifts (X/Y displacement between cycles)
3. Compute Pearson correlations between cycles
4. Generate visualizations (scatter plots, heatmaps, spatial maps)
5. Validate against `barcoding_shift_threshold` and `barcoding_corr_threshold`

**Output Files**:

- `shift_summary.csv`: Per-site shift statistics
- `correlation_matrix.csv`: Cycle-to-cycle correlations
- `shift_spatial_plot.png`: Spatial distribution of shifts
- `correlation_heatmap.png`: Correlation visualization
- `qc_report.html`: Interactive QC report

**QC Criteria**:

- Pass: Mean pixel shift < `barcoding_shift_threshold`, mean correlation > `barcoding_corr_threshold`
- Fail: Any site exceeds shift threshold or any cycle pair below correlation threshold

---

## Output Reference

### Directory Structure

```text
results/
├── images/
│   └── {batch}/
│       ├── illum/                          # Illumination functions
│       ├── images_corrected/               # Illumination-corrected images
│       ├── images_aligned/                 # Aligned barcoding images
│       ├── images_segmentation/            # Segmentation check outputs
│       ├── images_corrected_stitched/      # Stitched images (full resolution)
│       ├── images_corrected_cropped/       # Cropped images
│       └── images_corrected_stitched_10X/  # 10X downsampled stitched images
├── workspace/
│   ├── analysis/                           # Combined analysis outputs
│   ├── load_data_csv/                      # CellProfiler input files
│   └── qc_reports/                         # Quality control reports
│       ├── 1_illumination_painting/
│       ├── 3_segmentation/
│       ├── 4_stitching_painting/
│       ├── 5_illumination_barcoding/
│       ├── 6_alignment/
│       ├── 7_preprocessing/
│       └── 8_stitching_barcoding/
├── multiqc/                                # MultiQC summary reports
└── pipeline_info/                          # Nextflow execution reports
```

### Cell Painting Outputs

#### Illumination Functions

- **Location**: `results/images/{batch}/illum/{plate}/`
- **Files**: `{plate}_Illum{channel}.npy`
- **Description**: NumPy arrays containing illumination correction functions for each channel

#### Corrected Images

- **Location**: `results/images/{batch}/images_corrected/painting/{plate}/{plate}-{well}-{site}/`
- **Files**: `Plate_{plate}_Well_{well}_Site_{site}_Corr{channel}.tiff`
- **Description**: Multi-frame TIFF images with illumination correction applied

#### Stitched Images

- **Location**: `results/images/{batch}/images_corrected_stitched/painting/{plate}/{plate}-{well}/`
- **Files**: `*.tiff`, `TileConfiguration.txt`
- **Description**: Stitched full-resolution images for each well (requires `qc_painting_passed == true`)

### Barcoding Outputs

#### Aligned Images

- **Location**: `results/images/{batch}/images_aligned/barcoding/{plate}/{plate}-{well}/`
- **Files**: `*.tiff`
- **Description**: Illumination-corrected and aligned barcoding images

#### Preprocessed Images

- **Location**: `results/images/{batch}/images_corrected/barcoding/{plate}/{plate}-{well}-{site}/`
- **Files**: `Plate_{plate}_Well_{well}_Site_{site}_Cycle{cycle}_{channel}.tiff`
- **Description**: Barcode-called and color-compensated images

### Combined Analysis Outputs

**Location**: `results/workspace/analysis/{batch}/{plate}-{well}-{site}/`

#### Segmentation Masks

| File | Description |
|------|-------------|
| `{plate}_{well}_{site}_Nuclei.tiff` | Nuclear segmentation |
| `{plate}_{well}_{site}_Cells.tiff` | Whole cell segmentation |
| `{plate}_{well}_{site}_Cytoplasm.tiff` | Cytoplasm only (Cells - Nuclei) |

#### Feature Measurements (CSV)

| File | Description |
|------|-------------|
| `Image.csv` | Per-image measurements (counts, metadata) |
| `Nuclei.csv` | Per-nucleus measurements (location, intensity, texture) |
| `Cells.csv` | Per-cell measurements |
| `Cytoplasm.csv` | Per-cytoplasm measurements |
| `Experiment.csv` | Pipeline metadata |

**Key columns in Nuclei.csv / Cells.csv**:

| Column | Description |
|--------|-------------|
| `ObjectNumber` | Unique object ID within image |
| `ImageNumber` | Reference to Image.csv |
| `Metadata_Barcode` | Assigned barcode sequence |
| `Location_Center_X` | X coordinate of object center |
| `Location_Center_Y` | Y coordinate of object center |
| `AreaShape_Area` | Object area in pixels |
| `Intensity_MeanIntensity_*` | Mean intensity per channel |
| `Texture_*` | Texture features |
| `Granularity_*` | Granularity features |

### Quality Control Outputs

**Location**: `results/workspace/qc_reports/`

| Directory | Description |
|-----------|-------------|
| `1_illumination_painting/` | Painting illumination correction montages |
| `3_segmentation/` | Segmentation QC with overlays |
| `4_stitching_painting/` | Painting stitching QC |
| `5_illumination_barcoding/` | Barcoding illumination correction montages |
| `6_alignment/` | Barcode alignment reports (HTML, notebooks, PNG) |
| `7_preprocessing/` | Barcoding preprocessing QC |
| `8_stitching_barcoding/` | Barcoding stitching QC |

### Pipeline Information

**Location**: `results/pipeline_info/`

| File | Description |
|------|-------------|
| `execution_report_*.html` | Resource usage and task statistics |
| `execution_timeline_*.html` | Timeline visualization of task execution |
| `execution_trace_*.txt` | Detailed execution log with per-task metrics |
| `pipeline_dag_*.html` | Interactive DAG visualization |
| `params_*.json` | Parameters used for the run |
| `nf-pooled-cellpainting_software_mqc_versions.yml` | Software versions |

### MultiQC Reports

**Location**: `results/multiqc/`

- `multiqc_report.html`: Interactive HTML report aggregating all QC metrics
- `multiqc_data/`: Raw data and plot data
- `multiqc_plots/`: Exported plot files

---

!!! info "For Document Contributors"
    This section contains editorial guidelines for maintaining this document. These guidelines are intended for contributors and maintainers, not end users.

    **Purpose and Audience**

    This document provides technical reference material for developers and advanced users who need to:

    - Understand the pipeline's internal architecture
    - Modify or extend pipeline functionality
    - Debug issues in specific processes
    - Integrate with CellProfiler pipelines
    - Parse and use output files programmatically

    **Guiding Structure Principles**

    1. **Single comprehensive reference** - Consolidate all technical details here rather than fragmenting
    2. **Architecture before implementation** - Start with workflow design, then process details, then outputs
    3. **Code examples from actual source** - Use real Groovy/Python snippets from the codebase
    4. **Tables for structured data** - Use tables for process listings, file formats, and output schemas

    **Content Style Principles**

    5. **Groovy code blocks** - Use `groovy` language tag for Nextflow DSL code
    6. **File path conventions** - Show full paths relative to `results/` directory
    7. **Cross-reference source files** - Point to actual `.nf` and `.py` files where logic is implemented
    8. **Avoid duplication with guide.md** - Reference guide.md for user-facing explanations

    **Terminology Consistency**

    - **Process** - A Nextflow process (capitalized, e.g., CELLPROFILER_ILLUMCALC)
    - **Subworkflow** - A reusable workflow component (e.g., CELLPAINTING, BARCODING)
    - **Channel** - Nextflow data channel carrying `[meta, files]` tuples
    - **Grouping key** - The metadata fields used to group data for a process
    - **CellProfiler pipeline** - A `.cppipe` file (not to be confused with Nextflow pipeline)

    **Document Relationships**

    - **guide.md** - User-facing content; link there for installation and usage
    - **CLAUDE.md** - AI guidance; keep terminology aligned
    - **Source code** - This document should stay synchronized with actual implementation

    **Future Enhancements**

    Consider expanding with:

    - Detailed channel flow diagrams for each subworkflow
    - CellProfiler module-by-module documentation for each `.cppipe`
    - Performance tuning guidelines by process
    - Custom module development guide
