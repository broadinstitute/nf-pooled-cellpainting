process QC_CHECKDUPLICATEIMAGES {
    tag "${meta.batch}_${meta.plate}"
    label 'qc'

    container "community.wave.seqera.io/library/numpy_python_pip_pillow:74310e9b76ff61b6"

    input:
    tuple val(meta), path(image_files, stageAs: 'input_?/*')

    output:
    tuple val(meta), path("*_duplicate_check.txt"), emit: report
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def prefix = "${meta.batch}_${meta.plate}"
    """
    check_duplicate_images.py . --report ${prefix}_duplicate_check.txt

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        qc_check_duplicate_images: 0.1.0
    END_VERSIONS
    """

    stub:
    def prefix = "${meta.batch}_${meta.plate}"
    """
    touch ${prefix}_duplicate_check.txt

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        qc_check_duplicate_images: 0.1.0
    END_VERSIONS
    """
}
