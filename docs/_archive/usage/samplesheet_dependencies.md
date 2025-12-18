# Samplesheet Dependencies & Channel Naming

This document outlines the critical dependencies between the input samplesheet, the Nextflow pipeline logic, and the Python scripts that generate `load_data.csv` files for CellProfiler. Correctly formatting your samplesheet and naming your files is essential for the pipeline to function correctly.

## 1. Samplesheet Requirements

The samplesheet is the single source of truth for experimental metadata. The pipeline expects specific columns to be present.

### Required Columns

| Column     | Description                       | Critical Dependency                                                                                                      |
| :--------- | :-------------------------------- | :----------------------------------------------------------------------------------------------------------------------- |
| `batch`    | Batch identifier (e.g., `Batch1`) | Used for grouping images for illumination calculation.                                                                   |
| `plate`    | Plate identifier (e.g., `Plate1`) | **CRITICAL**: Must match the plate name used in filenames for the Combined Analysis step.                                |
| `well`     | Well identifier (e.g., `A01`)     | **CRITICAL**: Used to map images to metadata.                                                                            |
| `site`     | Site/Field number (e.g., `1`)     | **CRITICAL**: Used to map images to metadata.                                                                            |
| `channels` | Comma-separated list of channels  | **CRITICAL**: Used as column headers in `load_data.csv`. Must match the channel names parsed from filenames (see below). |
| `arm`      | `painting` or `barcoding`         | Determines which subworkflow processes the image.                                                                        |
| `cycle`    | Cycle number (Barcoding only)     | **CRITICAL**: Used for grouping barcoding cycles.                                                                        |

### Metadata Flow

1.  **Ingestion**: The samplesheet is read by `main.nf`.
2.  **Channel Creation**: Nextflow creates channels carrying `[meta, image]` tuples. `meta` contains all the columns above.
3.  **Processing**:
    - **Illumination Calculation/Correction**: Metadata (`plate`, `channels`, `cycle`) is passed _explicitly_ to the Python script via CLI arguments.
    - **Preprocessing & Combined Analysis**: Metadata is _implicitly_ derived from filenames in some legacy paths, but the modern implementation relies on the `meta` map passed from Nextflow.


!!! danger Single Source of Truth
    The pipeline is designed so that metadata (Plate, Well, Site) comes from the **samplesheet**, not the filenames. However, **filenames must still follow specific patterns** so the Python script can correctly identify which file corresponds to which channel/cycle.

---

## 2. Channel Naming Constraints

The Python script (`bin/generate_load_data_csv.py`) uses regular expressions to parse filenames and extract **Channel** and **Cycle** information. This is where most user errors occur.

### A. Cell Painting Arm

**Input Images (Raw)**

- **Requirement**: Must contain the channel names specified in your samplesheet `channels` column.
- **Regex**: `Channel([^_]+)` matches the channel list.
- **Example**: `..._ChannelDNA,Phalloidin,Mito_...`

**Corrected Images (Intermediate)**

- **Requirement**: The pipeline generates these. If you provide pre-corrected images, they must match the pattern.
- **Regex**: `Corr(.+?)\.tiff?`
- **Example**: `Plate_P1_Well_A01_Site_1_CorrDNA.tiff`
  - Here, `DNA` is extracted as the channel name.
  - **Constraint**: This extracted name MUST match one of the entries in your samplesheet `channels` column (e.g., `DNA`).

### B. Barcoding Arm

**Input Images (Raw)**

- **Requirement**: Must contain cycle information if it's a multi-cycle experiment.

**Preprocessing & Alignment**

- **Constraint**: The barcoding arm is stricter. It expects specific channel names for the barcode bases.
- **Allowed Channels**: `A`, `C`, `G`, `T` (for bases), `DNA`, `DAPI` (for reference).
- **Regex**: `Cycle(\d+)_([ACGT]|DNA|DAPI)\.tiff?`
- **Example**: `Plate_P1_Well_A01_Site_1_Cycle01_A.tiff`
  - `Cycle01` -> Cycle 1
  - `A` -> Channel A

!!! warning Barcoding Channel Names
    Ensure your samplesheet `channels` column for barcoding rows uses standard base names (`A`, `C`, `G`, `T`) or `DNA`/`DAPI`. Using non-standard names (e.g., `Cy5`, `FITC`) may cause the regex to fail or the script to misinterpret the file type.

---

## 3. Combined Analysis Dependencies

The Combined Analysis step merges data from both arms. This is the most fragile step regarding naming.

### The "Plate Name" Trap

The Python script groups files by `(Plate, Well, Site)`.

- **Source**: It takes `Plate`, `Well`, `Site` from the **samplesheet metadata**.
- **Matching**: It looks for files in the input directory.

**The Constraint**:
The input files for combined analysis are generated by previous steps (IllumApply). These files are named using the metadata from those previous steps.

- If your samplesheet says Plate is `Plate_1` (underscore), but your raw filenames said `Plate1` (no underscore) and you relied on filename parsing earlier, you might have a mismatch.
- **Best Practice**: Ensure the `plate` column in your samplesheet EXACTLY matches the plate identifier used in your filenames if you are relying on any filename-based grouping logic.

### Channel Matching

The `generate_load_data_csv.py` script in `combined` mode uses regex to identify if a file is "Cell Painting" or "Barcoding" based on its filename pattern:

1.  **Barcoding Pattern**: Looks for `Cycle(\d+)`.
    - Matches: `..._Cycle01_A.tiff`
2.  **Cell Painting Pattern**: Looks for `Corr(.+)`.
    - Matches: `..._CorrDNA.tiff`

**Impact**:
If you name a Cell Painting channel `Cycle1` (e.g., `CorrCycle1.tiff`), the script might mistakenly try to parse it as a barcoding image because of the `Cycle` keyword.

- **Rule**: Avoid using the word `Cycle` in your Cell Painting channel names.

---

## 4. Summary Checklist

Before running the pipeline:

1. [ ] **Samplesheet Columns**: Ensure `batch`, `plate`, `well`, `site`, `channels`, `arm` are present.

2. [ ] **Channel Names**:

   - Cell Painting: Names in `channels` column match the names in your raw image filenames (e.g., `DNA`, `Mito`).

   - Barcoding: Names in `channels` column are `A`, `C`, `G`, `T`, `DNA`, or `DAPI`.

3. [ ] **Avoid Keywords**: Do not use `Cycle` or `Corr` as part of your raw channel names to avoid regex confusion.

4. [ ] **Consistency**: Ensure `plate` names are consistent across all rows for the same physical plate.
