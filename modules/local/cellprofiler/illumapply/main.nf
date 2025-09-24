process CELLPROFILER_ILLUMAPPLY {
    tag "${meta.id}"
    label 'process_medium'

    conda "${moduleDir}/environment.yml"
    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(meta), path(images, stageAs: "images/img*/*"), path(npy_files, stageAs: "images/*"), path(load_data_csv)
    path illumination_apply_cppipe

    output:
    tuple val(meta), path("*.tiff"), path("*.csv"), emit: corrected_images
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    cellprofiler -c -r \\
        ${task.ext.args ?: ''} \\
        -p ${illumination_apply_cppipe} \\
        -o . \\
        --data-file=${load_data_csv} \\
        --image-directory ./images/

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        cellprofiler: \$(cellprofiler --version)
    END_VERSIONS
    """

    stub:
    def args = task.ext.args ?: ''
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    echo $args
    
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
