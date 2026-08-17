process ALIGN_COMBINED {
    tag "${meta.id}"
    label 'align'

    // Built from containers/align/Dockerfile - not yet built/pushed anywhere, placeholder tag
    container "align:local"

    input:
    tuple val(meta), path(painting_images, stageAs: "images/painting/"), path(barcoding_images, stageAs: "images/barcoding/"), val(image_metas)
    val painting_scalingstring
    val barcoding_scalingstring
    val painting_channame
    val barcoding_channame

    output:
    tuple val(meta), path("aligned_painting/*.tiff"), emit: painting_aligned_images
    tuple val(meta), path("aligned_barcoding/*.tiff"), emit: barcoding_aligned_images
    tuple val(meta), path("*.csv"), optional: true, emit: alignment_stats
    tuple val(meta), path("*.png"), optional: true, emit: qc_overlay
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    // Serialize per-image metadata (arm/channel/cycle) for bin/align_combined.py to consume.
    def metadata_json_content = groovy.json.JsonOutput.toJson(image_metas)
    def metadata_base64 = metadata_json_content.bytes.encodeBase64().toString()
    """
    mkdir -p aligned_painting aligned_barcoding
    echo '${metadata_base64}' | base64 -d > metadata.json

    align_combined.py \\
        --painting-images-dir images/painting/ \\
        --barcoding-images-dir images/barcoding/ \\
        --metadata-json metadata.json \\
        --output-dir . \\
        --painting-output-dir aligned_painting/ \\
        --barcoding-output-dir aligned_barcoding/ \\
        --painting-scalingstring "${painting_scalingstring}" \\
        --barcoding-scalingstring "${barcoding_scalingstring}" \\
        --painting-channame "${painting_channame}" \\
        --barcoding-channame "${barcoding_channame}"

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        scikit-image: \$(python3 -c "import skimage; print(skimage.__version__)")
    END_VERSIONS
    """

    stub:
    """
    mkdir -p aligned_painting aligned_barcoding
    touch aligned_painting/${meta.id}_CorrDNA.tiff
    touch aligned_barcoding/${meta.id}_Cycle01_DNA.tiff
    touch AlignCombined_stats.csv
    touch AlignCombined_QC.png

    cat <<-END_VERSIONS > versions.yml
        "${task.process}":
            scikit-image: 0.25.2
    END_VERSIONS
    """
}
