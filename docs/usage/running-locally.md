# Running Locally

Guide for running the pipeline on local workstations and compute servers.

## Prerequisites

- Nextflow installed
- Docker or Singularity configured
- Sufficient storage for image data
- Adequate compute resources (recommended: 8+ cores, 32+ GB RAM)

## Configuration

### Local Execution Profile

Create `conf/local.config`:

```groovy
process {
    executor = 'local'
    cpus = 8
    memory = 32.GB

    withName: 'CELLPROFILER_.*' {
        cpus = 4
        memory = 16.GB
    }

    withName: 'FIJI_.*' {
        cpus = 2
        memory = 8.GB
    }
}

docker {
    enabled = true
    runOptions = '-u $(id -u):$(id -g)'
}
```

### Using the Profile

```bash
nextflow run main.nf \
  --input samplesheet.csv \
  -c conf/local.config \
  -resume
```

## Storage Considerations

### Work Directory

Nextflow stores intermediate files in `work/`. Size requirements:

- **Raw images**: Original size × number of processing steps
- **Corrected images**: Similar to raw images
- **Stitched images**: Variable based on stitching configuration

!!! tip "Storage Management"
    Use `-resume` to avoid re-computing completed tasks. Clean work directory periodically:
    ```bash
    nextflow clean -f
    ```

### Output Directory

Final outputs are stored in `--outdir`. Size:

- Illumination functions: ~MB per plate
- Corrected images: ~GB per plate
- Stitched images: Variable
- CSV files: ~MB

## Performance Tuning

### Parallel Execution

Control concurrent jobs:

```groovy
executor {
    queueSize = 8  // Max parallel tasks
}
```

### Process-Specific Resources

Fine-tune resource allocation:

```groovy
process {
    withName: 'CELLPROFILER_ILLUMCALC' {
        cpus = 8
        memory = 32.GB
        time = 8.h
    }

    withName: 'CELLPROFILER_ILLUMAPPLY' {
        cpus = 4
        memory = 16.GB
        time = 4.h
    }
}
```

### Container Caching

Enable container caching to speed up reruns:

=== "Docker"

    ```groovy
    docker {
        enabled = true
        fixOwnership = true
        runOptions = '-u $(id -u):$(id -g)'
    }
    ```

=== "Singularity"

    ```groovy
    singularity {
        enabled = true
        autoMounts = true
        cacheDir = '/path/to/singularity/cache'
    }
    ```

## Monitoring

### Real-time Progress

Monitor execution:

```bash
# In separate terminal
tail -f .nextflow.log
```

### Resource Usage

Check system resources:

```bash
# CPU and memory
htop

# Disk usage
df -h
du -sh work/
```

### Nextflow Reports

Generate execution reports:

```bash
nextflow run main.nf \
  --input samplesheet.csv \
  -with-report report.html \
  -with-timeline timeline.html \
  -with-dag dag.html
```

## Troubleshooting

### Out of Memory

Reduce parallelization:

```groovy
executor {
    queueSize = 4
}

process {
    memory = 16.GB
}
```

### Disk Space

Monitor and clean:

```bash
# Check usage
du -sh work/ results/

# Clean work directory
nextflow clean -f -k
```

### Container Issues

Test container accessibility:

```bash
docker run --rm wave.seqera.io/cellprofiler/cellprofiler:4.2.8 cellprofiler --version
```

## Best Practices

1. **Use `-resume`**: Always resume failed runs
2. **Monitor resources**: Watch CPU, memory, and disk usage
3. **Test with subset**: Validate with small dataset first
4. **Clean regularly**: Remove old work directories
5. **Version control**: Track pipeline version and parameters

## Example Configurations

### Small Workstation (16 GB RAM)

```groovy
process {
    executor = 'local'
    cpus = 4
    memory = 8.GB
}

executor {
    queueSize = 2
}
```

### High-end Server (128 GB RAM)

```groovy
process {
    executor = 'local'
    cpus = 16
    memory = 64.GB
}

executor {
    queueSize = 16
}
```

## Next Steps

- [Seqera Platform](seqera-platform.md) - Scale to cloud/HPC
- [Troubleshooting](../reference/troubleshooting.md) - Solve common issues
