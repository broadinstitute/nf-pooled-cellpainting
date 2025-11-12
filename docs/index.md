# nf-pooled-cellpainting

A high-throughput Nextflow pipeline for optical pooled screening combining Cell Painting phenotypic analysis with sequencing-by-synthesis barcoding.

## Overview

This pipeline processes pooled cell screening data through two parallel processing arms:

- **Cell Painting Arm**: Phenotypic profiling using multi-channel fluorescence microscopy
- **Barcoding Arm**: Genetic identification using sequencing-by-synthesis (SBS)

The pipeline includes extensive quality control checkpoints, automated image stitching, and combined analysis for comprehensive screening results.

## Key Features

- **Dual-arm processing** for painting and barcoding data
- **Illumination correction** via CellProfiler
- **Quality control gates** at critical pipeline stages
- **Automated image stitching** with Fiji
- **Flexible parallelization** at plate, well, and site levels
- **CellProfiler plugin support** for barcode calling and color compensation
- **Seqera Platform ready** for cloud and HPC execution

## Quick Links

<div class="grid cards" markdown>

- :material-rocket-launch:{ .lg .middle } **Getting Started**

  ***

  Learn how to install and run your first analysis

  [:octicons-arrow-right-24: Quick Start](getting-started/quickstart.md)

- :material-cog:{ .lg .middle } **Parameters**

  ***

  Complete reference of all pipeline parameters

  [:octicons-arrow-right-24: Parameters](usage/parameters.md)

- :material-code-braces:{ .lg .middle } **Developer Guide**

  ***

  Understand the pipeline architecture and implementation

  [:octicons-arrow-right-24: Architecture](developer/architecture.md)

- :material-cloud:{ .lg .middle } **Seqera Platform**

  ***

  Run the pipeline on cloud and HPC infrastructure

  [:octicons-arrow-right-24: Seqera Platform](usage/seqera-platform.md)

</div>

## Citation

If you use this pipeline, please cite:

```
[Citation information to be added]
```

## Support

For questions and support:

- Open an issue on [GitHub](https://github.com/your-org/nf-pooled-cellpainting/issues)
- Contact the development team

## License

[License information to be added]
