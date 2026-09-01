process CELLPROFILER_ILLUMAPPLY {
    tag "${meta.id}"
    label 'cellprofiler_large'

    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(meta), val(channels), val(cycles), path(images, stageAs: "images/img?/*"), val(image_metas), path(npy_files, stageAs: "images/")
    path illumination_apply_cppipe
    val has_cycles

    output:
    tuple val(meta), path("*.tiff"), path("*.csv"), emit: corrected_images
    tuple val(meta), path("*.png"), emit: qc_images, optional: true
    tuple val(meta), path("load_data.csv"), emit: load_data_csv
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    // Serialize image metadata directly - it already contains all fields (plate, well, site, channels, filename, etc.)
    // Base64 encode to reduce log verbosity
    def metadata_json_content = groovy.json.JsonOutput.toJson(image_metas)
    def metadata_base64 = metadata_json_content.bytes.encodeBase64().toString()
    def staged_list_base64 = images.toString().bytes.encodeBase64().toString()

    """
    # Create metadata JSON file from base64 (reduces log verbosity)
    echo '${metadata_base64}' | base64 -d > metadata.json
    echo '${staged_list_base64}' | base64 -d > staged_list.txt
    # Replace the metadata with staged paths instead - matched by basename, not
    # list position (list order between the Groovy-built metadata and Nextflow's
    # actual staged-file order are not guaranteed to match - a prior index-based
    # version of this silently mismatched channel labels for large "well"-mode
    # illumapply calls bundling hundreds of images in one invocation).

    python3 -c "
import json
import os
import sys

with open('metadata.json') as f:
    metadata = json.load(f)
with open('staged_list.txt') as f:
    staged_list = f.read()

staged_list = staged_list.split(' ')

# Two different physical files can share a basename (e.g. Phenix filenames
# reuse the same ch{N} index across different acquisition 'round'
# subfolders), so basename alone can't disambiguate them. Nextflow stages
# each file as a symlink back to its real source path, and every metadata
# entry already records that same absolute path as original_path - resolve
# each staged symlink's target and match on that instead, falling back to
# basename matching only if the staged copy isn't a symlink (e.g. a
# stageInMode: copy environment), preserving today's behavior there.
staged_by_realpath = {}
staged_by_basename = {}
for s in staged_list:
    rel = os.path.sep.join(s.split(os.path.sep)[1:])
    staged_by_basename.setdefault(s.split(os.path.sep)[-1], rel)
    real = os.path.realpath(s)
    if real != os.path.abspath(s):
        staged_by_realpath[real] = rel

missing = []
for entry in metadata:
    staged_path = None
    original_path = entry.get('original_path')
    if original_path:
        staged_path = staged_by_realpath.get(os.path.realpath(original_path))
    if staged_path is None:
        staged_path = staged_by_basename.get(entry['filename'])
    if staged_path is None:
        missing.append(entry['filename'])
    else:
        entry['filename'] = staged_path

if missing:
    print(f'Error: {len(missing)} metadata entries have no matching staged file, e.g. {missing[:10]}', file=sys.stderr)
    sys.exit(1)

with open('metadata.json','w') as f:
    json.dump(metadata,f)
"

    # Generate load_data.csv
    generate_load_data_csv.py \\
        --pipeline-type illumapply \\
        --images-dir ./images \\
        --illum-dir ./images \\
        --output load_data.csv \\
        --metadata-json metadata.json \\
        --channels "${channels}" \\
        --cycle-metadata-name "${params.cycle_metadata_name}" \\
        --outdir "${params.outdir}" \\
        ${has_cycles ? '--has-cycles' : ''}

    # Patch Base image location to use Default Input Folder (staged images)
    # We need to copy the input file to a writable file first if it's a symlink or read-only
    cp -L ${illumination_apply_cppipe} illumination_apply_patched.cppipe
    sed -i 's/Base image location:None|/Base image location:Default Input Folder|/g' illumination_apply_patched.cppipe

    cellprofiler -c -r \\
        -p illumination_apply_patched.cppipe \\
        -o . \\
        --data-file=load_data.csv \\
        --image-directory ./images/

    cat <<-END_VERSIONS > versions.yml
	"${task.process}":
	    cellprofiler: \$(cellprofiler --version)
	END_VERSIONS
    """

    stub:
    // For barcoding (has_cycles=true): create files with _Cycle pattern that downstream regex expects
    // For painting (has_cycles=false): create painting-style files
    def stub_files = has_cycles
        ? """
        touch load_data.csv
        touch Plate_${meta.plate}_Well_${meta.well}_Site_${meta.site ?: 1}_Cycle01_DNA.tiff
        touch Plate_${meta.plate}_Well_${meta.well}_Site_${meta.site ?: 1}_Cycle01_A.tiff
        touch BarcodingIllumApplication_Cells.csv
        touch BarcodingIllumApplication_ConfluentRegions.csv
        touch BarcodingIllumApplication_Experiment.csv
        touch BarcodingIllumApplication_Image.csv
        touch BarcodingIllumApplication_Nuclei.csv
        """
        : """
        touch load_data.csv
        touch Plate_${meta.plate}_Well_${meta.well}_Site_${meta.site ?: 1}_CorrPhalloidin.tiff
        touch PaintingIllumApplication_Cells.csv
        touch PaintingIllumApplication_ConfluentRegions.csv
        touch PaintingIllumApplication_Experiment.csv
        touch PaintingIllumApplication_Image.csv
        touch PaintingIllumApplication_Nuclei.csv
        """
    """
    ${stub_files}

    cat <<-END_VERSIONS > versions.yml
	"${task.process}":
	    cellprofiler: \$(cellprofiler --version)
	END_VERSIONS
    """
}
