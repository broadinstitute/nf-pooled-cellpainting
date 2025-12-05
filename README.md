# nf-pooled-cellpainting

[![Nextflow](https://img.shields.io/badge/nextflow%20DSL2-%E2%89%A525.04.8-23aa62.svg)](https://www.nextflow.io/)
[![run with docker](https://img.shields.io/badge/run%20with-docker-0db7ed?labelColor=000000&logo=docker)](https://www.docker.com/)

## Introduction

**nf-pooled-cellpainting** is a Nextflow pipeline for processing optical pooled screening (OPS) data, combining Cell Painting phenotypic analysis with sequencing-by-synthesis barcoding. The output of the pipeline is a collection of phenotypic measurements for each identified cell in the dataset.

## Pipeline Overview

The pipeline processes data through two parallel arms:

- **Cell Painting**: Multi-channel fluorescence microscopy for phenotypic profiling
- **Barcoding**: Sequencing-by-synthesis for cell identification by genetic barcoding

Key steps include:

1. Illumination correction (CellProfiler)
2. Quality control checkpoints (segmentation evaluation, barcode calling and cycle alignment)
3. Image stitching and cropping (Fiji)
4. Segmentation and feature extraction
5. Barcode calling and assignment
6. Final reporting and QC with MultiQC

## Quick Start

The pipeline includes a small test dataset to verify that the pipeline executes correctly from end to end. You can run the test profile using the following command:

```bash
nextflow run broadinstitute/nf-pooled-cellpainting -profile test,docker --outdir results
```

### Using your own data

To use your own or public optical pooled screening data, you need to supply a samplesheet, a `barcode.csv` file, your own generated CellProfiler pipeline files (`.cppipe` files) for all pipeline steps, and an output directory for the results.

```bash
nextflow run broadinstitute/nf-pooled-cellpainting \
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

Instead of defining parameters on the command line, you can also define them via a Nextflow config file or as json or yaml params files (see [Nextflow documentation](https://nextflow.io/docs/latest/cli.html)).

## Documentation

For detailed documentation, see: **[Full Documentation](https://broadinstitute.github.io/nf-pooled-cellpainting/)**

- [Installation](https://broadinstitute.github.io/nf-pooled-cellpainting/getting-started/installation/)
- [Usage Guide](https://broadinstitute.github.io/nf-pooled-cellpainting/usage/parameters/)
- [Troubleshooting](https://broadinstitute.github.io/nf-pooled-cellpainting/reference/troubleshooting/)

## Important pipeline Parameters

The pipeline contains several parameters that are necessary for correct execution of the pipeline and to determine whether the pipeline will pause for manual quality control.

| Parameter                   | Description                                        | Required |
| :-------------------------- | :------------------------------------------------- | :------- |
| `--input`                   | Samplesheet CSV with image paths and metadata      | Yes      |
| `--outdir`                  | Output directory                                   | Yes      |
| `--barcodes`                | Barcode reference CSV                              | Yes      |
| `--painting_*_cppipe`       | CellProfiler pipelines for the painting arm        | Yes      |
| `--barcoding_*_cppipe`      | CellProfiler pipelines for the barcoding arm       | Yes      |
| `--combinedanalysis_cppipe` | Combined analysis pipeline                         | Yes      |
| `--qc_painting_passed`      | QC status for the painting arm (default: `false`)  | No       |
| `--qc_barcoding_passed`     | QC status for the barcoding arm (default: `false`) | No       |

<!-- See [Parameters Documentation](https://your-org.github.io/nf-pooled-cellpainting/usage/parameters/) for complete list. -->

## Credits

nf-pooled-cellpainting was originally written by [Florian Wuennemann](https://github.com/FloWuenne) (Seqera), [Ken Brewer](https://github.com/kenibrewer) (Seqera), [Erin Weissbart](https://github.com/ErinWeisbart) (Broad Institute), and [Shantanu Singh](https://github.com/shntnu) (Broad Institute).

## Contributions and Support

If you would like to contribute to this pipeline, please see the [contributing guidelines](.github/CONTRIBUTING.md).

## License

This pipeline is licensed under the [BSD 3-Clause License](LICENSE).

Portions of this software are derived from the nf-core project template and nf-core tools, which are licensed under the [MIT License](LICENSE-MIT). This includes the pipeline template structure, module patterns, configuration patterns, and utility functions.

## Citations

An extensive list of references for the tools used by the pipeline can be found in the [`CITATIONS.md`](CITATIONS.md) file.

This pipeline uses code and infrastructure developed and maintained by the [nf-core](https://nf-co.re) community, reused here under the [MIT license](https://github.com/nf-core/tools/blob/main/LICENSE).

> **The nf-core framework for community-curated bioinformatics pipelines.**
>
> Philip Ewels, Alexander Peltzer, Sven Fillinger, Harshil Patel, Johannes Alneberg, Andreas Wilm, Maxime Ulysse Garcia, Paolo Di Tommaso & Sven Nahnsen.
>
> _Nat Biotechnol._ 2020 Feb 13. doi: [10.1038/s41587-020-0439-x](https://dx.doi.org/10.1038/s41587-020-0439-x).
