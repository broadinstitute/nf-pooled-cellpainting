process CELLPROFILER_SEGCHECK {
    tag "${meta.id}"
    label 'cellprofiler_basic'

    conda "${moduleDir}/environment.yml"
    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(meta), path(corr_images, stageAs: "images/"), val(image_metas)
    path segcheck_cppipe
    val range_skip

    output:
    tuple val(meta), path("*.csv"), path("*.png"), emit: segcheck_res
    path "load_data.csv", emit: load_data_csv
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    // Serialize image metadata directly - it already contains all fields (plate, well, site, channels, filename, etc.)
    // Base64 encode to reduce log verbosity
    def metadata_json_content = groovy.json.JsonOutput.toJson(image_metas)
    def metadata_base64 = metadata_json_content.bytes.encodeBase64().toString()

    """
    # Create metadata JSON file from base64 (reduces log verbosity)
    echo '${metadata_base64}' | base64 -d > metadata.json

    # Generate load_data.csv
    generate_load_data_csv.py \\
        --pipeline-type segcheck \\
        --images-dir ./images \\
        --output load_data.csv \\
        --metadata-json metadata.json \\
        --range-skip ${range_skip} \\
        --cycle-metadata-name "${params.cycle_metadata_name}"

    # Patch Base image location to use Default Input Folder (staged images)
    cp -L ${segcheck_cppipe} segcheck_patched.cppipe
    sed -i 's/Base image location:None|/Base image location:Default Input Folder|/g' segcheck_patched.cppipe

    cellprofiler -c -r \\
        ${task.ext.args ?: ''} \\
        -p segcheck_patched.cppipe \\
        -o . \\
        --data-file=load_data.csv \\
        --image-directory ./images/

    cat <<-END_VERSIONS > versions.yml
	"${task.process}":
	    cellprofiler: \$(cellprofiler --version)
	END_VERSIONS
    """

    stub:
    """
    touch load_data.csv
    touch ${meta.id}_image1.png
    touch SegmentationCheck_Cells.csv
    touch SegmentationCheck_ConfluentRegions.csv
    touch SegmentationCheck_Experiment.csv
    touch SegmentationCheck_Image.csv
    touch SegmentationCheck_Nuclei.csv
    touch SegmentationCheck_PreCells.csv

    cat <<-END_VERSIONS > versions.yml
	"${task.process}":
	    cellprofiler: \$(cellprofiler --version)
	END_VERSIONS
    """
}
