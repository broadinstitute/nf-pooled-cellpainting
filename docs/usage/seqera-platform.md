# Running on Seqera Platform

Execute the pipeline on cloud and HPC infrastructure using Seqera Platform.

## Overview

[Seqera Platform](https://seqera.io) provides:

- **Cloud execution**: AWS, Azure, Google Cloud
- **HPC integration**: SLURM, SGE, PBS, LSF
- **Resource optimization**: Auto-scaling and cost management
- **Monitoring**: Real-time execution dashboards
- **Collaboration**: Team workspaces and sharing

## Getting Started

### Prerequisites

- Seqera Platform account (sign up at [cloud.seqera.io](https://cloud.seqera.io))
- Compute environment configured (AWS Batch, Azure Batch, HPC cluster, etc.)
- Pipeline repository accessible (GitHub, GitLab, Bitbucket)

### Create Compute Environment

1. Navigate to **Compute Environments** in Seqera Platform
2. Click **Add Compute Environment**
3. Select your infrastructure:
    - **AWS Batch**: Automatic EC2 provisioning
    - **Azure Batch**: Azure VM provisioning
    - **Google Cloud Batch**: GCP compute instances
    - **HPC Cluster**: SLURM, SGE, PBS, LSF
4. Configure credentials and resource limits
5. Save the compute environment

### Add Pipeline

1. Go to **Launchpad**
2. Click **Add Pipeline**
3. Enter repository URL: `https://github.com/your-org/nf-pooled-cellpainting`
4. Select compute environment
5. Configure default parameters

## Launching Pipelines

### Via Web Interface

1. Navigate to **Launchpad**
2. Select **nf-pooled-cellpainting**
3. Configure run parameters:
    - Input samplesheet (S3/Azure/GCS path or local upload)
    - Output directory
    - CellProfiler pipelines
    - QC parameters
4. Click **Launch**

### Via Tower CLI

```bash
# Install Tower CLI
pip install tower-cli

# Configure credentials
tw login

# Launch pipeline
tw launch \
  your-org/nf-pooled-cellpainting \
  --compute-env my-compute-env \
  --params-file params.json
```

### Via Nextflow

Add Seqera Platform integration:

```bash
nextflow run your-org/nf-pooled-cellpainting \
  --input s3://bucket/samplesheet.csv \
  --outdir s3://bucket/results/ \
  -with-tower \
  -resume
```

## Configuration

### Pipeline Parameters

Create `params.json`:

```json
{
  "input": "s3://my-bucket/samplesheet.csv",
  "barcodes": "s3://my-bucket/barcodes.csv",
  "outdir": "s3://my-bucket/results/",

  "painting_illumcalc_cppipe": "s3://my-bucket/pipelines/painting_illumcalc.cppipe",
  "painting_illumapply_cppipe": "s3://my-bucket/pipelines/painting_illumapply.cppipe",

  "cp_img_overlap_pct": 10,
  "range_skip": 16,

  "qc_painting_passed": true,
  "qc_barcoding_passed": true
}
```

### Compute Environment Configuration

Configure process-specific resources:

```groovy
// In nextflow.config or custom config
process {
    withName: 'CELLPROFILER_ILLUMCALC' {
        cpus = 16
        memory = 64.GB
        time = 8.h
        queue = 'large'
    }

    withName: 'CELLPROFILER_ILLUMAPPLY' {
        cpus = 8
        memory = 32.GB
        time = 4.h
        queue = 'medium'
    }

    withName: 'FIJI_.*' {
        cpus = 4
        memory = 16.GB
        time = 2.h
    }
}
```

## Cloud Storage Integration

### AWS S3

Configure S3 access:

```groovy
aws {
    accessKey = '<YOUR_ACCESS_KEY>'
    secretKey = '<YOUR_SECRET_KEY>'
    region = 'us-east-1'
}
```

Or use IAM roles (recommended):

```groovy
aws {
    region = 'us-east-1'
}
```

Example paths:

```bash
--input s3://my-bucket/data/samplesheet.csv
--outdir s3://my-bucket/results/
```

### Azure Blob Storage

```groovy
azure {
    storage {
        accountName = '<YOUR_ACCOUNT>'
        accountKey = '<YOUR_KEY>'
    }
}
```

Example paths:

```bash
--input az://container/samplesheet.csv
--outdir az://container/results/
```

### Google Cloud Storage

```groovy
google {
    project = 'my-project'
    region = 'us-central1'
}
```

Example paths:

```bash
--input gs://my-bucket/samplesheet.csv
--outdir gs://my-bucket/results/
```

## Monitoring

### Real-time Dashboard

Seqera Platform provides:

- **Task progress**: See which tasks are running, completed, or failed
- **Resource usage**: CPU, memory, and time per task
- **Cost tracking**: Estimated cloud costs
- **Logs**: Live logs for each task

### Notifications

Configure notifications:

1. Go to **Settings** → **Notifications**
2. Add webhook or email endpoint
3. Select events: pipeline started, completed, failed

### Reports

Download execution reports:

- Execution timeline
- Resource usage charts
- Task failure summaries

## Cost Optimization

### Spot Instances

Use spot/preemptible instances for cost savings:

```groovy
process {
    queue = 'spot'
    errorStrategy = 'retry'
    maxRetries = 3
}
```

### Resource Allocation

Right-size process resources:

```groovy
process {
    // Avoid over-allocation
    withName: 'CELLPROFILER_.*' {
        cpus = { task.attempt == 1 ? 8 : 16 }
        memory = { task.attempt == 1 ? 32.GB : 64.GB }
    }
}
```

### Auto-scaling

Configure compute environment auto-scaling:

- **Min instances**: 0 (for cost savings)
- **Max instances**: Based on workload
- **Scaling policy**: Scale up quickly, scale down slowly

## HPC Integration

### SLURM Example

```groovy
process {
    executor = 'slurm'
    queue = 'normal'
    clusterOptions = '--account=myaccount'

    withName: 'CELLPROFILER_.*' {
        cpus = 16
        memory = 64.GB
        time = 8.h
        queue = 'large'
    }
}
```

### SGE Example

```groovy
process {
    executor = 'sge'
    penv = 'smp'
    queue = 'all.q'

    withName: 'CELLPROFILER_.*' {
        cpus = 16
        memory = '64G'
        time = '8h'
    }
}
```

## Best Practices

1. **Use cloud storage**: Store input/output data in cloud buckets
2. **Test locally first**: Validate with small dataset before scaling
3. **Monitor costs**: Track resource usage and optimize
4. **Use spot instances**: Reduce costs with preemptible VMs
5. **Configure retries**: Handle transient cloud failures
6. **Enable resume**: Always use `-resume` for failed runs
7. **Version control**: Tag pipeline releases for reproducibility

## Troubleshooting

### Authentication Issues

Check credentials:

```bash
# AWS
aws s3 ls s3://my-bucket/

# Azure
az storage blob list --account-name myaccount --container-name mycontainer

# Google Cloud
gsutil ls gs://my-bucket/
```

### Resource Limits

Increase compute environment limits:

- Max instances
- Max CPUs
- Max memory

### Network Issues

Ensure compute environment can access:

- Pipeline repository (GitHub/GitLab)
- Cloud storage (S3/Azure/GCS)
- Container registries

## Next Steps

- [Parameters Reference](parameters.md) - Configure pipeline
- [Architecture](../developer/architecture.md) - Understand pipeline design
- [Troubleshooting](../reference/troubleshooting.md) - Solve common issues
