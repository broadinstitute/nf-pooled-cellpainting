# Troubleshooting

## Load Data CSV Errors

**Symptom**: CellProfiler fails with "Unable to load image"

**Solution**: Validate CSV paths are accessible:

```bash
# Check CSV format
head load_data.csv

# Verify image paths exist
cat load_data.csv | cut -d',' -f5 | xargs -I {} test -f {} && echo "OK"
```

## Plugin Not Found

**Symptom**: "Plugin 'callbarcodes' not found"

**Solution**: Ensure plugin URL is accessible and pipeline has access to the internet if plugin is loaded from an online source.

## Memory Errors

**Symptom**: CellProfiler crashes with out-of-memory. Exit code 137 means that a process failed from insufficient memory.

**Solution**: Increase process memory or reduce image size.

To reduce image sizes for steps 1-3 or 5-7 (all of the CellProfiler steps before the final Analysis pipeline), image size needs to be reduced before the Nextflow pipeline is triggered. Create a pipeline (CellProfiler, FIJI, Python, or otherwise) to rescale or crop your images and then adjust your samplesheet to point to the smaller images as input. To reduce image sizes for step 9 (the final Analysis pipeline), change the image scale/crop parameters that are passed to steps 4 and 8. Specifically, increasing `tileperside` will reduce image size because the whole-well stitch will be cropped into more, smaller images.

To increase process memory, you can edit the `nextflow.config` file. Alternatively, in Seqera Platform, in the Launchpad, in the 3) Advanced settings tab, under **Advanced options** you can add in process information that will supercede configuration defined elsewhere. (See Nextflow documentation for more on [configuration order of priority](https://docs.seqera.io/platform-cloud/launch/advanced#nextflow-config-file).) e.g.

```groovy
process {
    withName: 'POOLED_CELLPAINTING:BARCODING:CELLPROFILER_ILLUMAPPLY_BARCODING' {
        memory = 4.GB
        cpus = 2
    }
}
```

## Missing Images

**Symptom**: CSV has fewer rows than expected

**Solution**: Check filename patterns match exactly:

```bash
ls test_images/ | grep -E "P[0-9]+_[A-Z][0-9]+_[0-9]+_[0-9]+_.*\.tif"
```

## Metadata Mismatches

**Symptom**: CellProfiler can't group images properly

**Solution**: Ensure metadata columns are populated correctly:

```python
df[['Metadata_Plate', 'Metadata_Well', 'Metadata_Site']].drop_duplicates()
```

## Changes to the Nextflow codebase are not reflected in your Seqera Platform run

**Symptom**: A resumed or relaunched pipeline does not include changes made to the Nextflow workflow codebase since the last launch.

![Seqera Platform settings for using latest commit](image/use_latest_commits.png)

**Solution**: In Seqera Platform, in the Launchpad, in the 1) General config tab, under **Run setup**, make sure that `Revision` is pointing to the branch that you are working off of and not a specific commit. Make sure that `Pull latest` is set to True (toggle is to the right and shows blue).

## Cant run multiple subsets of wells/images from single plate

**Symptom**: Triggering independent runs using separate subsets of wells/images from a single plate makes it so that runs cannot be resumed but instead start from the beginning.

**Solution**: You cannot process two separate subsets of wells/images from a single plate in independent runs because there are some files that are created on a per-plate basis (e.g. illum .npy files). Therefore the output of one workflow trigger will overwrite the output of the other and since files are overwritten, Nextflow starts the workflow over upon resumption. To get around this, you must use different "Plate" metadata in your samplesheet (e.g. Plate1_subset1 in one samplesheet and Plate1_subset2 in the other samplesheet instead of just Plate1 in both samplesheets).

## Local run fails to pull Docker on a Mac

**Symptom**: You are running a local run on a Mac and get an error like:

```
Command error:
  Unable to find image 'cellprofiler/distributed-fiji:fusion-v0.1.0' locally
  fusion-v0.1.0: Pulling from cellprofiler/distributed-fiji
  docker: no matching manifest for linux/arm64/v8 in the manifest list entries
```

**Solution**: Add `containerOptions = '--platform linux/amd64'` to your config for the process that is failing to pull the Docker. e.g.

```
process {
    withName: 'POOLED_CELLPAINTING:BARCODING:FIJI_STITCHCROP' {
        cpus   = { 1 * task.attempt }
        memory = { 10.GB * task.attempt }
        containerOptions = '--platform linux/amd64'
    }
}
```
