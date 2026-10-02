process CROP {
    tag "${meta.id}"
    label 'crop'

    // bin/crop.py only needs numpy + Pillow, both already present in this image
    container "community.wave.seqera.io/library/numpy_python_pip_pillow:74310e9b76ff61b6"

    input:
    tuple val(meta), path(stitched_images, stageAs: 'images/')
    val tileperside
    val final_tile_size
    val compress
    val phenix
    val channame

    output:
    tuple val(meta), path("cropped_images/**.tiff"), emit: cropped_images
    path "versions.yml", emit: versions

    // No when: clause - unconditional, runs for every well regardless of qc_*_passed.

    script:
    def first_site_index = meta.first_site_index ?: 0
    """
    mkdir -p cropped_images

    crop.py \\
        --input-dir images/ \\
        --output-dir cropped_images/ \\
        --tileperside "${tileperside}" \\
        --final-tile-size "${final_tile_size}" \\
        --compress "${compress}" \\
        --phenix "${phenix}" \\
        --channame "${channame}" \\
        --first-site-index "${first_site_index}"

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        crop: 0.1.0
    END_VERSIONS
    """

    stub:
    def is_barcoding = meta.arm == 'barcoding'
    def prefix = "Plate_${meta.plate}_Well_${meta.well}_Site_1"
    """
    mkdir -p cropped_images

    if [ "${is_barcoding}" == "true" ]; then
        touch cropped_images/${prefix}_Cycle01_DNA.tiff
        touch cropped_images/${prefix}_Cycle01_A.tiff
    else
        touch cropped_images/${prefix}_Cycle01_CorrDNA.tiff
        touch cropped_images/${prefix}_Cycle01_CorrER.tiff
    fi

    cat <<-END_VERSIONS > versions.yml
        "${task.process}":
            crop: 0.1.0
    END_VERSIONS
    """
}
