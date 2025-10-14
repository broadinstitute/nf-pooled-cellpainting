process CELLPROFILER_PREPROCESS {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(meta), path(corr_images, stageAs: "images/*")
    path preprocess_cppipe
    path barcodes, stageAs: "images/Barcodes.csv"
    path (plugins, stageAs: "plugins/*")


    output:
    tuple val(meta), path("*.tiff")                      , emit: preprocessed_images
    tuple val(meta), path("overlay/*.tiff")              , emit: overlay
    tuple val(meta), path("BarcodingPreprocessing*.csv") , emit: preprocess_stats
    path("barcoding_preprocessing.load_data.csv")        , emit: load_data_csv
    path "versions.yml"                                  , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    generate_load_data_csv.py \\
        --pipeline-type preprocess \\
        --images-dir ./images \\
        --output load_data.csv

    cellprofiler -c -r \\
        ${task.ext.args ?: ''} \\
        -p ${preprocess_cppipe} \\
        -o . \\
        --data-file=load_data.csv \\
        --image-directory ./images/ \\
        --plugins-directory=./plugins/

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        cellprofiler: \$(cellprofiler --version)
    END_VERSIONS
    """

    stub:
    """
    touch BarcodingPreprocess_Cells.csv
    touch BarcodingPreprocess_Experiment.csv
    touch BarcodingPreprocess_Image.csv
    touch BarcodingPreprocess_Nuclei.csv

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        cellprofiler: \$(cellprofiler --version)
    END_VERSIONS
    """
}
