process STITCH {
    tag "${meta.id}"
    label 'stitch'

    // Built from containers/ashlar/Dockerfile - not yet built/pushed anywhere, placeholder tag
    container "ashlar:local"

    input:
    tuple val(meta), path(corrected_images, stageAs: 'images/')
    path well_site_layouts_json
    val round_or_square
    val quarter_if_round
    val overlap_pct
    val imperwell
    val rows
    val columns
    val stitchorder
    val compress
    val phenix
    val channame

    output:
    tuple val(meta), path("stitched_images/*.tiff"), emit: stitched_images
    tuple val(meta), path("stitched_images/TileConfiguration*.txt"), optional: true, emit: tile_config
    tuple val(meta), path("downsampled_images/*.tiff"), emit: downsampled_images
    path "versions.yml", emit: versions

    // No when: clause - unconditional, runs for every well regardless of qc_*_passed.

    script:
    def first_site_index = meta.first_site_index ?: 0
    def cycle_arg = meta.cycle != null ? "--cycle ${meta.cycle}" : ''
    """
    mkdir -p stitched_images downsampled_images

    stitch.py \\
        --input-dir images/ \\
        --output-dir stitched_images/ \\
        --downsampled-dir downsampled_images/ \\
        --arm "${meta.arm}" \\
        --round-or-square "${round_or_square}" \\
        --quarter-if-round "${quarter_if_round}" \\
        --overlap-pct "${overlap_pct}" \\
        --imperwell "${imperwell ?: ''}" \\
        --rows "${rows ?: ''}" \\
        --columns "${columns ?: ''}" \\
        --stitchorder "${stitchorder}" \\
        --compress "${compress}" \\
        --phenix "${phenix}" \\
        --channame "${channame}" \\
        --first-site-index "${first_site_index}" \\
        --well-site-layouts-json "${well_site_layouts_json}" \\
        ${cycle_arg}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        ashlar: \$(ashlar --version 2>/dev/null | head -n1)
    END_VERSIONS
    """

    stub:
    def is_barcoding = meta.arm == 'barcoding'
    def prefix = "Plate_${meta.plate}_Well_${meta.well}_Site_1"
    def cycle_tag = String.format('Cycle%02d', (meta.cycle ?: 1) as Integer)
    """
    mkdir -p stitched_images downsampled_images

    if [ "${is_barcoding}" == "true" ]; then
        touch stitched_images/${prefix}_Stitched_${cycle_tag}_DNA.tiff
        touch downsampled_images/${prefix}_Stitched_${cycle_tag}_DNA.tiff
    else
        touch stitched_images/${prefix}_Stitched_${cycle_tag}_CorrDNA.tiff
        touch downsampled_images/${prefix}_Stitched_${cycle_tag}_CorrDNA.tiff
    fi
    touch stitched_images/TileConfiguration_${cycle_tag}.txt

    cat <<-END_VERSIONS > versions.yml
        "${task.process}":
            stitch: 0.1.0
    END_VERSIONS
    """
}
