process FIJI_STITCHCROP {
    tag "${meta.id}"
    label 'process_high'

    conda "${moduleDir}/environment.yml"
    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/fiji_openjdk:placeholder'
        : 'docker.io/fiji/fiji:latest'}"

    containerOptions {
        workflow.containerEngine == 'docker' ? '--entrypoint=""' : ''
    }

    input:
    tuple val(meta), path(corrected_images, stageAs: "images_corrected/*")
    val track_type
    path stitch_script

    output:
    path "stitched/*"       , emit: stitched_images
    path "cropped/*"        , emit: cropped_images
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
    def compress_flag = task.ext.compress ?: 'True'
    """
    # Create output directories
    mkdir -p stitched cropped downsampled

    # Create directory structure expected by the Fiji script
    # The script expects: STITCH_INPUT_BASE/images_corrected/{track_type}/
    WORK_DIR=\$(pwd)
    mkdir -p input_base/images_corrected/${track_type}

    # Copy images to the expected input structure
    cp images_corrected/* input_base/images_corrected/${track_type}/

    # Set environment variables for the Fiji script
    # STITCH_INPUT_BASE should point to the parent directory
    export STITCH_INPUT_BASE=\${WORK_DIR}/input_base
    export STITCH_TRACK_TYPE=${track_type}
    export CROP_PERCENT=${crop_percent}
    export STITCH_AUTORUN=true

    # Debug: Check input structure
    echo "=== Debugging Input Structure ==="
    echo "Working directory: \$(pwd)"
    echo "Contents of input_base/images_corrected/${track_type}/:"
    ls -la input_base/images_corrected/${track_type}/ || echo "Directory not found"
    echo "Environment variables:"
    echo "  STITCH_INPUT_BASE=\${STITCH_INPUT_BASE}"
    echo "  STITCH_TRACK_TYPE=\${STITCH_TRACK_TYPE}"
    echo "  CROP_PERCENT=\${CROP_PERCENT}"
    echo "  STITCH_AUTORUN=\${STITCH_AUTORUN}"

    # Script is staged as an input
    echo "Using stitch script: ${stitch_script}"
    if [ ! -f "${stitch_script}" ]; then
        echo "ERROR: stitch_crop.py not found at ${stitch_script}!"
        exit 1
    fi

    # Check if Fiji executable exists
    if [ ! -f "/opt/fiji/Fiji.app/ImageJ-linux64" ]; then
        echo "ERROR: Fiji executable not found at /opt/fiji/Fiji.app/ImageJ-linux64"
        echo "Searching for Fiji..."
        find / -name "*fiji*" -o -name "ImageJ*" 2>/dev/null | head -20
        exit 1
    fi

    echo "=== Running Fiji ==="
    # Run Fiji with the stitch_crop.py script as a Jython macro
    # The script needs to run in Fiji's Jython interpreter
    /opt/fiji/Fiji.app/ImageJ-linux64 --headless --console --jython ${stitch_script} 2>&1 | tee fiji_output.log
    FIJI_EXIT=\$?

    echo "Fiji exit code: \${FIJI_EXIT}"
    echo "Full Fiji output:"
    cat fiji_output.log || echo "No output log found"

    echo "=== Fiji Completed ==="
    echo "Output directories created:"
    ls -la input_base/

    # The script creates outputs like:
    # - input_base/images_corrected_stitched/{track_type}/
    # - input_base/images_corrected_cropped/{track_type}/
    # - input_base/images_corrected_stitched_10X/{track_type}/

    # Create output directories and move files
    mkdir -p stitched cropped downsampled

    if [ -d "input_base/images_corrected_stitched/${track_type}" ]; then
        find input_base/images_corrected_stitched/${track_type}/ -type f -name "*.tif*" -exec mv {} stitched/ \\; 2>/dev/null || true
    fi
    if [ -d "input_base/images_corrected_cropped/${track_type}" ]; then
        find input_base/images_corrected_cropped/${track_type}/ -type f -name "*.tif*" -exec mv {} cropped/ \\; 2>/dev/null || true
    fi
    if [ -d "input_base/images_corrected_stitched_10X/${track_type}" ]; then
        find input_base/images_corrected_stitched_10X/${track_type}/ -type f -name "*.tif*" -exec mv {} downsampled/ \\; 2>/dev/null || true
    fi

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        fiji: \$(fiji --version 2>&1 | grep -o 'ImageJ [0-9.]*' | sed 's/ImageJ //' || echo "unknown")
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
        fiji: stub
    END_VERSIONS
    """
}
