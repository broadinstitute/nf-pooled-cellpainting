process CELLPROFILER_SEGCHECK {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(meta), val(channels), path(sub_corr_images, stageAs: "images/*"), path(load_data_csv)
    path segcheck_cppipe


    output:
    tuple val(meta), path("*.csv"), path("*.png"), emit: segcheck_res
    path "versions.yml"                          , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    generate_load_data_csv_v2.py \
        --pipeline 3 \
        --base-path . \
        --output-dir . 

    cellprofiler -c -r \\
        ${task.ext.args ?: ''} \\
        -p ${segcheck_cppipe} \\
        -o . \\
        --data-file=${load_data_csv} \\
        --image-directory ./images/

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        cellprofiler: \$(cellprofiler --version)
    END_VERSIONS
    """

    stub:
    """
    echo $args
    
    touch test.txt

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        cellprofiler: \$(cellprofiler --version)
    END_VERSIONS
    """
}
