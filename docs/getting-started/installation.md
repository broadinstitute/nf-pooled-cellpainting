# Installation

## Prerequisites

### Required

- **Nextflow** `>= 23.04.0`
- **Java** `>= 11`
- **Container engine**: One of:
  - Docker
  - Singularity/Apptainer
  - Podman
  - Shifter
  - Charliecloud

### Optional

- **Seqera Platform account** for cloud/HPC execution
- **Git** for version control

## Install Nextflow

=== "Conda"

    ```bash
    conda install -c bioconda nextflow
    ```

=== "Manual"

    ```bash
    curl -s https://get.nextflow.io | bash
    mv nextflow ~/bin/
    ```

=== "Verify"

    ```bash
    nextflow -version
    ```

## Install Container Engine

=== "Docker"

    Follow the [official Docker installation guide](https://docs.docker.com/get-docker/).

=== "Singularity"

    ```bash
    # On HPC systems, Singularity is often pre-installed
    singularity --version
    ```

=== "Apptainer"

    ```bash
    # Apptainer is the community fork of Singularity
    apptainer --version
    ```

## Get the Pipeline

=== "From GitHub"

    ```bash
    git clone https://github.com/your-org/nf-pooled-cellpainting.git
    cd nf-pooled-cellpainting
    ```

=== "Run Directly"

    Nextflow can pull from GitHub automatically:

    ```bash
    nextflow run your-org/nf-pooled-cellpainting --input samplesheet.csv --outdir results
    ```

## Prepare Input Files

### 1. Samplesheet

Create a CSV with the following columns:

```csv
path,arm,batch,plate,well,channels,site,cycle,n_frames
```

Example:

```csv
/data/images/,painting,batch1,plate1,A01,DAPI-GFP-RFP,1,,4
/data/images/,barcoding,batch1,plate1,A01,Cy3-Cy5,1,1,4
```

### 2. Barcodes File

Create a CSV with barcode definitions:

```csv
barcode_id,sequence
```

### 3. CellProfiler Pipelines

Prepare `.cppipe` files for each stage:

- Painting illumination calculation
- Painting illumination correction
- Segmentation check
- Barcoding illumination calculation
- Barcoding illumination correction
- Barcoding preprocessing
- Combined analysis

### 4. CellProfiler Plugins

Download required plugins:

- `callbarcodes.py`: Barcode calling logic
- `compensatecolors.py`: Color compensation

Store as URL-accessible files or local paths.

## Configuration

Create a `nextflow.config` or use command-line parameters:

```groovy
params {
    input = 'samplesheet.csv'
    barcodes = 'barcodes.csv'
    outdir = 'results'

    // CellProfiler pipelines
    painting_illumcalc_cppipe = 'pipelines/painting_illumcalc.cppipe'
    painting_illumapply_cppipe = 'pipelines/painting_illumapply.cppipe'
    // ... additional pipeline paths
}
```

## Test the Installation

Run a minimal test:

```bash
nextflow run main.nf --help
```

You should see the pipeline help message with all available parameters.

## Next Steps

- [Quick Start Guide](quickstart.md) - Run your first analysis
- [Parameters Reference](../usage/parameters.md) - Configure the pipeline
