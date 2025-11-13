process QC_MONTAGEILLUM {
    tag "${meta.plate}"
    label 'qc'

    conda "${moduleDir}/environment.yml"
    container "community.wave.seqera.io/library/numpy_python_pip_pillow:74310e9b76ff61b6"

    input:
    tuple val(meta), path(input_files)
    val(pattern)

    output:
    tuple val(meta), path("*.png")      , emit: montage
    path "versions.yml"                 , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args = task.ext.args ?: ''
    def output_name = "${meta.arm}.${meta.batch}_${meta.plate}.montage.png"
    """
    montage.py \\
        $args \\
        . \\
        ${output_name} \\
        --pattern "${pattern}"

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        qc_montage: 0.1.0
    END_VERSIONS
    """

    stub:
    def args = task.ext.args ?: ''
    """
    echo $args

    touch montage.png

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        qc_illum_montage: 0.1.0
    END_VERSIONS
    """
}
