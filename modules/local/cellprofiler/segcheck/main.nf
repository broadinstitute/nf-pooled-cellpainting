process CELLPROFILER_SEGCHECK {
    tag "$meta.id"
    label 'cellprofiler_basic'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92':
        'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f' }"

    input:
    tuple val(meta), path(corr_images, stageAs: "images/*"), val(image_metas)
    path segcheck_cppipe
    val range_skip


    output:
    tuple val(meta), path("*.csv"), path("*.png"), emit: segcheck_res
    path "load_data.csv"                         , emit: load_data_csv
    path "versions.yml"                          , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    // Build optional JSON fields
    def batch_json = meta.batch ? "\"batch\": \"${meta.batch}\"," : ""
    def arm_json = meta.arm ? "\"arm\": \"${meta.arm}\"," : ""
    def channels_json = meta.channels ? "\"channels\": \"${meta.channels}\"," : ""
    // Build image_metadata array with well+site+filename+channel for each image
    def image_metadata_json = image_metas.collect { m ->
        def fname = m.filename ?: 'MISSING'
        def channel = m.channel ?: 'UNKNOWN'
        "        {\"well\": \"${m.well}\", \"site\": ${m.site}, \"filename\": \"${fname}\", \"channel\": \"${channel}\"}"
    }.join(',\n')
    """
    # Create metadata JSON file (force overwrite with >| to handle noclobber)
    cat >| metadata.json << 'EOF'
{
    "plate": "${meta.plate}",
    ${batch_json}
    ${arm_json}
    ${channels_json}
    "id": "${meta.id}",
    "image_metadata": [
${image_metadata_json}
    ]
}
EOF

    # Generate load_data.csv
    generate_load_data_csv.py \\
        --pipeline-type segcheck \\
        --images-dir ./images \\
        --output load_data.csv \\
        --metadata-json metadata.json \\
        --range-skip ${range_skip}

    cellprofiler -c -r \\
        ${task.ext.args ?: ''} \\
        -p ${segcheck_cppipe} \\
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
    touch image1.png
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
