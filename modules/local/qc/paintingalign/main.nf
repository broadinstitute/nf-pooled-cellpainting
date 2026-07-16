process QC_PAINTINGALIGN {
    tag "${meta.id}"
    label 'qc'

    container 'community.wave.seqera.io/library/ipykernel_jupytext_nbconvert_pandas_pruned:c397cee54f4ab064'

    input:
    tuple val(meta), val(wells), path(csv_files, stageAs: 'input_?/*'), val(num_cycles)
    path qc_paintingalign_script
    val rows
    val columns

    output:
    tuple val(meta), path("*_qc_painting_align.ipynb"), emit: notebook
    tuple val(meta), path("*.html"), emit: html_report
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
    for dir in input_*/; do
        if [ -f "\${dir}PaintingIllumApplication_Image.csv" ]; then
            mkdir -p "analysis_input/\${dir}"
            mv "\${dir}PaintingIllumApplication_Image.csv" "analysis_input/\${dir}PaintingIllumApplication_Image.csv"
        fi
    done

    # Convert Python script to notebook
    jupytext --to ipynb ${qc_paintingalign_script} -o qc_painting_align_template.ipynb

    # Run papermill to execute notebook with parameters
    papermill qc_painting_align_template.ipynb \\
        ${prefix}_qc_painting_align.ipynb \\
        -p input_dir './analysis_input' \\
        -p output_dir '.' \\
        -p use_cache false \\
        -p numcycles ${num_cycles} \\
        ${rows_param} \\
        ${columns_param}

    jupyter nbconvert --to html --no-input ${prefix}_qc_painting_align.ipynb

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
    touch ${prefix}_qc_painting_align.ipynb
    touch ${prefix}_qc_painting_align.html

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        jupytext: 1.16.0
        papermill: 2.5.0
        nbconvert: 7.16.0
    END_VERSIONS
    """
}
