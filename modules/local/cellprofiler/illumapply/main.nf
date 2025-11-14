process CELLPROFILER_ILLUMAPPLY {
    tag "${meta.id}"
    label 'cellprofiler_basic'

    conda "${moduleDir}/environment.yml"
    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(meta), val(channels), val(cycles), path(images, stageAs: "images/img?/*"), val(image_metas), path(npy_files, stageAs: "images/*")
    path illumination_apply_cppipe
    val has_cycles

    output:
    tuple val(meta), path("*.tiff"), path("*.csv"), emit: corrected_images
    path "load_data.csv", emit: load_data_csv
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    // Serialize image metadata directly - it already contains all fields (plate, well, site, channels, filename, etc.)
    def metadata_json = groovy.json.JsonOutput.toJson(image_metas)

    """
    # Create metadata JSON file
    cat > metadata.json << 'EOF'
${metadata_json}
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
