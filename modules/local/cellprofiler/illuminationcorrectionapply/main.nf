process CELLPROFILER_ILLUMINATIONCORRECTIONAPPLY {
    tag "${meta.id}"
    label 'process_medium'

    conda "${moduleDir}/environment.yml"
    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'https://depot.galaxyproject.org/singularity/cellprofiler:4.2.8--pyhdfd78af_0'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(meta), val(channels), path(images, stageAs: "images/*"), path(npy_files,stageAs: "images/*"), path(load_data_csv)
    path illumination_apply_cppipe

    output:
    tuple val(meta), path("images_corrected/*.tiff"), path("images_corrected/*.csv"), emit: corrected_images
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    mkdir -p images_corrected

    cellprofiler -c -r \
        ${task.ext.args ?: ''} \
        -p ${illumination_apply_cppipe} \
        -o images_corrected \
        --data-file=${load_data_csv} \
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
    
    touch ${prefix}.bam

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        cellprofiler: \$(cellprofiler --version)
    END_VERSIONS
    """
}
