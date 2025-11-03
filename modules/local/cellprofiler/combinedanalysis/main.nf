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
    mkdir -p results/segmentation_masks

    # Create stub overlay PNG files
    touch results/Plate1-B1_CorrDNA_Site_4_Overlay.png
    touch results/Plate1-B1_CorrDNA_Site_4_SpotOverlay.png

    # Create stub CSV statistics files
    touch results/BarcodeFoci.csv
    touch results/Cells.csv
    touch results/ConfluentRegions.csv
    touch results/Cytoplasm.csv
    touch results/Experiment.csv
    touch results/Foci_NonCellEdge.csv
    touch results/Foci_PreMask.csv
    touch results/Foci.csv
    touch results/Image.csv
    touch results/Nuclei.csv
    touch results/PreCells.csv
    touch results/RelateObjects.csv
    touch results/ResizeConfluent.csv
    touch results/ResizeCells.csv
    touch results/Resize_Foci.csv
    touch results/ResizeNuclei.csv

    # Create stub segmentation masks
    touch results/segmentation_masks/stub_mask.tiff

    # Create stub load_data.csv
    touch load_data.csv

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        cellprofiler: \$(cellprofiler --version)
    END_VERSIONS
    """
}
