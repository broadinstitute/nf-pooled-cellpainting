# nf-pooled-cellpainting

[![Nextflow](https://img.shields.io/badge/nextflow%20DSL2-%E2%89%A525.04.8-23aa62.svg)](https://www.nextflow.io/)
[![run with docker](https://img.shields.io/badge/run%20with-docker-0db7ed?labelColor=000000&logo=docker)](https://www.docker.com/)
[![run with singularity](https://img.shields.io/badge/run%20with-singularity-1d355c.svg?labelColor=000000)](https://sylabs.io/docs/)

## Introduction

**nf-pooled-cellpainting** is a Nextflow pipeline for processing optical pooled screening (OPS) data, combining Cell Painting phenotypic analysis with sequencing-by-synthesis barcoding.

> [!WARNING]
> This pipeline is under active development by Seqera and the Broad Institute's Imaging Platform.

## Pipeline Overview

The pipeline processes data through two parallel arms:

- **Cell Painting**: Multi-channel fluorescence microscopy for phenotypic profiling
- **Barcoding**: Sequencing-by-synthesis for cell identification by genetic barcoding

Key steps include:

1. Illumination correction (CellProfiler)
2. Quality control checkpoints
3. Image stitching and cropping (Fiji)
4. Segmentation and feature extraction
5. Barcode calling and assignment
6. Final version and QC report with MultiQC

## Quick Start

```bash
nextflow run seqera-services/nf-pooled-cellpainting \
   -profile docker \
   --input samplesheet.csv \
   --barcodes barcodes.csv \
   --painting_illumcalc_cppipe painting_illumcalc.cppipe \
   --painting_illumapply_cppipe painting_illumapply.cppipe \
   --painting_segcheck_cppipe painting_segcheck.cppipe \
   --barcoding_illumcalc_cppipe barcoding_illumcalc.cppipe \
   --barcoding_illumapply_cppipe barcoding_illumapply.cppipe \
   --barcoding_preprocess_cppipe barcoding_preprocess.cppipe \
   --combinedanalysis_cppipe combinedanalysis.cppipe \
   --outdir results
```

Run the pipeline with small test data:

```bash
nextflow run seqera-services/nf-pooled-cellpainting -profile test,docker --outdir results
```

## Documentation

For detailed documentation, see: **[Full Documentation](https://your-org.github.io/nf-pooled-cellpainting/)**

- [Installation](https://your-org.github.io/nf-pooled-cellpainting/getting-started/installation/)
- [Usage Guide](https://your-org.github.io/nf-pooled-cellpainting/usage/parameters/)
- [Pipeline Architecture](https://your-org.github.io/nf-pooled-cellpainting/developer/architecture/)
- [Troubleshooting](https://your-org.github.io/nf-pooled-cellpainting/reference/troubleshooting/)

## Pipeline Parameters

Key parameters:

| Parameter                   | Description                                 | Required |
| --------------------------- | ------------------------------------------- | -------- |
| `--input`                   | Samplesheet CSV with image paths            | Yes      |
| `--barcodes`                | Barcode reference CSV                       | Yes      |
| `--painting_*_cppipe`       | CellProfiler pipelines for painting arm     | Yes      |
| `--barcoding_*_cppipe`      | CellProfiler pipelines for barcoding arm    | Yes      |
| `--combinedanalysis_cppipe` | Combined analysis pipeline                  | Yes      |
| `--outdir`                  | Output directory                            | Yes      |
| `--qc_painting_passed`      | Enable painting stitching (default: false)  | No       |
| `--qc_barcoding_passed`     | Enable barcoding stitching (default: false) | No       |

See [Parameters Documentation](https://your-org.github.io/nf-pooled-cellpainting/usage/parameters/) for complete list.

## Credits

nf-pooled-cellpainting was originally written by [Florian Wuennemann](https://github.com/FloWuenne) (Seqera), [Ken Brewer](https://github.com/kenibrewer) (Seqera), [Erin Weissbart](https://github.com/ErinWeisbart) (Broad Institute), [Shantanu Singh](https://github.com/shntnu) (Broad Institute).

## Contributions and Support

If you would like to contribute to this pipeline, please see the [contributing guidelines](.github/CONTRIBUTING.md).

## Citations

An extensive list of references for the tools used by the pipeline can be found in the [`CITATIONS.md`](CITATIONS.md) file.

This pipeline uses code and infrastructure developed and maintained by the [nf-core](https://nf-co.re) community, reused here under the [MIT license](https://github.com/nf-core/tools/blob/main/LICENSE).

> **The nf-core framework for community-curated bioinformatics pipelines.**
>
> Philip Ewels, Alexander Peltzer, Sven Fillinger, Harshil Patel, Johannes Alneberg, Andreas Wilm, Maxime Ulysse Garcia, Paolo Di Tommaso & Sven Nahnsen.
>
> _Nat Biotechnol._ 2020 Feb 13. doi: [10.1038/s41587-020-0439-x](https://dx.doi.org/10.1038/s41587-020-0439-x).
