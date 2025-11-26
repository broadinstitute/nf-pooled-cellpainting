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
"/data/images/painting/batch1/plate1/WellA1_PointA1_0000_ChannelPhalloAF750,CHN2-AF488,DAPI_Seq0000.ome.tiff",painting,Batch1,Plate1,A1,"Phalloidin,CHN2,DNA",1,1,3
"/data/images/barcoding/batch1/plate1/WellA1_PointA1_0000_ChannelC,A,T,G,DAPI_Seq0000.ome.tiff",barcoding,Batch1,Plate1,A1,"C,A,T,G,DNA",1,1,5
"/data/images/barcoding/batch1/plate1/WellA1_PointA1_0001_ChannelC,A,T,G,DAPI_Seq0001.ome.tiff",barcoding,Batch1,Plate1,A1,"C,A,T,G,DNA",2,1,5
```

!!! warning "Channel Names"
Ensure the channel names in the `channels` column match the names used in your CellProfiler pipelines as the channel names will be used to build load_data.csv columns that need to correspond to your cppipe files provided to the pipeline!

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

- `--painting_illumcalc_cppipe`: Calculates illumination correction functions for painting images.
- `--painting_illumapply_cppipe`: Applies illumination correction to painting images.
- `--painting_segcheck_cppipe`: Performs quality control for painting segmentation (stops here in Phase 1).

### Barcoding Arm

- `--barcoding_illumcalc_cppipe`: Calculates illumination correction for barcoding images.
- `--barcoding_illumapply_cppipe`: Applies illumination correction to barcoding images.
- `--barcoding_preprocess_cppipe`: Performs base calling (decoding) for barcodes.

### Combined

- `--combinedanalysis_cppipe`: The final step that merges data. **Crucially**, this pipeline must expect the input object tables from the previous steps.

!!! warning "Pipeline Compatibility"
Ensure your CellProfiler pipelines are compatible with the version of CellProfiler used in the container (currently 4.2.x).

## Running the Pipeline

Once your inputs are ready, run the pipeline pointing to your files:

```bash
nextflow run seqera-services/nf-pooled-cellpainting \
    --input samplesheet.csv \
    --barcodes barcodes.csv \
    --outdir results \
    --painting_illumcalc_cppipe your_painting_illumcalc_cppipe.cppipe \
    --painting_illumapply_cppipe your_painting_illumapply_cppipe.cppipe \
    --painting_segcheck_cppipe your_painting_segcheck_cppipe.cppipe \
    --barcoding_illumcalc_cppipe your_barcoding_illumcalc_cppipe.cppipe \
    --barcoding_illumapply_cppipe your_barcoding_illumapply_cppipe.cppipe \
    --barcoding_preprocess_cppipe your_barcoding_preprocess_cppipe.cppipe \
    --combinedanalysis_cppipe your_combinedanalysis_cppipe.cppipe \
    -profile docker
```

See the [Parameters Guide](parameters.md) for a full list of configuration options.
