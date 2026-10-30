# broadinstitute/nf-pooled-cellpainting: Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v1.1.0 - 2026-10-23

### `Added`

- **New entrypoints** alongside the default FIJI-based workflow (`POOLED_CELLPAINTING`), selected with `-entry`:
  - `NO_STITCH`: same QC flow as the default workflow but skips `FIJI_STITCHCROP` in both arms; combined analysis runs on the pre-stitch per-site images.
  - `STITCH_ALIGN_CROP`: stitching, alignment and cropping without FIJI. Order is illumcalc, illumapply, per-arm stitch (ashlar), within-arm cycle alignment, cross-arm alignment, per-arm crop, segmentation check and preprocess, then a single QC gate before combined analysis. Stitch/align/crop always run; only combined analysis is gated by `qc_painting_passed`/`qc_barcoding_passed`. Supports multi-cycle painting.
- **New local modules and scripts**: `STITCH` (`bin/stitch.py`), `ALIGN_INTRAARM` (`bin/align_intraarm.py`), `ALIGN_COMBINED` (`bin/align_combined.py`), `CROP` (`bin/crop.py`), `QC_PAINTINGALIGN`, `QC_CHECKDUPLICATEIMAGES` and `CELLPROFILER_PLUGINS_UPDATE`, with new `stitch_align_crop`, `align` and `ashlar` containers.
- **Support for Phenix-style acquisition.** `phenix` parameter (first site is the well centre) for both the FIJI and ashlar stitchers; round-well site layouts now live in the shared `assets/stitchcrop/well_site_layouts.json`. Barcode image-name matching also accepts 2- and 3-colour barcode channels (`A488`, `A568`, `A647`).
- **Cellpose support** for segmentation check and combined analysis: `cellprofiler_flavor` (`default`, `cellpose2`, `cellpose3`), `cellprofiler_container_override`, and `runcellpose_plugin`.
- **Enhanced CellProfiler plugin support**. `update_cellprofiler_plugins` and `cellprofiler_plugins_repo` to clone the latest CellProfiler-plugins at runtime. User-set `callbarcodes_plugin`/`compensatecolors_plugin` still take precedence over the clone (tracked via the hidden `callbarcodes_plugin_default` and `compensatecolors_plugin_default`).
- **Allow passing of Foci objects instead of images to analysis**. Optional `FociObjects` image (`.tiff`) from barcode preprocessing, routed into combined analysis. `combinedanalysis_include_barcoding_images` (default `false`) for the `STITCH_ALIGN_CROP` combined analysis.
- **Expanded QC**:
  - `check_duplicate_images` (default `false`): fails the run if any two output images of a CellProfiler step are pixel-identical (blank frames ignored). Runs after illumcalc, illumapply and preprocess.
  - painting-alignment QC for multicycle painting
  - barcode-alignment QC with two alignment methods (original NCC and MI), pixel-shift and correlation plots, channel-combination plots and per-well ordering
  - montages of sites failing alignment
  - improved illumination and `.npy` checks.
  - Warnings when sites are dropped or missing while staging the stitch grid.
- Documentation migrated from MkDocs to Jupyter Book and reorganised
- `cellprofiler_large` resource label and `stitch`, `crop` and `align` labels in `conf/base.config`.

### `Changed`

- **Output layout:** all `qc_reports` are now nested under the batch (`workspace/qc_reports/<batch>/...`). `STITCH_ALIGN_CROP` uses its own numbered stage folders and writes `images_corrected`, `images_corrected_stitched`, `images_aligned_intraarm`, `images_aligned_combined`, `images_aligned_cropped` and `images_preprocessed` (documented in the output docs). FIJI cropped images are no longer written to per-channel or per-cycle subfolders.
- **Parameter defaults:** `painting_imperwell` and `barcoding_imperwell` are now integers (default `80` and `20`, previously `"unused"`); `barcoding_channame` defaults to `DAPI` (was `DNA`). `fiji_stitchcrop_script` no longer has a hardcoded default path in the schema (the config default is unchanged).
- **LoadData.csv outputs.** `load_data.csv` files are written per batch/plate to `workspace/load_data_csv/<batch>/<plate>/`, with true (`FileName_`) and staged (`StagedFileName_`) columns.
- `FIJI_STITCHCROP` takes the `well_site_layouts_json` and `phenix` inputs and uses the `cellprofiler/nf-pooled-cellpainting:fiji_v1` container; `CELLPROFILER_COMBINEDANALYSIS` now uses the `cellprofiler_large` label.
- `load_data.csv` generation rewritten: callers state per-(file, channel) metadata explicitly instead of the script parsing filenames and inferring pipeline type, and duplicate image names are caught.
- `barcoding_preprocess.cppipe` metadata regex uses `Well` instead of `Well_Value`.
- Resource handling: tasks exiting with status 0 or 2147483647 (spot reclamation or host termination after the script finished) retry up to 8 times without escalating memory/time/CPUs; `aws.batch.maxSpotAttempts = 5`. Real failures still retry once or twice as before.
- Higher memory for preprocess (12 GB) and combined analysis (40 GB) in `STITCH_ALIGN_CROP`.
- Async-sourced file lists are sorted and sources of randomness removed so runs are deterministic and `-resume` hashes are stable.
- `barcodes.csv` is staged by copying into `images/` inside the task.
- Updated CellProfiler plugin pins (`callbarcodes`, plus new `runcellpose`), nf-core components (MultiQC, nf-schema and pipeline utils), nf-test 0.9.5 and nft-utils 0.0.4.
- CI hardened: least-privilege permissions, actions pinned to commit SHAs, PR-comment workflows hardened per nf-core advisory, `fix_linting.yml` removed, lint on push to `dev` and `main`, slow tests skipped on PRs.

### `Fixed`

- Channels and cycles now propagate into combined analysis; single-channel and list-valued channel handling in `load_data.csv` generation and illumination gathering.
- A single globbed output file no longer gets iterated as path segments when building combined-analysis metadata.
- Combined-analysis input order is sorted, so `-resume` no longer breaks on arrival-order differences.
- `FIRST_SITE_INDEX` exported to the Fiji stitch script; typo in the combined analysis cppipe filename.
- Segmentation-check/combined-analysis `.png` overlays are optional (all-black sites produce none).
- Writable cache dirs (`HOME`, `MPLCONFIGDIR`, `XDG_CACHE_HOME`, `NUMBA_CACHE_DIR`) for containers run as non-root, e.g. in Seqera.
- Dead memory override for the `STITCH_ALIGN_CROP` combined analysis.
- `process.cache` is not set to `lenient` for S3-backed work dirs, so a retrigger cannot reuse stitched files that differ from what was published.

### `Deprecated`

- The extra painting-specific cycle column in `load_data.csv` has been removed.
- The single, flat `workspace/load_data_csv/<name>.load_data.csv` merge files are replaced by per-batch/plate files.

## v1.0.1 - 2026-07-22

### `Fixed`

- CellProfiler plugin URLs are pinned to immutable commit SHAs.

## v1.0.0 - 2025-12-05

Initial release of broadinstitute/nf-pooled-cellpainting, created with the [nf-core](https://nf-co.re/) template.
