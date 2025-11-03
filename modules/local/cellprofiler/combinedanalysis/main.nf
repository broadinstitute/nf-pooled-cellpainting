process CELLPROFILER_COMBINEDANALYSIS {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://depot.galaxyproject.org/singularity/cellprofiler:4.2.8--pyhdfd78af_0':
        'biocontainers/cellprofiler:4.2.8--pyhdfd78af_0' }"

    input:
    tuple val(meta), path(cropped_images, stageAs: "images/*")
    path combinedanalysis_cppipe
    path barcodes, stageAs: "images/Barcodes.csv"
    path plugins, stageAs: "plugins/*"

    output:
    tuple val(meta), path("*.png")                     , emit: overlay_images
    tuple val(meta), path("*.csv")                     , emit: csv_stats
    tuple val(meta), path("segmentation_masks/*.tiff") , emit: segmentation_masks, optional: true
    path "load_data.csv"                               , emit: load_data_csv
    path "versions.yml"                                , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    # Set writable cache directories for CellProfiler and dependencies
    export MPLCONFIGDIR=\${PWD}/.matplotlib
    export HOME=\${PWD}
    export XDG_CACHE_HOME=\${PWD}/.cache
    mkdir -p \${MPLCONFIGDIR} \${XDG_CACHE_HOME}

    generate_combined_load_data.py \\
        --images-dir ./images \\
        --output load_data.csv

    cellprofiler -c -r \\
        -p ${combinedanalysis_cppipe} \\
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
    # Set writable cache directories for CellProfiler and dependencies
    export MPLCONFIGDIR=\${PWD}/.matplotlib
    export HOME=\${PWD}
    export XDG_CACHE_HOME=\${PWD}/.cache
    mkdir -p \${MPLCONFIGDIR} \${XDG_CACHE_HOME}

    mkdir -p segmentation_masks

    # Create stub overlay PNG files
    touch Plate1-B1_CorrDNA_Site_4_Overlay.png
    touch Plate1-B1_CorrDNA_Site_4_SpotOverlay.png

    # Create stub CSV statistics files
    touch BarcodeFoci.csv
    touch Cells.csv
    touch ConfluentRegions.csv
    touch Cytoplasm.csv
    touch Experiment.csv
    touch Foci_NonCellEdge.csv
    touch Foci_PreMask.csv
    touch Foci.csv
    touch Image.csv
    touch Nuclei.csv
    touch PreCells.csv
    touch RelateObjects.csv
    touch ResizeConfluent.csv
    touch ResizeCells.csv
    touch Resize_Foci.csv
    touch ResizeNuclei.csv

    # Create stub segmentation masks
    touch segmentation_masks/stub_mask.tiff

    # Create stub load_data.csv
    touch load_data.csv

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        cellprofiler: \$(cellprofiler --version)
    END_VERSIONS
    """
}
