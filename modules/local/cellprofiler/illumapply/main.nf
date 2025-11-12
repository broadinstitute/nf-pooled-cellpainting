process CELLPROFILER_ILLUMAPPLY {
    tag "${meta.id}"
    label 'process_medium'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92':
        'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f' }"

    input:
    tuple val(meta), val(channels), val(cycles), path(images, stageAs: "images/img*/*"), path(npy_files, stageAs: "images/*")
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
    def cycle_json = meta.cycle ? "\"cycle\": ${meta.cycle}," : ""
    def batch_json = meta.batch ? "\"batch\": \"${meta.batch}\"," : ""
    def arm_json = meta.arm ? "\"arm\": \"${meta.arm}\"," : ""
    // NOTE: Don't include site for ILLUMAPPLY - it processes multiple sites per well
    // and needs to discover them from filenames
    """
    cat << EOF > metadata.json
{
    "plate": "${meta.plate}",
    "well": "${meta.well}",
    ${cycle_json}
    ${batch_json}
    ${arm_json}
    "channels": "${channels}",
    "id": "${meta.id}"
}
EOF

    generate_load_data_csv.py \\
        --pipeline-type illumapply \\
        --images-dir ./images \\
        --illum-dir ./images \\
        --output load_data.csv \\
        --channels "${channels}" \\
        --metadata-json metadata.json

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
