# Installation/Setup

We provide installation and run instructions for both local runs and cloud runs with Seqera Platform.

**Local installation is best for development, testing, or running on a single server**. We recommend you perform a local installation regardless of whether you will eventually also run at scale in Seqera Platform so that you can simply run minimal test pipelines.

**Cloud execution with Seqera Platform is recommended for production runs at scale.** Seqera Platform (formerly Nextflow Tower) provides a web interface for launching, monitoring, and managing Nextflow pipelines on cloud infrastructure.

## Local Installation of Nextflow

### Local Prerequisites

1. **Java**: Version 11 or later
2. **Nextflow**: Version 25.04.0 or later
3. **Docker**: Engine must be installed and running

### Local Setup

1. Install Nextflow:

    ```bash
    curl -s https://get.nextflow.io | bash
    mv nextflow /usr/local/bin/
    ```

2. Verify installation:

    ```bash
    nextflow run broadinstitute/nf-pooled-cellpainting -profile docker --help -r dev
    ```

After successfully verifying installation, we recommend you [run the local test example](quick_start.md).

## Cloud Setup of Seqera Platform

### AWS Prerequisites

1. **Seqera Platform Account**: Access to a workspace at [cloud.seqera.io](https://cloud.seqera.io)
2. **AWS Account**: With permissions to create Batch resources
3. **AWS Credentials**: Configured in Seqera Platform
4. **S3 Bucket**: For work directory and data storage

### Setting Up an AWS Batch Compute Environment

From your Seqera Platform workspace, navigate to **Compute Environments** → **Add Compute Environment**.

#### Basic Configuration

| Setting | Recommended Value | Notes |
|---------|-------------------|-------|
| **Name** | `AWSBatch_pooled_cellpainting` | Descriptive name |
| **Platform** | AWS Batch | |
| **Credentials** | Your AWS credentials | Must have AWS Batch permissions |
| **Region** | `us-east-1` (or your preferred region) | Should match your S3 bucket |
| **Work directory** | `s3://your-bucket/work` | Pipeline scratch data |

#### Seqera Features (Optional but Recommended)

| Feature | Description | Recommendation |
|---------|-------------|----------------|
| **Wave containers** | Container provisioning service | Enable for easier container management |
| **Fusion v2** | Virtual distributed file system for S3 | Enable for faster S3 access |
| **Fast instance storage** | NVMe for faster I/O | Enable if using Fusion v2 |
| **Fusion Snapshots** | Auto-restore on spot interruption | Enable for spot instance resilience |

#### Config Mode: Batch Forge

Select **Batch Forge** for automated queue creation. Seqera will create:

- A head queue (for the Nextflow process)
- A compute queue (for pipeline tasks)

#### Forge Configuration

| Setting | Recommended Value | Notes |
|---------|-------------------|-------|
| **Provisioning model** | Spot | Cost-effective; use On-demand for critical runs |
| **Max CPUs** | 2000 | Total CPU pool; adjust based on workload |
| **Allowed S3 buckets** | Your data bucket(s) | Grant read-write access |
| **EFS/FSx** | None | Not required for most use cases |

#### Advanced Options: Instance Types

For image processing workloads, select instance families with:

- Good compute-to-memory ratio
- NVMe storage (if using Fusion)

**Recommended instance types:**

- `c6id` - Compute-optimized with NVMe
- `m6id` - General-purpose with NVMe
- `r6id` - Memory-optimized with NVMe

```{warning} 
**When using Fusion Snapshots, pin specific instance sizes** (not just families) to ensure successful snapshot creation. Snapshots require sufficient memory-to-NVMe-bandwidth ratio to complete within the 2-minute spot reclamation window.

**Recommended for Fusion Snapshots** (pin all of these in your compute environment):

- `c6id.large`, `c6id.xlarge`, `c6id.2xlarge`, `c6id.4xlarge`, `c6id.8xlarge`, `c6id.12xlarge`

Avoid letting AWS auto-select very large instances (e.g., `32xlarge`) which may sit idle after some tasks complete, costing ~$6/hour for minimal utilization. The `12xlarge` ceiling provides sufficient memory for most Combined Analysis tasks while limiting cost exposure.
```

After setup, we recommend you [run the test example](quick_start.md).
