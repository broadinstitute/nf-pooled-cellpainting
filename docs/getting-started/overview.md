# Overview

## What is Optical Pooled Screening?

Optical Pooled Screening (OPS) enables high-throughput functional genomics by combining genetic perturbations with image-based phenotyping at single-cell resolution. Unlike traditional arrayed screening approaches that test perturbations individually, OPS allows thousands of genetic variants to be assayed simultaneously within a single pooled population, with cellular identity decoded through in situ sequencing.

This pipeline integrates two complementary methodologies:

1. **Cell Painting** provides quantitative morphological profiling. Through multiplexed fluorescent labeling of cellular compartments (nucleus, endoplasmic reticulum, mitochondria, actin cytoskeleton, Golgi apparatus, and RNA), this approach generates high-dimensional feature vectors describing cellular morphology, organization, and intensity distributions. These features serve as phenotypic readouts of perturbation-induced cellular states.

2. **In-situ Sequencing (ISS)** enables spatial genotyping through cyclical imaging of fluorescently labeled nucleotides. Each genetic perturbation is tagged with a unique DNA barcode sequence. Sequential rounds of hybridization, imaging, and base calling reconstruct these barcodes directly within the microscopy field of view, establishing the genetic identity of individual cells.

The integration of these modalities yields matched genotype-phenotype data at single-cell resolution. By linking decoded barcodes to segmented cell morphologies, this approach facilitates large-scale perturbation screens where each cell's genetic modification and resulting phenotypic response are simultaneously captured and quantified.

## Pipeline Architecture

The pipeline is designed with two parallel processing "arms" that operate independently before converging for the final analysis.

### 1. Cell Painting Arm (Phenotype)

This arm processes the morphological images.

- **Illumination Correction**: Corrects for uneven lighting across the field of view, which is critical for accurate intensity measurements.
- **Segmentation**: Identifies individual cells and nuclei. This is the foundation of the analysis—if segmentation fails, downstream data is invalid.
- **QC Check**: Generates visual montages to verify that segmentation is performing correctly before proceeding.

### 2. Barcoding Arm (Genotype)

This arm processes the sequencing-by-synthesis (SBS) images.

- **Alignment**: Registers images from multiple sequencing cycles (rounds) to the first cycle to ensure perfect overlap.
- **Base Calling**: Reads the sequence of fluorescent bases (A, C, G, T) at each pixel to decode the barcode.
- **QC Check**: Verifies that barcodes are being called with high confidence and aligning to the known library.

### 3. Convergence (Single-Cell Mapping)

Once both arms pass quality control, they are stitched and merged. The pipeline maps the decoded barcodes from the Barcoding Arm to the segmented cells from the Cell Painting Arm, creating a unified dataset where every cell has both a phenotype and an assigned genetic perturbation.

## Data Hierarchy

Understanding how the pipeline organizes data is key to preparing your inputs correctly.

- **Batch**: A collection of plates processed together.
- **Plate**: A physical multi-well plate (e.g., 96 or 384 wells).
- **Well**: A single experimental unit within a plate.
- **Site**: A specific field of view within a well.
- **Cycle** (Barcoding only): Represents a round of sequencing. Cycle 1 is usually the reference for alignment.

![Data Hierarchy Visualization](../assets/images/data_hierarchy.png)

## The "Stop-and-Check" Philosophy

Processing terabytes of high-content imaging data is computationally expensive. To avoid wasting resources on poor-quality data, the pipeline implements a **"Stop-and-Check"** workflow. This stop and check behaviour is controlled by two pipeline parameters (`--qc_painting_passed` and `--qc_barcoding_passed`), which are both false by default, causing the pipeline to stop before stitch and cropping via Fiji.

1.  **Phase 1: Raw data processing:**
    The pipeline runs illumination correction, segmentation (for painting arm) and image alignment across cycles (for barcoding arm) and generates QC images and metrics. It then **stops** processing for the user to manually verify

2.  **Phase 2: Manual Review:**
    You review the QC outputs in the `results/qc` folder (or in the Reports tab if running via Seqera Platform).

3.  **Phase 3: Production Run:**
    If the data looks good, you "open the gates" by setting the parameters `--qc_painting_passed` and `--qc_barcoding_passed` to `true` and resuming the pipeline. It will pick up exactly where it left off and proceed to the heavy lifting: stitching, feature extraction, and CSV generation. If you only turn one of the parameters to true, that arm (painting or barcoding) will continue with stitching and cropping but then stop because the final combined analysis step needs the outputs from both painting and barcoding.
