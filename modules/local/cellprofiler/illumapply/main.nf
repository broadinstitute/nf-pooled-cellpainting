process CELLPROFILER_ILLUMAPPLY {
    tag "${group_meta.id}"
    label 'process_medium'

    conda "${moduleDir}/environment.yml"
    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'https://depot.galaxyproject.org/singularity/cellprofiler:4.2.8--pyhdfd78af_0'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(group_meta), path(images, stageAs: "images/*"), path(npy_files, stageAs: "images/*"), path(load_data_csv)
    path illumination_apply_cppipe

    output:
    tuple val(group_meta), path("*.tiff"), path("*.csv"), emit: corrected_images
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """

    cellprofiler -c -r \
        ${task.ext.args ?: ''} \
        -p ${illumination_apply_cppipe} \
        -o . \
        --data-file=${load_data_csv} \
        --image-directory ./images/

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        cellprofiler: \$(cellprofiler --version)
    END_VERSIONS
    """

    stub:
    def args = task.ext.args ?: ''
    def prefix = task.ext.prefix ?: "${group_meta.id}"
    """
    echo $args
    
    touch ${prefix}_corrected_image.tiff
    touch ${prefix}_load_data.csv

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        cellprofiler: \$(cellprofiler --version)
    END_VERSIONS
    """
}
