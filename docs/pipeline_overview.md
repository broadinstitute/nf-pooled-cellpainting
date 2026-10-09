# Pipeline Overview

## Pipeline Architecture

The pipeline processes data through two parallel arms (the Cell Painting arm and the ISS arm) that operate independently on separate stacks of images before converging for final analysis. A mermaid diagram follows:

```{mermaid}
flowchart TD
    subgraph Input
        Samplesheet[Samplesheet]
    end

    subgraph "Cell Painting Arm"
        CP_IllumCalc[IllumCalc]
        CP_IllumQC[Illum QC]
        CP_IllumApply[IllumApply]
        CP_SegCheck[SegCheck]
        CP_SegCheckQC[SegCheck QC]
        CP_StitchCrop[Stitch & Crop]
        CP_StitchQC[Stitch QC]
    end

    subgraph "Barcoding Arm"
        BC_IllumCalc[IllumCalc]
        BC_IllumQC[Illum QC]
        BC_IllumApply[IllumApply & Align]
        BC_AlignQC[Align QC]
        BC_Preprocess[Preprocess]
        BC_PreprocessQC[Preprocess QC]
        BC_StitchCrop[Stitch & Crop]
        BC_StitchQC[Stitch QC]
    end

    subgraph "Combined Analysis"
        CombinedAnalysis[Combined Analysis]
        MultiQC[MultiQC]
    end

    Samplesheet --> CP_IllumCalc
    Samplesheet --> BC_IllumCalc

    CP_IllumCalc --> CP_IllumQC
    CP_IllumCalc --> CP_IllumApply
    CP_IllumApply --> CP_SegCheck
    CP_SegCheck --> CP_SegCheckQC
    CP_SegCheckQC -.-> CP_StitchCrop
    CP_IllumApply --> CP_StitchCrop
    CP_StitchCrop --> CP_StitchQC

    BC_IllumCalc --> BC_IllumQC
    BC_IllumCalc --> BC_IllumApply
    BC_IllumApply --> BC_AlignQC
    BC_IllumApply --> BC_Preprocess
    BC_Preprocess --> BC_PreprocessQC
    BC_PreprocessQC -.-> BC_StitchCrop
    BC_Preprocess --> BC_StitchCrop
    BC_StitchCrop --> BC_StitchQC

    CP_StitchCrop --> CombinedAnalysis
    BC_StitchCrop --> CombinedAnalysis
    CombinedAnalysis --> MultiQC
```

### Cell Painting Arm (Phenotype)

- **Illumination Correction**: Calculates a flat-field illumination correction to correct for uneven illumination.
- **Illumination Application**: Applies the flat-field illumination correction created in the previous step.
- **Segmentation Check**: Verifies cell/nuclei segmentation quality on a subset of images
- **Stitch & Crop**: Stitches fields of view into whole-well images and crops into tiles

### Barcoding Arm (Genotype)

- **Illumination Correction**: Calculates a flat-field illumination correction to correct for uneven illumination.
- **Illumination Application**: Applies the flat-field illumination correction created in the previous step. Also performs inter-cycle alignment to align all subsequent barcoding cycles to cycle 1.
- **Preprocessing**: Compensates for spectral bleed-through, identifies barcode foci, and generates QC metrics
- **Stitch & Crop**: Stitches and crops to match Cell Painting tiles

### Combined Analysis

Once both arms pass quality control, the final **Analysis** pipeline aligns Cell Painting and barcoding images, segments cells from the phenotypic stains, measures morphological features, reads an SBS barcodes for each SBS focus and selects a best match from the barcode library, and assigns barcode foci to cells — linking each cell's genotype to its phenotype.

## The "Stop-and-Check" Workflow

Making morphological measurements in high-content imaging data is computationally expensive. To avoid wasting resources on poor-quality data, the pipeline implements a **"Stop-and-Check"** workflow controlled by two parameters:

- `--qc_painting_passed` (default: `false`)
- `--qc_barcoding_passed` (default: `false`)

**Phase 1 - Initial Processing**: The pipeline runs through the QC checkpoints for both arms (SegCheck QC for painting, Preprocess QC for barcoding), generates QC montages, and **stops before Stitch & Crop**.

**Phase 2 - Manual Review**: You review QC outputs in `results/workspace/qc_reports/`.

**Phase 3 - Production Run**: If data looks good, set `--qc_painting_passed true` and `--qc_barcoding_passed true`, then resume with `-resume`. The pipeline continues from cached results.

## Data Hierarchy

Understanding how the pipeline organizes data:

| Level | Description | Example |
|-------|-------------|---------|
| **Batch** | Collection of plates processed together. Assumed to share some amount of technical artifacts. | `Batch1` |
| **Plate** | Physical multi-well plate. Typically a smaller number of larger wells than for an arrayed experiment. | `Plate1` |
| **Well** | Single experimental unit. All cells within a well share a common pool of genetic perturbations and may share a common secondary perturbation (such as an additional drug treatment). | `A01` |
| **Site** | Field of view within a well | `1`, `2`, `3`... |
| **Cycle** | Sequencing round for barcoding. Also supports multi-round phenotype acquisition | `1`, `2`, `3`... |
