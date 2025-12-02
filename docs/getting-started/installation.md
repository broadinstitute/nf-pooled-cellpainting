# Installation

This page describes two modes to execute the `nf-pooled-cellpainting` pipeline: locally using the Nextflow CLI (with Docker) or on the cloud using the Seqera Platform.

## Mode 1: Nextflow CLI (Local/Server)

This mode is best for development, testing, or running on a single server.

### Prerequisites

1.  **Java**: Version 11 or later.
2.  **Nextflow**: Version `23.04.0` or later.
3.  **Docker**: Engine must be installed and running.

### Setup

1.  **Install Nextflow**:

    ```bash
    curl -s https://get.nextflow.io | bash
    mv nextflow /usr/local/bin/
    ```

2.  **Test the installation**:
    Run the pipeline help command to verify everything is working and Docker is accessible:

    ```bash
    nextflow run seqera-services/nf-pooled-cellpainting -profile docker --help -r dev
    ```

3.  Head to the [Quick Start Guide](quickstart.md) to run your first test analysis.

---

## Mode 2: Seqera Platform (AWS Batch)

This mode is recommended for production runs at scale.

### Prerequisites

1.  **Seqera Platform Account**: Access to a workspace.
2.  **AWS Batch Compute Environment**: You must have an AWS Batch Compute Environment (CE) configured in your workspace. This CE provides the scalable compute resources needed for the pipeline.

### Setup

1.  **Add pipeline to Launchpad**:
    - Navigate to the **Launchpad** in your workspace.
    - Click **Add Pipeline**.
    - Enter the repository URL: `https://github.com/seqera-services/nf-pooled-cellpainting`.
    - Select your AWS Batch Compute Environment.

2.  **Launch**:
    You can now launch runs directly from the UI, configuring parameters via the web interface or providing json or yaml syntax for configuration.

---

## Prepare Input Files

For detailed instructions on how to prepare your samplesheet, barcodes file, and CellProfiler pipelines, please refer to the [Using Your Own Dataset](../usage/custom-data.md) guide.

## Next Steps

- [Quick Start Guide](quickstart.md) - Run your first analysis.
- [Parameters Reference](../usage/parameters.md) - See all available configuration options.
