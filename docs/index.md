# nf-pooled-cellpainting

A high-throughput Nextflow pipeline for optical pooled screening combining Cell Painting phenotypic analysis with sequencing-by-synthesis barcoding.

## Overview

This pipeline processes optical pooled screening (OPS) data through two parallel processing arms:

- **Cell Painting Arm**: Phenotypic profiling using multi-channel fluorescence microscopy
- **Barcoding Arm**: Genetic identification using sequencing-by-synthesis (SBS)

The pipeline includes extensive quality control checkpoints, automated image stitching, and combined analysis for comprehensive screening results.

## Repository Structure

```
nf-pooled-cellpainting/
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
```

## Key Features

- **Dual-arm processing** for painting and barcoding data
- **Illumination correction** via CellProfiler
- **Quality control gates** at critical pipeline stages
- **Automated image stitching** with Fiji
- **Flexible parallelization** at plate, well, and site levels
- **CellProfiler plugin support** for barcode calling and color compensation
- **Seqera Platform ready** for cloud and HPC execution

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

See [CITATIONS.md](https://github.com/seqera-services/nf-pooled-cellpainting/blob/dev/CITATIONS.md) for complete citations.

## Support

For questions and support:

- Open an issue on [GitHub](https://github.com/seqera-services/nf-pooled-cellpainting/issues)
- Review [Troubleshooting Guide](reference/troubleshooting.md)

## License

This pipeline uses code and infrastructure from the nf-core community, reused under the MIT license.
