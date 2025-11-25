# Parameters

This page describes the parameters available in the pipeline.

## Input/output options

Define where the pipeline should find input data and save output data.

| Parameter                  | Description                                                                                                                                                                                                                                                                                                                                                                      | Type    | Default                                                          | Required |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | ---------------------------------------------------------------- | -------- |
| `--input`                  | Path to comma-separated file containing information about the samples in the experiment.<br><details><summary>Help</summary>You will need to create a design file with information about the samples in your experiment before running the pipeline. Use this parameter to specify its location. It has to be a comma-separated file with 3 columns, and a header row.</details> | string  |                                                                  | ✅       |
| `--outdir`                 | The output directory where the results will be saved. You have to use absolute paths to storage on Cloud infrastructure.                                                                                                                                                                                                                                                         | string  |                                                                  | ✅       |
| `--qc_painting_passed`     | Flag to check whether quality control for the painting arm has been performed                                                                                                                                                                                                                                                                                                    | boolean |                                                                  |          |
| `--qc_barcoding_passed`    | Flag to check whether quality control for the barcoding arm has been performed                                                                                                                                                                                                                                                                                                   | boolean |                                                                  |          |
| `--barcodes`               | Path to barcodes.csv file for SBS data.                                                                                                                                                                                                                                                                                                                                          | string  |                                                                  | ✅       |
| `--fiji_stitchcrop_script` | Path to script to use for FIJI Stitchcrop.                                                                                                                                                                                                                                                                                                                                       | string  | `/home/florian/nf-pooled-cellpainting/bin/stitch_crop.master.py` | ✅       |
| `--range_skip`             | Step number for subsampling images for segcheck.                                                                                                                                                                                                                                                                                                                                 | integer | `2`                                                              |          |
| `--multiqc_title`          | MultiQC report title. Printed as page header, used for filename if not otherwise specified.                                                                                                                                                                                                                                                                                      | string  |                                                                  |          |

## Cellprofiler Pipelines

Paths to custom cellprofiler pipeline files (cppipe)

| Parameter                       | Description                                                                | Type   | Default | Required |
| ------------------------------- | -------------------------------------------------------------------------- | ------ | ------- | -------- |
| `--painting_illumcalc_cppipe`   | Cellprofiler pipeline for painting illumination calculation.               | string |         | ✅       |
| `--painting_illumapply_cppipe`  | Cellprofiler pipeline for applying illumination profiles for painting arm. | string |         | ✅       |
| `--painting_segcheck_cppipe`    | Cellprofiler pipeline for running segmentation QC check.                   | string |         | ✅       |
| `--barcoding_illumcalc_cppipe`  | Cellprofiler pipeline for barcoding arm illumination calculation.          | string |         | ✅       |
| `--barcoding_illumapply_cppipe` | Cellprofiler pipeline for illumination profiles for barcoding arm.         | string |         | ✅       |
| `--barcoding_preprocess_cppipe` | Cellprofiler pipeline for barcoding preprocessing.                         | string |         | ✅       |
| `--combinedanalysis_cppipe`     | Cellprofiler pipeline for combined analysis.                               | string |         | ✅       |

## Painting arm parameters

Configuration options for the paintingarm of the pipeline.

| Parameter                     | Description                                                  | Type    | Default               | Required |
| ----------------------------- | ------------------------------------------------------------ | ------- | --------------------- | -------- |
| `--painting_round_or_square`  | Well shape for processing                                    | string  | `round`               |          |
| `--painting_quarter_if_round` | Whether to divide round wells into quarters for processing   | boolean | `True`                |          |
| `--painting_overlap_pct`      | Image overlap percentage                                     | integer | `10`                  |          |
| `--painting_scalingstring`    |                                                              | integer | `1`                   |          |
| `--painting_imperwell`        | Number of images per well                                    | string  | `unused`              |          |
| `--painting_rows`             | Rows for image grid layout                                   | integer | `2`                   |          |
| `--painting_columns`          | Columns for image grid layout                                | integer | `2`                   |          |
| `--painting_stitchorder`      | Tile arrangement method                                      | string  | `Grid: snake by rows` |          |
| `--painting_xoffset_tiles`    | Optional offsets for troubleshooting stitching misalignments | integer | `0`                   |          |
| `--painting_yoffset_tiles`    | Optional offsets for troubleshooting stitching misalignments | integer | `0`                   |          |

## Barcoding (Sequencing-by-synthesis) options

Configuration options for the barcoding (SBS) arm of the pipeline.

| Parameter                        | Description                                                                       | Type    | Default               | Required |
| -------------------------------- | --------------------------------------------------------------------------------- | ------- | --------------------- | -------- |
| `--barcoding_round_or_square`    | Well shape for processing                                                         | string  | `round`               |          |
| `--barcoding_quarter_if_round`   | Whether to divide round wells into quarters for processing                        | boolean | `True`                |          |
| `--barcoding_overlap_pct`        | Image overlap percentage                                                          | integer | `10`                  |          |
| `--barcoding_scalingstring`      | Number of images per well                                                         | number  | `1.99`                |          |
| `--barcoding_imperwell`          | Number of images per well                                                         | string  | `unused`              |          |
| `--barcoding_rows`               | Rows for image grid layout                                                        | integer | `2`                   |          |
| `--barcoding_columns`            | Columns for image grid layout                                                     | integer | `2`                   |          |
| `--barcoding_stitchorder`        | Tile arrangement method                                                           | string  | `Grid: snake by rows` |          |
| `--barcoding_xoffset_tiles`      | Optional offsets for troubleshooting stitching misalignments                      | integer | `0`                   |          |
| `--barcoding_yoffset_tiles`      | Optional offsets for troubleshooting stitching misalignments                      | integer | `0`                   |          |
| `--barcoding_shift_threshold`    | Shift threshold for barcoding align QC step.                                      | integer | `50`                  |          |
| `--barcoding_corr_threshold`     | Correlation threshold for barcoding align QC step.                                | number  | `0.9`                 |          |
| `--acquisition_geometry_rows`    | Number of rows in acquisition geometry for QC spatial plots (square patterns).    | integer | `2`                   |          |
| `--acquisition_geometry_columns` | Number of columns in acquisition geometry for QC spatial plots (square patterns). | integer | `2`                   |          |

## General pipeline parameters for both arms

| Parameter           | Description                               | Type    | Default | Required |
| ------------------- | ----------------------------------------- | ------- | ------- | -------- |
| `--tileperside`     | Number of tiles to create along each axis | integer | `10`    |          |
| `--final_tile_size` | Pixel dimensions for output tiles         | integer | `5500`  |          |
| `--compress`        | Whether to compress output files          | boolean | `True`  |          |

## Institutional config options

Parameters used to describe centralised config profiles. These should not be edited.

| Parameter | Description | Type | Default | Required |
| --------- | ----------- | ---- | ------- | -------- |

## Cellprofiler plugins

| Parameter                   | Description                                  | Type   | Default                                                                                                                    | Required |
| --------------------------- | -------------------------------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------- | -------- |
| `--callbarcodes_plugin`     | Cellprofiler plugin for calling barcodes.    | string | `https://raw.githubusercontent.com/CellProfiler/CellProfiler-plugins/refs/heads/master/active_plugins/callbarcodes.py`     |          |
| `--compensatecolors_plugin` | Cellprofiler plugin for compensating colors. | string | `https://raw.githubusercontent.com/CellProfiler/CellProfiler-plugins/refs/heads/master/active_plugins/compensatecolors.py` |          |

## Generic options

Less common options for the pipeline, typically set in a config file.

| Parameter                       | Description                                                               | Type   | Default | Required |
| ------------------------------- | ------------------------------------------------------------------------- | ------ | ------- | -------- |
| `--multiqc_methods_description` | Custom MultiQC yaml file containing HTML including a methods description. | string |         |          |
