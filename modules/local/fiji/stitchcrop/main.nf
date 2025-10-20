process FIJI_STITCHCROP {
    tag "${meta.id}"
    label 'process_high'

    conda "${moduleDir}/environment.yml"
    container 'docker.io/fiji/fiji:latest'

    containerOptions {
        workflow.containerEngine == 'docker' ? '--entrypoint=""' : ''
    }

    input:
    tuple val(meta), path(corrected_images, stageAs: 'images/*')
    path stitch_script
    val crop_percent

    output:
    tuple val(meta), path("stitched_images/*.tiff")                 , emit: stitched_images
    tuple val(meta), path("stitched_images/TileConfiguration.txt")  , emit: tile_config
    tuple val(meta), path("cropped_images/*.tiff")                  , emit: cropped_images
    tuple val(meta), path("downsampled_images/*.tiff")              , emit: downsampled_images
    path("versions.yml")                                            , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    // Allocate 75% of available memory to JVM heap (leaving 25% for non-heap, native memory, and OS)
    // Use a minimum of 2GB to ensure basic functionality
    def heap_size = task.memory ? Math.max(2, (task.memory.toGiga() * 0.75) as int) : 2
    def threads = task.cpus ?: 1
    """
    # Set environment variables for Fiji script (simplified for Nextflow integration)
    export CROP_PERCENT=${crop_percent}
    export STITCH_AUTORUN=true

    # Configure Java memory directly via JVM heap options
    # -Xms: initial heap size, -Xmx: maximum heap size
    # Also set ImageJ-specific options and thread count
    export _JAVA_OPTIONS="-Xmx${heap_size}g -Duser.home=/tmp/fiji_prefs -Dij.dir=/opt/fiji/Fiji.app -Dscijava.thread.max=${threads}"
    mkdir -p /tmp/fiji_prefs

    # Run Fiji in headless mode
    /opt/fiji/Fiji.app/ImageJ-linux64 \\
        --ij-dir /opt/fiji/Fiji.app \\
        --headless \\
        --console \\
        --run ${stitch_script}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        fiji: \$(/opt/fiji/Fiji.app/ImageJ-linux64 -h 2>&1 | grep "ImageJ launcher" | awk '{print \$3}')
    END_VERSIONS
    """

    stub:
    """
    mkdir -p stitched_images
    mkdir -p cropped_images
    mkdir -p downsampled_images

    touch stitched_images/Plate1-A1_Stitched_DNA.tiff
    touch stitched_images/TileConfiguration.txt
    touch cropped_images/Plate1-A1_DNA_Site_1.tiff
    touch downsampled_images/Plate1-A1_Stitched_DNA.tiff

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        fiji: \$(/opt/fiji/Fiji.app/ImageJ-linux64 -h 2>&1 | grep "ImageJ launcher" | awk '{print \$3}' || echo "unknown")
    END_VERSIONS
    """
}
