process PYTHON_STITCHCROP {
    tag "${meta.id}"
    label 'process_high'

    conda "${moduleDir}/environment.yml"
    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
        : 'community.wave.seqera.io/library/pip_numpy_scipy_pillow_pruned:ef738e45d41bdb58'}"

    input:
    tuple val(meta), path(corrected_images, stageAs: "images_corrected/*")
    val track_type

    output:
    tuple val(meta), path("stitched/*"), emit: stitched
    tuple val(meta), path("cropped/*"), emit: cropped
    tuple val(meta), path("downsampled/*"), emit: downsampled
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args = task.ext.args ?: ''
    def crop_percent = task.ext.crop_percent ?: 25
    def grid_rows = task.ext.grid_rows ?: 2
    def grid_cols = task.ext.grid_cols ?: 2
    def overlap = task.ext.overlap ?: 10.0
    def scale = task.ext.scale ?: 1.99
    def tiles_per_side = task.ext.tiles_per_side ?: 2
    def compress_flag = task.ext.no_compress ? '--no-compress' : ''
    """
    stitch_crop_python.py \\
        . \\
        ${track_type} \\
        --input-dir ./images_corrected \\
        --crop-percent ${crop_percent} \\
        --grid-rows ${grid_rows} \\
        --grid-cols ${grid_cols} \\
        --overlap ${overlap} \\
        --scale ${scale} \\
        --tiles-per-side ${tiles_per_side} \\
        --output-stitched stitched \\
        --output-cropped cropped \\
        --output-downsampled downsampled \\
        ${compress_flag} \\
        ${args}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version | sed 's/Python //g')
        numpy: \$(python -c "import numpy; print(numpy.__version__)")
        pillow: \$(python -c "import PIL; print(PIL.__version__)")
        tifffile: \$(python -c "import tifffile; print(tifffile.__version__)")
    END_VERSIONS
    """

    stub:
    """
    mkdir -p stitched cropped downsampled

    touch stitched/Stitched_test.tiff
    touch cropped/test_Site_1.tiff
    touch downsampled/Stitched_test.tiff

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version | sed 's/Python //g')
        numpy: \$(python -c "import numpy; print(numpy.__version__)")
        pillow: \$(python -c "import PIL; print(PIL.__version__)")
        tifffile: \$(python -c "import tifffile; print(tifffile.__version__)")
    END_VERSIONS
    """
}
