process QC_MONTAGEILLUM {
    tag "${meta.plate}"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "community.wave.seqera.io/library/python_loguru_matplotlib_numpy_typer:9378cf9abd25cf72"

    input:
    tuple val(meta), path(npy_files)

    output:
    tuple val(meta), path("*.png"), emit: illum_montage
    path "versions.yml"                 , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args = task.ext.args ?: ''
    """
    qc_illum_montage.py \\
        $args \\
        . \\
        ${meta.arm}.${meta.batch}_${meta.plate}.montage.png \\
        ${meta.arm} \\
        ${meta.plate} \\
        --auto-channels

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        qc_illum_montage: 0.1.0
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
