process GENERATE_LOAD_DATA_CSV {
    tag "pipeline_${pipeline_numbers}"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "community.wave.seqera.io/library/pandas:2.3.3--5a902bf824a79745"

    input:
    path(samplesheet)
    val(pipeline_numbers)
    val(range_skip)

    output:
    path("load_data_*.csv"), emit: load_data_csv
    path "versions.yml"    , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    generate_load_data_csv.py ${samplesheet} \
        --base-path . \
        --output-dir . \
        --pipeline ${pipeline_numbers} \
        --split-by batch,plate,well\
        --range-skip ${range_skip} 

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        generate_load_data_csv.py: 0.1.0
    END_VERSIONS
    """

    stub:
    def args = task.ext.args ?: ''
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    echo $args



    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        generate_load_data_csv.py: 0.1.0
    END_VERSIONS
    """
}
