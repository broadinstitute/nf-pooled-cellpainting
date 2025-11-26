# Parameters

This page describes the parameters available in the pipeline.

## Input/output options

Define where the pipeline should find input data and save output data.

| Parameter                  | Description                                                                                                                                                                                                                                                                                                                                                                      | Default                                                          | Required |
| :------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------- | :------- |
| `--input`                  | Path to comma-separated file containing information about the samples in the experiment.<br><details><summary>Help</summary>You will need to create a design file with information about the samples in your experiment before running the pipeline. Use this parameter to specify its location. It has to be a comma-separated file with 3 columns, and a header row.</details> |                                                                  | ✅       |
| `--outdir`                 | The output directory where the results will be saved. You have to use absolute paths to storage on Cloud infrastructure.                                                                                                                                                                                                                                                         |                                                                  | ✅       |
| `--qc_painting_passed`     | Flag to check whether quality control for the painting arm has been performed.                                                                                                                                                                                                                                                                                                   |                                                                  |          |
| `--qc_barcoding_passed`    | Flag to check whether quality control for the barcoding arm has been performed.                                                                                                                                                                                                                                                                                                  |                                                                  |          |
| `--barcodes`               | Path to file for barcode information.                                                                                                                                                                                                                                                                                                                                            |                                                                  | ✅       |
| `--fiji_stitchcrop_script` | Path to script to use for FIJI Stitchcrop.                                                                                                                                                                                                                                                                                                                                       | `/home/florian/nf-pooled-cellpainting/bin/stitch_crop.master.py` | ✅       |
| `--range_skip`             | Step number for subsampling images for segcheck.                                                                                                                                                                                                                                                                                                                                 | `2`                                                              |          |
| `--multiqc_title`          | MultiQC report title. Printed as page header, used for filename if not otherwise specified.                                                                                                                                                                                                                                                                                      |                                                                  |          |

## Cellprofiler Pipelines

Paths to custom cellprofiler pipeline files (cppipe)

| Parameter                       | Description                                                                 | Default | Required |
| :------------------------------ | :-------------------------------------------------------------------------- | :------ | :------- |
| `--painting_illumcalc_cppipe`   | Cellprofiler pipeline for painting illumination calculation.                |         | ✅       |
| `--painting_illumapply_cppipe`  | Cellprofiler pipeline for applying illumination profiles for painting arm.  |         | ✅       |
| `--painting_segcheck_cppipe`    | Cellprofiler pipeline for running segmentation QC check.                    |         | ✅       |
| `--barcoding_illumcalc_cppipe`  | Cellprofiler pipeline for barcoding arm illumination calculation.           |         | ✅       |
| `--barcoding_illumapply_cppipe` | Cellprofiler pipeline for applying illumination profiles for barcoding arm. |         | ✅       |
| `--barcoding_preprocess_cppipe` | Cellprofiler pipeline for barcode preprocessing.                            |         | ✅       |
| `--combinedanalysis_cppipe`     | Cellprofiler pipeline for combined analysis.                                |         | ✅       |

## Painting arm parameters

Configuration options for the paintingarm of the pipeline.

| Parameter                     | Description                                                   | Default               | Required |
| :---------------------------- | :------------------------------------------------------------ | :-------------------- | :------- |
| `--painting_round_or_square`  | Well shape for processing.                                    | `round`               |          |
| `--painting_quarter_if_round` | Whether to divide round wells into quarters for processing.   | `True`                |          |
| `--painting_overlap_pct`      | Image overlap percentage.                                     | `10`                  |          |
| `--painting_scalingstring`    | Scaling applied to painting images.                           | `1`                   |          |
| `--painting_imperwell`        | Number of images per well.                                    | `unused`              |          |
| `--painting_rows`             | Rows for image grid layout.                                   | `2`                   |          |
| `--painting_columns`          | Columns for image grid layout.                                | `2`                   |          |
| `--painting_stitchorder`      | Tile arrangement method.                                      | `Grid: snake by rows` |          |
| `--painting_xoffset_tiles`    | Optional offsets for troubleshooting stitching misalignments. | `0`                   |          |
| `--painting_yoffset_tiles`    | Optional offsets for troubleshooting stitching misalignments. | `0`                   |          |

## Barcoding (Sequencing-by-synthesis) options

Configuration options for the barcoding (SBS) arm of the pipeline.

| Parameter                        | Description                                                                       | Default               | Required |
| :------------------------------- | :-------------------------------------------------------------------------------- | :-------------------- | :------- |
| `--barcoding_round_or_square`    | Well shape for processing.                                                        | `round`               |          |
| `--barcoding_quarter_if_round`   | Whether to divide round wells into quarters for processing.                       | `True`                |          |
| `--barcoding_overlap_pct`        | Image overlap percentage.                                                         | `10`                  |          |
| `--barcoding_scalingstring`      | Scaling applied to barcoding images.                                              | `1.99`                |          |
| `--barcoding_imperwell`          | Number of images per well.                                                        | `unused`              |          |
| `--barcoding_rows`               | Rows for image grid layout.                                                       | `2`                   |          |
| `--barcoding_columns`            | Columns for image grid layout.                                                    | `2`                   |          |
| `--barcoding_stitchorder`        | Tile arrangement method.                                                          | `Grid: snake by rows` |          |
| `--barcoding_xoffset_tiles`      | Optional offsets for troubleshooting stitching misalignments.                     | `0`                   |          |
| `--barcoding_yoffset_tiles`      | Optional offsets for troubleshooting stitching misalignments.                     | `0`                   |          |
| `--barcoding_shift_threshold`    | Shift threshold for barcoding align QC step.                                      | `50`                  |          |
| `--barcoding_corr_threshold`     | Correlation threshold for barcoding align QC step.                                | `0.9`                 |          |
| `--acquisition_geometry_rows`    | Number of rows in acquisition geometry for QC spatial plots (square patterns).    | `2`                   |          |
| `--acquisition_geometry_columns` | Number of columns in acquisition geometry for QC spatial plots (square patterns). | `2`                   |          |

## General pipeline parameters for both arms

| Parameter           | Description                                | Default | Required |
| :------------------ | :----------------------------------------- | :------ | :------- |
| `--tileperside`     | Number of tiles to create along each axis. | `10`    |          |
| `--final_tile_size` | Pixel dimensions for output tiles.         | `5500`  |          |
| `--compress`        | Whether to compress output files.          | `True`  |          |

## Cellprofiler plugins

| Parameter                   | Description                                  | Default                                                                                                                    | Required |
| :-------------------------- | :------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------- | :------- |
| `--callbarcodes_plugin`     | Cellprofiler plugin for calling barcodes.    | `https://raw.githubusercontent.com/CellProfiler/CellProfiler-plugins/refs/heads/master/active_plugins/callbarcodes.py`     |          |
| `--compensatecolors_plugin` | Cellprofiler plugin for compensating colors. | `https://raw.githubusercontent.com/CellProfiler/CellProfiler-plugins/refs/heads/master/active_plugins/compensatecolors.py` |          |

## Generic options

Less common options for the pipeline, typically set in a config file.

| Parameter                       | Description                                                               | Default | Required |
| :------------------------------ | :------------------------------------------------------------------------ | :------ | :------- |
| `--multiqc_methods_description` | Custom MultiQC yaml file containing HTML including a methods description. |         |          |
