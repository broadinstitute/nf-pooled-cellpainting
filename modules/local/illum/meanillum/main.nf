process ILLUM_MEANILLUM {
    tag "${meta.id}"
    label 'qc'

    container "community.wave.seqera.io/library/numpy_python_pip_pillow:74310e9b76ff61b6"

    input:
    tuple val(meta), path(npy_files, stageAs: "well?/*")

    output:
    tuple val(meta), path("*.npy"), emit: illumination_corrections
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    mean_illum.py . --outdir .

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        numpy: \$(python -c "import numpy; print(numpy.__version__)")
    END_VERSIONS
    """

    stub:
    // Cycle-prefixed like CELLPROFILER_ILLUMCALC's stub, so barcoding's
    // per-cycle tasks (grouped back together downstream by plate only) don't
    // collide on an identical stub filename.
    def cycle_prefix = meta.cycle ? "${meta.cycle}_" : ""
    """
    touch ${meta.plate}_${cycle_prefix}Illum.npy

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        numpy: \$(python -c "import numpy; print(numpy.__version__)")
    END_VERSIONS
    """
}
