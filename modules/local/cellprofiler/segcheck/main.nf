process CELLPROFILER_SEGCHECK {
    tag "${meta.id}"
    label 'cellprofiler_basic'

    container "${
        params.cellprofiler_container_override ?:
        (params.cellprofiler_flavor == 'default' && workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
            ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
            : params.cellprofiler_flavor_containers[params.cellprofiler_flavor])
    }"

    input:
    tuple val(meta), path(corr_images, stageAs: "images/"), val(image_metas)
    path segcheck_cppipe
    val range_skip
    // stage to root to prevent collision with image file staging
    path plugins, stageAs: "plugins/"

    output:
    tuple val(meta), path("*.csv"), path("*.png"), emit: segcheck_res
    tuple val(meta), path("load_data.csv"), emit: load_data_csv
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
        --images-dir ./images \\
        --output load_data.csv \\
        --metadata-json metadata.json \\
        --range-skip ${range_skip} \\
        --cycle-metadata-name "${params.cycle_metadata_name}"

    # Patch Base image location to use Default Input Folder (staged images)
    cp -L ${segcheck_cppipe} segcheck_patched.cppipe
    sed -i 's/Base image location:None|/Base image location:Default Input Folder|/g' segcheck_patched.cppipe

    # Set writable cache directories for CellProfiler and dependencies (the container runs as the
    # host UID/GID, so the default homedir-based paths aren't writable).
    export MPLCONFIGDIR="\${PWD}/.matplotlib"
    export HOME="\${PWD}"
    export XDG_CACHE_HOME="\${PWD}/.cache"
    # Cellpose's numba JIT tries to cache compiled code next to the installed package files,
    # which aren't writable when the container runs as the host UID/GID; redirect to a writable dir.
    export NUMBA_CACHE_DIR="\${PWD}/.numba_cache"
    mkdir -p "\$MPLCONFIGDIR" "\$XDG_CACHE_HOME" "\$NUMBA_CACHE_DIR"

    cellprofiler -c -r \\
        ${task.ext.args ?: ''} \\
        -p segcheck_patched.cppipe \\
        -o . \\
        --data-file=load_data.csv \\
        --image-directory ./images/ \\
        --plugins-directory=./plugins/

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
