process ALIGN_INTRAARM {
    tag "${meta.id}"
    label 'align'

    // Built from containers/align/Dockerfile - not yet built/pushed anywhere, placeholder tag
    container "align:local"

    input:
    tuple val(meta), path(stitched_images, stageAs: "images/"), val(image_metas)
    val channame
    val shift_threshold
    val corr_threshold

    output:
    tuple val(meta), path("*.tiff"), emit: aligned_images
    tuple val(meta), path("*.csv"), optional: true, emit: alignment_stats
    tuple val(meta), path("*.png"), optional: true, emit: qc_overlay
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    // Serialize image metadata (cycle/channel per file) for bin/align_intraarm.py to consume.
    def metadata_json_content = groovy.json.JsonOutput.toJson(image_metas)
    def metadata_base64 = metadata_json_content.bytes.encodeBase64().toString()
    """
    echo '${metadata_base64}' | base64 -d > metadata.json

    align_intraarm.py \\
        --images-dir images/ \\
        --metadata-json metadata.json \\
        --output-dir . \\
        --channame "${channame}" \\
        --shift-threshold "${shift_threshold}" \\
        --corr-threshold "${corr_threshold}"

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        scikit-image: \$(python3 -c "import skimage; print(skimage.__version__)")
    END_VERSIONS
    """

    stub:
    def is_barcoding = meta.arm == 'barcoding'
    """
    if [ "${is_barcoding}" == "true" ]; then
        touch ${meta.id}_Cycle01_DNA.tiff
        touch ${meta.id}_Cycle01_A.tiff
    else
        touch ${meta.id}_CorrDNA.tiff
        touch ${meta.id}_CorrER.tiff
    fi
    touch AlignIntraArm_stats.csv
    touch AlignIntraArm_QC_Cycle02.png

    cat <<-END_VERSIONS > versions.yml
        "${task.process}":
            scikit-image: 0.25.2
    END_VERSIONS
    """
}
