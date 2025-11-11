# Troubleshooting

Common issues and solutions for the nf-pooled-cellpainting pipeline.

## Pipeline Execution Issues

### Pipeline Fails to Start

#### Symptom
```
ERROR ~ Error executing process > 'CELLPAINTING:CELLPROFILER_ILLUMCALC'
```

#### Causes & Solutions

**1. Missing required parameters**

Check all required parameters are provided:
```bash
nextflow run main.nf --help
```

Ensure you have:
- `--input`
- `--barcodes`
- `--outdir`
- All CellProfiler pipeline paths
- Plugin URLs

**2. Invalid samplesheet**

Validate CSV format:
```bash
head samplesheet.csv
# Should have headers: path,arm,batch,plate,well,channels,site,cycle,n_frames
```

**3. Nextflow version**

Update Nextflow:
```bash
nextflow self-update
nextflow -version  # Should be >= 23.04.0
```

### Processes Fail with "Cannot find file"

#### Symptom
```
ERROR ~ Error executing process > 'CELLPROFILER_ILLUMCALC'
Caused by:
  Process `CELLPROFILER_ILLUMCALC` terminated with an error exit status (1)
  Cannot find file: /path/to/images
```

#### Solutions

**1. Check file paths in samplesheet**

Ensure paths are:
- Absolute paths (recommended)
- Accessible from execution environment
- Point to directories containing images

```bash
# Test file accessibility
cat samplesheet.csv | tail -n +2 | cut -d',' -f1 | xargs -I {} ls {}
```

**2. Cloud storage authentication**

For S3/Azure/GCS paths, verify credentials:

```bash
# AWS
aws s3 ls s3://bucket/path/

# Azure
az storage blob list --account-name myaccount --container-name mycontainer

# Google Cloud
gsutil ls gs://bucket/path/
```

### Out of Memory Errors

#### Symptom
```
ERROR ~ Error executing process > 'CELLPROFILER_ILLUMCALC'
java.lang.OutOfMemoryError: Java heap space
```

or

```
CellProfiler: MemoryError: Unable to allocate array
```

#### Solutions

**1. Increase Java heap size**

```bash
export NXF_OPTS='-Xms2g -Xmx8g'
nextflow run main.nf ...
```

**2. Increase process memory**

Create `nextflow.config`:
```groovy
process {
    withName: 'CELLPROFILER_.*' {
        memory = { task.attempt == 1 ? 32.GB : 64.GB }
        errorStrategy = 'retry'
        maxRetries = 2
    }
}
```

**3. Reduce parallelization**

```groovy
executor {
    queueSize = 4  // Reduce concurrent tasks
}
```

**4. Process smaller batches**

Split samplesheet into smaller subsets and run separately.

### Work Directory Full

#### Symptom
```
ERROR ~ Error executing process > 'CELLPROFILER_ILLUMAPPLY'
No space left on device
```

#### Solutions

**1. Clean work directory**

```bash
# Remove failed task work directories
nextflow clean -f

# Keep only successful cached tasks
nextflow clean -f -k
```

**2. Change work directory**

```bash
nextflow run main.nf -w /path/to/large/disk/work ...
```

**3. Monitor disk usage**

```bash
df -h
du -sh work/
```

## CellProfiler Issues

### CellProfiler Process Fails

#### Symptom
```
CellProfiler: Error while processing ...
```

#### Solutions

**1. Check load_data.csv**

Examine generated CSV:
```bash
# Find work directory
ls -lrt work/*/*/

# Check CSV
cat work/a1/b2c3.../load_data.csv
```

Verify:
- Correct column names
- Valid file paths
- No missing values

**2. Test pipeline manually**

Extract and run CellProfiler directly:
```bash
cd work/<task-hash>/

cellprofiler \
    -c -r \
    -p pipeline.cppipe \
    --log-level=DEBUG \
    --data-file=load_data.csv
```

**3. Validate .cppipe file**

Open in CellProfiler GUI:
```bash
cellprofiler  # Opens GUI
# Load pipeline and check for errors
```

### Plugin Download Failures

#### Symptom
```
wget: unable to resolve host address
ERROR: Plugin 'callbarcodes' not found
```

#### Solutions

**1. Check URL accessibility**

```bash
curl -I https://example.com/callbarcodes.py
```

**2. Use local files**

Download plugins locally:
```bash
wget -O plugins/callbarcodes.py https://example.com/callbarcodes.py
```

Update parameters:
```bash
--callbarcodes_plugin file:$PWD/plugins/callbarcodes.py
```

**3. Check network connectivity**

Ensure compute environment can access external URLs.

### Illumination Correction Issues

#### Symptom

Corrected images look wrong or unchanged.

#### Solutions

**1. Verify illumination functions**

Check `.npy` files exist and are non-empty:
```bash
ls -lh results/painting/illum/batch1/P001/*.npy
```

Load and inspect:
```python
import numpy as np
import matplotlib.pyplot as plt

illum = np.load('P001_IllumDAPI.npy')
plt.imshow(illum)
plt.colorbar()
plt.show()
```

**2. Check pipeline configuration**

Ensure `illumapply` pipeline:
- Loads illumination functions correctly
- Applies correction formula (usually divide or subtract)
- Saves corrected output

## QC Gate Issues

### Pipeline Stops Before Stitching

#### Symptom

No stitched outputs despite successful execution.

#### Solution

This is expected behavior! Enable QC gates after manual review:

```bash
nextflow run main.nf \
    ... \
    --qc_painting_passed true \
    --qc_barcoding_passed true \
    -resume
```

### QC Metrics Don't Match Expectations

#### Barcode Alignment Fails QC

**Symptom**: High pixel shifts or low correlations

**Solutions**:

1. **Adjust thresholds**:
```bash
--barcoding_shift_threshold 100  # Increase from 50
--barcoding_corr_threshold 0.8   # Decrease from 0.9
```

2. **Inspect QC outputs**:
```bash
open results/qc/barcode_align/batch1/P001/qc_report.html
```

3. **Check imaging quality**: May indicate stage drift or focus issues.

## Container Issues

### Docker Permission Denied

#### Symptom
```
ERROR ~ Error executing process > 'CELLPROFILER_ILLUMCALC'
docker: Got permission denied while trying to connect to the Docker daemon socket
```

#### Solutions

**1. Add user to docker group**

```bash
sudo usermod -aG docker $USER
newgrp docker
```

**2. Use Docker sudo**

```groovy
docker {
    enabled = true
    sudo = true
}
```

**3. Switch to Singularity**

```bash
nextflow run main.nf -profile singularity ...
```

### Container Image Pull Failures

#### Symptom
```
ERROR ~ Failed to pull Docker image 'wave.seqera.io/cellprofiler/cellprofiler:4.2.8'
```

#### Solutions

**1. Check network connectivity**

```bash
docker pull wave.seqera.io/cellprofiler/cellprofiler:4.2.8
```

**2. Use alternative registry**

```groovy
process {
    container = 'docker.io/cellprofiler/cellprofiler:4.2.8'
}
```

**3. Pre-pull images**

```bash
docker pull wave.seqera.io/cellprofiler/cellprofiler:4.2.8
docker pull fiji/fiji:20220415
```

## Performance Issues

### Pipeline Runs Slowly

#### Causes & Solutions

**1. Insufficient parallelization**

Increase concurrent tasks:
```groovy
executor {
    queueSize = 20
}
```

**2. Over-allocation**

Too many parallel tasks can cause thrashing. Monitor and adjust:
```bash
htop  # Watch CPU and memory
```

**3. I/O bottleneck**

Use local SSD for work directory:
```bash
nextflow run main.nf -w /fast/local/disk/work ...
```

**4. Network latency**

For cloud storage, ensure compute is in same region:
```groovy
aws {
    region = 'us-east-1'  # Match S3 bucket region
}
```

### Tasks Timeout

#### Symptom
```
ERROR ~ Error executing process > 'CELLPROFILER_ILLUMCALC'
Execution cancelled -- Execution time limit exceeded
```

#### Solution

Increase time limit:
```groovy
process {
    withName: 'CELLPROFILER_ILLUMCALC' {
        time = 12.h  // Increase from default
    }
}
```

## Output Issues

### Missing Output Files

#### Symptom

Expected files not in `results/`.

#### Solutions

**1. Check publishDir configuration**

Verify publish settings in process:
```groovy
publishDir "${params.outdir}/painting/corrected", mode: 'copy'
```

**2. Check process completion**

Ensure process succeeded:
```bash
grep -r "Completed" .nextflow.log | grep ILLUMCALC
```

**3. Check work directory**

Files may be in work directory:
```bash
find work/ -name "*.tif" | head
```

### Incorrect Output Organization

#### Symptom

Files not organized as expected.

#### Solution

Verify metadata is correctly parsed:
```groovy
// Check samplesheet parsing
cat .nextflow.log | grep "Metadata:"
```

Ensure grouping keys match expectations in subworkflows.

## Seqera Platform Issues

### Authentication Failures

#### Symptom
```
ERROR ~ Unable to authenticate to Seqera Platform
```

#### Solutions

```bash
# Configure credentials
tw login

# Verify authentication
tw info
```

### Compute Environment Errors

#### Symptom

Jobs not launching in cloud/HPC.

#### Solutions

**1. Verify compute environment**

Check Seqera Platform dashboard:
- Compute environment status
- Credentials validity
- Resource limits

**2. Check queue configuration**

```groovy
process {
    queue = 'default'  // Verify queue name
    clusterOptions = '--account=myaccount'
}
```

**3. Review logs in Seqera Platform**

Navigate to run → Tasks → Select failed task → View logs

## Data Issues

### Metadata Mismatches

#### Symptom

Files not grouping correctly.

#### Solutions

**1. Validate samplesheet**

```python
import pandas as pd

df = pd.read_csv('samplesheet.csv')

# Check for duplicates
duplicates = df[df.duplicated(subset=['batch', 'plate', 'well', 'site', 'cycle'], keep=False)]
print(duplicates)

# Check for missing values
print(df.isnull().sum())
```

**2. Verify filename patterns**

Ensure filenames match expected pattern:
```
{plate}_{well}_{site}_{frame}_{channel}.tif
```

### Image Format Issues

#### Symptom

CellProfiler can't read images.

#### Solutions

**1. Validate TIFF format**

```python
from PIL import Image

img = Image.open('test.tif')
print(img.format, img.size, img.mode)
```

**2. Convert incompatible formats**

```python
from PIL import Image
import numpy as np

# Load and convert
img = Image.open('input.png')
img_array = np.array(img)

# Save as 16-bit TIFF
Image.fromarray(img_array.astype('uint16')).save('output.tif')
```

## Getting Help

### Collect Diagnostic Information

```bash
# Nextflow version
nextflow -version

# Container versions
docker --version
singularity --version

# Check logs
tail -100 .nextflow.log

# Execution report
nextflow run main.nf -with-report report.html
```

### Report an Issue

When reporting issues, include:

1. **Nextflow version**: `nextflow -version`
2. **Command used**: Full `nextflow run` command
3. **Error message**: From `.nextflow.log`
4. **Work directory**: Relevant files from `work/<task-hash>/`
5. **Configuration**: Custom `nextflow.config` if any

## Additional Resources

- [Nextflow Documentation](https://www.nextflow.io/docs/latest/)
- [CellProfiler Forum](https://forum.image.sc/tag/cellprofiler)
- [nf-core Guidelines](https://nf-co.re/docs/)
- [Seqera Platform Docs](https://docs.seqera.io/)

## Next Steps

- [Parameters](../usage/parameters.md) - Adjust pipeline configuration
- [Architecture](../developer/architecture.md) - Understand pipeline internals
- [Testing](../developer/testing.md) - Test your changes
