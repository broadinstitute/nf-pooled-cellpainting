# Overview

## What is Pooled Cell Painting?

Optical Pooled Screening (OPS) enables high-throughput functional genomics by combining genetic perturbations with image-based phenotyping at single-cell resolution. Unlike traditional arrayed screening approaches that test perturbations individually, OPS allows thousands of genetic variants to be assayed simultaneously within a single pooled population, with cellular identity decoded through in situ sequencing.

This pipeline integrates two complementary methodologies that together yields matched genotype-phenotype data at single-cell resolution.

### Cell Painting (phenotyping)

Cell Painting is a specific morphological profiling assay (or image-based phenotyping assay) that produces single-cell, quantitative phenotypic measurements. Through multiplexed fluorescent labeling of cellular compartments (canonically DNA, endoplasmic reticulum, mitochondria, actin, Golgi apparatus, nucleoli, plasma membrane, and cytoplasmic RNA), this approach generates high-dimensional feature vectors describing cellular morphology, organization, and intensity distributions.

### In Situ Sequencing (genotyping)

In-situ Sequencing (ISS) enables spatial genotyping by decoding DNA barcodes directly within the microscopy field of view. In optical pooled screens, this is typically achieved using sequencing-by-synthesis (SBS) chemistry: each genetic perturbation is tagged with a unique barcode, and sequential rounds of fluorescent nucleotide incorporation, imaging, and base calling reconstruct the barcode sequence while preserving spatial information. This arm can be referred to as "barcoding", "ISS", or "SBS".

## What is nf-pooled-cellpainting?

nf-pooled-cellpainting is a [Nextflow](https://www.nextflow.io) pipeline that coordinates the Pooled Cell Painting workflow.

## Citation

If you use this pipeline, please cite the original authors and tools:

**Pipeline Authors**: Florian Wuennemann, Erin Weisbart, Shantanu Singh, Ken Brewer

**Key Tools**:

- CellProfiler (Stirling et al., 2021)
- Fiji/ImageJ (Schindelin et al., 2012)
- Nextflow (Di Tommaso et al., 2017)
- Ashlar (Muhlich et al., 2022)

See [CITATIONS.md](https://github.com/broadinstitute/nf-pooled-cellpainting/blob/dev/CITATIONS.md) for complete citations.

## Support

- Open an issue on [GitHub](https://github.com/broadinstitute/nf-pooled-cellpainting/issues)
- Review the [FAQ](faq.md)
- Review [troubleshooting](troubleshooting.md)
