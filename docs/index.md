# nf-pooled-cellpainting

nf-pooled-cellpainting is a Nextflow pipeline for the processing and analysis of optical pooled screening (OPS) data combining Cell Painting phenotypic analysis with sequencing-by-synthesis barcoding.

## Introduction

The pipeline builds upon previous work by the Broad Institute and the [Cimini lab](https://cimini-lab.broadinstitute.org/) establishing large scale image analysis for cell painting assays.
nf-pooled-cellpainting processes optical pooled screening (OPS) data through two parallel processing arms:

- **Cell Painting Arm**: Phenotypic profiling using multi-channel fluorescence microscopy
- **Barcoding Arm**: Genetic barcoding using sequencing-by-synthesis (SBS)

The pipeline takes images of cells stained with cell painting markers and images of sequencing-by-synthesis (SBS) barcoding images as input and processes them through a number of image analysis and processing steps using Cellprofiler, Fiji and custom python scripts. A detailed workflow description can be found in the [Workflow](developer/architecture.md) section. A high level overview of the different steps in the pipeline is shown in the Mermaid diagram below.

```mermaid
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
        BC_IllumApply[IllumApply]
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

    %% Input connections
    Samplesheet --> CP_IllumCalc
    Samplesheet --> BC_IllumCalc

    %% Cell Painting Flow
    CP_IllumCalc --> CP_IllumQC
    CP_IllumCalc --> CP_IllumApply
    CP_IllumApply --> CP_SegCheck
    CP_SegCheck --> CP_SegCheckQC
    CP_SegCheckQC -.-> CP_StitchCrop
    CP_IllumApply --> CP_StitchCrop
    CP_StitchCrop --> CP_StitchQC

    %% Barcoding Flow
    BC_IllumCalc --> BC_IllumQC
    BC_IllumCalc --> BC_IllumApply
    BC_IllumApply --> BC_AlignQC
    BC_IllumApply --> BC_Preprocess
    BC_Preprocess --> BC_PreprocessQC
    BC_PreprocessQC -.-> BC_StitchCrop
    BC_Preprocess --> BC_StitchCrop
    BC_StitchCrop --> BC_StitchQC

    %% Combined Flow
    CP_StitchCrop --> CombinedAnalysis
    BC_StitchCrop --> CombinedAnalysis
    CombinedAnalysis --> MultiQC
```

## Key Features

- **Dual-arm, parallel processing** for painting and barcoding data
- **Illumination correction** via CellProfiler
- **Automated image stitching** with Fiji
- **Possibility for parallelization** at plate, well, and site levels
- **Quality control gates** at critical pipeline stages
- **Resumability** after manual QC and failed pipeline runs
- **CellProfiler plugin support** for barcode calling and color compensation
- **Easily portable across** cloud and HPC executions

### Repository overview

!!! quote "Repository Structure"
`     nf-pooled-cellpainting/
    ├── main.nf                    # Entry point
    ├── nextflow.config            # Main configuration
    ├── workflows/                 # Main workflow logic
    │   └── nf-pooled-cellpainting.nf
    ├── subworkflows/local/        # Pipeline subworkflows
    │   ├── cellpainting/          # Cell painting processing arm
    │   ├── barcoding/             # Barcoding processing arm
    │   └── utils*/                # Utility subworkflows
    ├── modules/local/             # Local process modules
    │   ├── cellprofiler/          # CellProfiler processes
    │   │   ├── illumcalc/         # Illumination calculation
    │   │   ├── illumapply/        # Illumination application
    │   │   ├── preprocess/        # Barcode preprocessing
    │   │   ├── segcheck/          # Segmentation QC
    │   │   └── combinedanalysis/  # Combined analysis
    │   ├── fiji/                  # Fiji image processing
    │   │   └── stitchcrop/        # Image stitching & cropping
    │   └── qc/                    # QC modules
    ├── bin/                       # Python scripts & tools
    ├── conf/                      # Configuration files
    ├── assets/                    # CellProfiler pipelines & resources
    ├── docs/                      # Documentation source
    └── tests/                     # nf-test test cases
    `

## Quick Links

- [Getting Started](getting-started/quickstart.md) - Install and run your first analysis
- [Parameters](usage/parameters.md) - Complete parameter reference
- [Architecture](developer/architecture.md) - Pipeline architecture and implementation
- [Seqera Platform](usage/seqera-platform.md) - Run on cloud and HPC infrastructure

## Citation

If you use this pipeline, please cite the original authors and tools:

**Pipeline Authors**: Florian Wuennemann, Erin Weisbart, Shantanu Singh, Ken Brewer

**Key Tools**:

- CellProfiler (Carpenter et al., 2006)
- Fiji/ImageJ (Schindelin et al., 2012)
- Nextflow (Di Tommaso et al., 2017)

See [CITATIONS.md](https://github.com/seqera-services/nf-pooled-cellpainting/blob/dev/CITATIONS.md) for a list of complete citations.

## Support

For questions and support:

- Open an issue on [GitHub](https://github.com/seqera-services/nf-pooled-cellpainting/issues)
- Review [Troubleshooting Guide](reference/troubleshooting.md)

## License

This pipeline is licensed under the [BSD 3-Clause License](LICENSE).

Portions of this software are derived from the nf-core project template and nf-core tools, which are licensed under the [MIT License](LICENSE-MIT). This includes the pipeline template structure, module patterns, configuration patterns, and utility functions.
