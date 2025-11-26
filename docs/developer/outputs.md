# Output Reference

Complete reference for pipeline outputs and their organization.

## Cell Painting Outputs

### Illumination Functions

**Location**: `results/images/{batch}}/`

**Files**:

```
{batch}/
  {plate}/
    {plate}_Illum{channel}.npy
```

**Description**: NumPy arrays containing illumination correction functions for each channel. Used to correct uneven illumination across the field of view.

**Example**:

```
results/painting/illum/batch1/P001/
  P001_IllumDAPI.npy
  P001_IllumGFP.npy
  P001_IllumRFP.npy
```

### Corrected Images

**Location**: `results/painting/corrected/`

**Files**:

```
{batch}/
  {plate}/
    {well}/
      {plate}_{well}_{site}_Corr{channel}.tif
```

**Description**: Multi-frame TIFF images with illumination correction applied. One file per channel per site.

**Example**:

```
results/painting/corrected/batch1/P001/A01/
  P001_A01_1_CorrDAPI.tif
  P001_A01_1_CorrGFP.tif
  P001_A01_1_CorrRFP.tif
```

### Stitched and Cropped Images

**Location**: `results/painting/stitched_cropped/`

**Files**:

```
{batch}/
  {plate}/
    {well}/
      {site}/
        {plate}_{well}_{site}_Stitched{channel}.tif
```

**Description**: Stitched full-resolution images for each site, cropped to remove overlap regions. Generated only if `qc_painting_passed == true`.

## Barcoding Outputs

### Illumination Functions

**Location**: `results/barcoding/illum/`

**Files**:

```
{batch}/
  {plate}/
    {cycle}/
      {plate}_Cycle{cycle}_Illum{channel}.npy
```

**Description**: Cycle-specific illumination correction functions.

**Example**:

```
results/barcoding/illum/batch1/P001/1/
  P001_Cycle1_IllumCy3.npy
  P001_Cycle1_IllumCy5.npy
```

### Corrected Images

**Location**: `results/barcoding/corrected/`

**Files**:

```
{batch}/
  {plate}/
    {well}/
      {site}/
        {cycle}/
          {plate}_{well}_{site}_{frame}_Cycle{cycle}_{channel}.tif
```

**Description**: Illumination-corrected barcoding images, organized by cycle.

### Preprocessed Images

**Location**: `results/barcoding/preprocessed/`

**Files**:

```
{batch}/
  {plate}/
    {well}/
      {site}/
        {plate}_{well}_{site}_{frame}_Cycle{cycle}_{channel}.tif
```

**Description**: Barcode-called and color-compensated images. Ready for stitching and combined analysis.

### Stitched and Cropped Images

**Location**: `results/barcoding/stitched_cropped/`

**Files**: Similar structure to painting, with cycle information preserved.

**Description**: Stitched preprocessed images. Generated only if `qc_barcoding_passed == true`.

## Combined Analysis Outputs

### Segmentation Masks

**Location**: `results/combined/analysis/{batch}/{plate}/{well}/{site}/`

**Files**:

```
{plate}_{well}_{site}_Nuclei.tif
{plate}_{well}_{site}_Cells.tif
{plate}_{well}_{site}_Cytoplasm.tif
```

**Description**: Binary masks for segmented objects:

- **Nuclei**: Nuclear segmentation
- **Cells**: Whole cell segmentation
- **Cytoplasm**: Cytoplasm only (Cells - Nuclei)

### Overlay Images

**Files**:

```
{plate}_{well}_{site}_Overlay.tif
```

**Description**: RGB composite images showing segmentation overlays on original images.

### Feature Measurements

**Files**:

```
Image.csv
Nuclei.csv
Cells.csv
Cytoplasm.csv
Experiment.csv
```

**Description**: CSV files containing extracted features and measurements.

#### Image.csv

Per-image measurements:

| Column           | Description               |
| ---------------- | ------------------------- |
| `ImageNumber`    | Unique image identifier   |
| `Metadata_Plate` | Plate identifier          |
| `Metadata_Well`  | Well position             |
| `Metadata_Site`  | Site number               |
| `Count_Nuclei`   | Number of nuclei detected |
| `Count_Cells`    | Number of cells detected  |

#### Nuclei.csv / Cells.csv

Per-object measurements:

| Column                      | Description                   |
| --------------------------- | ----------------------------- |
| `ObjectNumber`              | Unique object ID within image |
| `ImageNumber`               | Reference to Image.csv        |
| `Metadata_Barcode`          | Assigned barcode sequence     |
| `Location_Center_X`         | X coordinate of object center |
| `Location_Center_Y`         | Y coordinate of object center |
| `AreaShape_Area`            | Object area in pixels         |
| `Intensity_MeanIntensity_*` | Mean intensity per channel    |
| `Texture_*`                 | Texture features              |
| `Granularity_*`             | Granularity features          |

#### Experiment.csv

Pipeline metadata and run parameters.

## Quality Control Outputs

### Illumination Montages

**Location**: `results/qc/montage_illum/`

**Files**:

```
{arm}/{batch}/{plate}/
  {plate}_IllumMontage_{channel}.png
```

**Description**: Visual summary of illumination correction functions. Shows original vs. corrected illumination patterns.

### Segmentation Check Montages

**Location**: `results/qc/montage_segcheck/`

**Files**:

```
{batch}/{plate}/{well}/
  {plate}_{well}_SegCheckMontage.png
```

**Description**: Visual QC for segmentation quality. Shows sample sites with segmentation overlays.

### Preprocessing Montages

**Location**: `results/qc/montage_preprocess/`

**Files**:

```
{batch}/{plate}/{well}/{site}/
  {plate}_{well}_{site}_PreprocessMontage.png
```

**Description**: Visual QC for barcoding preprocessing. Shows barcode calling results across cycles.

### Stitch/Crop Montages

**Location**: `results/qc/montage_stitchcrop/`

**Files**: Montages showing stitching quality and overlap regions.

### Barcode Alignment QC

**Location**: `results/qc/barcode_align/`

**Files**:

```
{batch}/{plate}/
  shift_summary.csv
  correlation_matrix.csv
  shift_spatial_plot.png
  correlation_heatmap.png
  qc_report.html
```

**Description**:

- **shift_summary.csv**: Per-site pixel shift statistics
- **correlation_matrix.csv**: Cycle-to-cycle correlation coefficients
- **Plots**: Visual summaries of alignment quality
- **qc_report.html**: Interactive QC dashboard

#### shift_summary.csv

| Column         | Description             |
| -------------- | ----------------------- |
| `Plate`        | Plate identifier        |
| `Well`         | Well position           |
| `Site`         | Site number             |
| `Mean_Shift_X` | Mean X-axis pixel shift |
| `Mean_Shift_Y` | Mean Y-axis pixel shift |
| `Max_Shift`    | Maximum shift magnitude |
| `Pass`         | Boolean QC pass/fail    |

## Load Data CSV Archive

**Location**: `results/csvs/load_data/`

**Files**: All generated `load_data.csv` files used by CellProfiler processes.

**Description**: Archived for reproducibility and debugging. Organized by process and metadata.

## Pipeline Information

**Location**: `results/pipeline_info/`

**Files**:

- `execution_report.html`: Resource usage and task statistics
- `execution_timeline.html`: Timeline visualization
- `execution_trace.txt`: Detailed execution log

**Usage**:

```bash
nextflow run main.nf -with-report results/pipeline_info/execution_report.html
```
