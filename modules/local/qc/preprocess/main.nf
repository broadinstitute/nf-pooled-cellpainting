process QC_PREPROCESS {
    tag "$meta.id"
    label 'qc'

    conda "${moduleDir}/environment.yml"
    container 'community.wave.seqera.io/library/ipykernel_jupytext_nbconvert_pandas_pruned:c397cee54f4ab064'

    input:
    tuple val(meta), val(wells), path(csv_files, stageAs: 'input_?/*'), val(num_cycles)
    path qc_preprocess_script
    path barcode_library
    val rows
    val columns

    output:
    tuple val(meta), path("*_qc_barcode_preprocess.ipynb"), emit: notebook
    tuple val(meta), path("*.html") , emit: html_report
        path "*.png", emit: png_reports
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def prefix = task.ext.prefix ?: "${meta.id}"
    def wells_list = wells.collect { well -> "'${well}'" }.join(' ')
    def rows_param = rows ? "-p rows ${rows}" : ""
    def columns_param = columns ? "-p columns ${columns}" : ""
    """
    # Organize CSV files by well in subdirectories
    mkdir -p analysis_input

    # Create arrays from the inputs
    wells=(${wells_list})

    # The CSV files are staged in numbered directories (input_1, input_2, etc.)
    # Organize them by well name
    i=1
    for well in "\${wells[@]}"; do
        if [ -f "input_\${i}/BarcodePreprocessing_Foci.csv" ]; then
            mkdir -p "analysis_input/\$well"
            cp "input_\${i}/BarcodePreprocessing_Foci.csv" "analysis_input/\$well/BarcodePreprocessing_Foci.csv"
        fi
        ((i++))
    done

    # Convert Python script to notebook
    jupytext --to ipynb ${qc_preprocess_script} -o qc_barcode_preprocess_template.ipynb

    # Run papermill to execute notebook with parameters
    papermill qc_barcode_preprocess_template.ipynb \\
        ${prefix}_qc_barcode_preprocess.ipynb \\
        -p input_dir './analysis_input' \\
        -p output_dir '.' \\
        -p use_cache false \\
        -p numcycles ${num_cycles} \\
        -p barcode_library_path ${barcode_library} \\
        ${rows_param} \\
        ${columns_param}

    jupyter nbconvert --to html ${prefix}_qc_barcode_preprocess.ipynb

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        jupytext: \$(jupytext --version | sed 's/jupytext //')
        papermill: \$(papermill --version | sed 's/papermill //')
        nbconvert: \$(jupyter nbconvert --version | sed 's/nbconvert //')
    END_VERSIONS
    """

    stub:
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    touch ${prefix}_qc_barcode_preprocess.ipynb
    touch ${prefix}_qc_barcode_preprocess.html
    touch ${prefix}_qc_barcode_preprocess.png

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        jupytext: 1.16.0
        papermill: 2.5.0
        nbconvert: 7.16.0
    END_VERSIONS
    """
}
