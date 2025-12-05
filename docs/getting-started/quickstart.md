# Quick Start

This guide assumes you have [installed Nextflow and Docker](installation.md) or have the required setup on Seqera Platform. We'll walk you through running the pipeline using a minimal test dataset to verify your setup and demonstrate the two-phase workflow.

## 1. Run the Test Profile (Phase 1)

The pipeline includes a built-in `test` profile that automatically downloads a small dataset. This test dataset contains:

- A subset of images from one well (both Cell Painting and Barcoding arms)
- Pre-configured CellProfiler pipelines
- A sample barcodes file

The test is designed to run in about 15-20 minutes locally (or 5-10 minutes on AWS Batch) and demonstrates the complete workflow without requiring your own data.

Run the following command (or submit a launch via [Seqera Platform](https://cloud.seqera.io/))

```bash
nextflow run broadinstitute/nf-pooled-cellpainting \
    -profile test,docker \
    --outdir results
```

Once you launch the pipeline, it will:

1.  Download the test dataset (images, samplesheet, barcodes).
2.  Run **Illumination Calculation** and **Application**.
3.  Run **Segmentation** (Cell Painting) and **Barcode Calling** (Barcoding).
4.  Generate **QC Montages**.
5.  **STOP** before stitching.

This behavior follows the **"Stop-and-Check"** philosophy described in the [Overview](overview.md). By default, the pipeline pauses to allow you to inspect the quality of the images and segmentation before proceeding to the computationally expensive stitching step

## 2. Inspect QC Outputs

Navigate to the `results/workspace/qc_reports` directory (or check the Reports tab on Seqera Platform) to check the generated quality control images:

```
results/workspace/qc_reports/
├── 1_illumination_painting/
├── 3_segmentation/
├── 5_illumination_barcoding/
├── 6_alignment/
└── 7_preprocessing/
```

In a real run, you would examine these images to ensure:

- Illumination correction profiles look correct
- Segmentation outlines accurately identify nuclei and cells.
- Barcoding cycles are properly aligned.

## 3. Complete the Run (Phase 2)

Once you are satisfied with the QC results (for this test data, we assume they are good), you can "open the gates" (by switching the QC flags to `true`) and finish the analysis.

Resume the pipeline with the QC flags set to `true`:

```bash
nextflow run broadinstitute/nf-pooled-cellpainting \
    -profile test,docker \
    --outdir results \
    --qc_painting_passed true \
    --qc_barcoding_passed true \
    -resume
```

!!! important "The `-resume` flag"
    The `-resume` flag is critical here. It tells Nextflow to use the cached results from the previous run and only execute the _new_ steps (stitching, cropping, and combined analysis). Without it, the pipeline would start from scratch. If you are running on Seqera Platform, make sure you click on resume to use the cached results. Don't use relaunch, as this will restart the run from scratch.

### What happens now?

The pipeline continues from where it left off:

1.  **Stitches** the images into full well montages.
2.  **Crops** the stitched images (if configured).
3.  Performs **Combined Analysis** to map barcodes to cells.
4.  Generates the final csv result files.

## 4. Explore the Final Outputs

After the run completes, your `results/` directory will contain the full analysis:

```
results/
├── images/ # All output images
│   ├── Batch1/
│   │   ├── illum/ # Illumination correction profiles
│   │   ├── images_aligned/
│   │   ├── images_corrected/
│   │   ├── images_corrected_cropped/
│   │   ├── images_corrected_stitched/
│   │   ├── images_corrected_stitched_10X/
│   │   └── images_segmentation/
├── multiqc/
├── pipeline_info/
└── workspace/
    ├── analysis/
    │   └── Batch1/
    ├── load_data_csv/
    │   ├── barcoding-illumapply.load_data.csv
    │   ├── barcoding-illumcalc.load_data.csv
    │   ├── barcoding-preprocess.load_data.csv
    │   ├── combined_analysis.load_data.csv
    │   ├── painting-illumapply.load_data.csv
    │   ├── painting-illumcalc.load_data.csv
    │   └── painting-segcheck.load_data.csv
    └── qc_reports/
        ├── 1_illumination_painting/
        ├── 3_segmentation/
        ├── 4_stitching_painting/
        ├── 5_illumination_barcoding/
        ├── 6_alignment/
        ├── 7_preprocessing/
        └── 8_stitching_barcoding/
```

The most important files are in `results/workspace/analysis/`. These CSV files contain the linked phenotype (Cell Painting) and genotype (Barcoding) data for every cell.

## Next Steps

Now that you've successfully run the test profile, you're ready to process your own data.

- **[Use your own dataset](../usage/custom-data.md)**: Run the pipeline with your own dataset or a public dataset from the [Cell Painting Gallery](https://broadinstitute.github.io/cellpainting-gallery/overview.html).
- **[Parameters Guide](../usage/parameters.md)**: Learn how to configure the pipeline for your specific dataset.
- **[FAQ](../usage/faq.md)**: Common issues and solutions.
