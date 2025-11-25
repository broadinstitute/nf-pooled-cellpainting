# Using Your Own Dataset

To run the pipeline on your own data, you need to prepare a few key input files. This guide details the requirements for each.

## 1. Samplesheet

The samplesheet is a CSV file that maps your image files to their experimental metadata. It tells the pipeline where to find the images and how they relate to each other (batch, plate, well, site).

### Format Requirements

- **Format**: Comma-separated values (CSV)
- **Header**: Required (see columns below)
- **Paths**: Must be **absolute paths** or valid **S3 URIs**. Relative paths are not supported.

### Columns

| Column     | Description                                 | Format                               |
| ---------- | ------------------------------------------- | ------------------------------------ |
| `path`     | Path to the directory containing the images | Directory path (local or S3)         |
| `arm`      | Experimental arm                            | String (`painting` or `barcoding`)   |
| `batch`    | Batch identifier                            | String                               |
| `plate`    | Plate identifier                            | String                               |
| `well`     | Well identifier                             | String (e.g., `A01`)                 |
| `channels` | Channel names                               | String (comma-separated if multiple) |
| `site`     | Site number                                 | Integer                              |
| `cycle`    | Cycle number (for barcoding)                | Integer (only for barcoding)         |
| `n_frames` | Number of frames/channels                   | Integer                              |

### Example

```csv
path,arm,batch,plate,well,channels,site,cycle,n_frames
/data/images/painting/batch1/plate1/,painting,batch1,plate1,A01,DAPI-GFP-RFP,1,,3
/data/images/barcoding/batch1/plate1/,barcoding,batch1,plate1,A01,Cy3-Cy5,1,1,2
/data/images/barcoding/batch1/plate1/,barcoding,batch1,plate1,A01,Cy3-Cy5,1,2,2
```

!!! tip "Channel Names"
Ensure the channel names in the `channels` column match the names used in your CellProfiler pipelines if you are using `LoadData` modules that reference them, although the pipeline handles most file discovery automatically.

## 2. Barcodes File

This CSV file defines the known barcodes in your library. It is used to map the decoded sequences back to gene identifiers.

### Format

- **Columns**: `barcode_id`, `sequence`
- **Sequence**: The nucleotide sequence of the barcode (A, C, G, T).

### Example

```csv
barcode_id,sequence
id1,TAAATAGTAGGATTTACACG
id2,TAGGTGATATCAATCGATAC
id3,ATAGCTGATTCCATTCGCTA
```

## 3. CellProfiler Pipelines (`.cppipe`)

The pipeline uses CellProfiler for image analysis. You must provide `.cppipe` files for each stage of the analysis. These files define the image processing modules (e.g., IdentifyPrimaryObjects, MeasureObjectIntensity).

You need to provide paths to these files using the corresponding parameters:

### Painting Arm

- `--painting_illumcalc_cppipe`: Calculates illumination correction functions.
- `--painting_illumapply_cppipe`: Applies illumination correction.
- `--painting_segcheck_cppipe`: Performs segmentation for QC (stops here in Phase 1).

### Barcoding Arm

- `--barcoding_illumcalc_cppipe`: Calculates illumination correction for barcoding cycles.
- `--barcoding_illumapply_cppipe`: Applies illumination correction.
- `--barcoding_preprocess_cppipe`: Performs base calling (decoding).

### Combined

- `--combinedanalysis_cppipe`: The final step that merges data. **Crucially**, this pipeline must expect the input object tables from the previous steps.

!!! warning "Pipeline Compatibility"
Ensure your CellProfiler pipelines are compatible with the version of CellProfiler used in the container (currently 4.2.x).

## 4. Directory Structure

While the pipeline is flexible, organizing your data logically helps avoid errors. A recommended structure is:

```
project_dir/
├── images/
│   ├── batch1/
│   │   ├── plate1/
│   │   │   ├── painting/
│   │   │   └── barcoding/
│   │   └── ...
├── metadata/
│   ├── samplesheet.csv
│   └── barcodes.csv
└── pipelines/
    ├── painting_illum.cppipe
    ├── painting_seg.cppipe
    └── ...
```

## Running the Pipeline

Once your inputs are ready, run the pipeline pointing to your files:

```bash
nextflow run seqera-services/nf-pooled-cellpainting \
    --input metadata/samplesheet.csv \
    --barcodes metadata/barcodes.csv \
    --outdir results \
    --painting_illumcalc_cppipe pipelines/painting_illum.cppipe \
    ... [other pipeline paths] ... \
    -profile docker
```

See the [Parameters Guide](parameters.md) for a full list of configuration options.
