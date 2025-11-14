process CELLPROFILER_ILLUMAPPLY {
    tag "${meta.id}"
    label 'cellprofiler_basic'

    conda "${moduleDir}/environment.yml"
    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(meta), val(channels), val(cycles), path(images, stageAs: "images/img*/*"), val(image_metas), path(npy_files, stageAs: "images/*")
    path illumination_apply_cppipe
    val has_cycles

    output:
    tuple val(meta), path("*.tiff"), path("*.csv"), emit: corrected_images
    path "load_data.csv", emit: load_data_csv
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    // Build optional JSON fields
    // Use "cycles" (plural) if it's a list, "cycle" (singular) if it's a single value
    def cycle_json = ""
    if (cycles instanceof List) {
        // Convert list to JSON array format
        def cycles_str = cycles.collect { it.toString() }.join(', ')
        cycle_json = "\"cycles\": [${cycles_str}],"
    }
    else if (cycles) {
        cycle_json = "\"cycle\": ${cycles},"
    }
    def batch_json = meta.batch ? "\"batch\": \"${meta.batch}\"," : ""
    def arm_json = meta.arm ? "\"arm\": \"${meta.arm}\"," : ""
    // Build image_metadata array with well+site+filename for each image
    def image_metadata_json = image_metas
        .collect { m ->
            def fname = m.filename ?: 'MISSING'
            def cycle_field = m.cycle ? ", \"cycle\": ${m.cycle}" : ""
            "        {\"well\": \"${m.well}\", \"site\": ${m.site}, \"filename\": \"${fname}\"${cycle_field}}"
        }
        .join(',\n')
    """
    # Create metadata JSON file (force overwrite with >| to handle noclobber)
    cat >| metadata.json << 'EOF'
{
    "plate": "${meta.plate}",
    ${cycle_json}
    ${batch_json}
    ${arm_json}
    "channels": "${channels}",
    "id": "${meta.id}",
    "image_metadata": [
${image_metadata_json}
    ]
}
EOF

    # Generate load_data.csv
    generate_load_data_csv.py \\
        --pipeline-type illumapply \\
        --images-dir ./images \\
        --illum-dir ./images \\
        --output load_data.csv \\
        --metadata-json metadata.json \\
        --channels "${channels}" \\
        ${has_cycles ? '--has-cycles' : ''}

    cellprofiler -c -r \\
        -p ${illumination_apply_cppipe} \\
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
    touch Plate_${meta.plate}_Well_${meta.well}_Site_${meta.site}_CorrPhalloidin.tiff
    touch PaintingIllumApplication_Cells.csv
    touch PaintingIllumApplication_ConfluentRegions.csv
    touch PaintingIllumApplication_Experiment.csv
    touch PaintingIllumApplication_Image.csv
    touch PaintingIllumApplication_Nuclei.csv

    cat <<-END_VERSIONS > versions.yml
	"${task.process}":
	    cellprofiler: \$(cellprofiler --version)
	END_VERSIONS
    """
}
