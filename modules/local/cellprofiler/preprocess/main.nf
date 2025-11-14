process CELLPROFILER_PREPROCESS {
    tag "${meta.id}"
    label 'cellprofiler_basic'

    conda "${moduleDir}/environment.yml"
    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(meta), path(aligned_images, stageAs: "images/*"), val(image_metas)
    path preprocess_cppipe
    path barcodes, stageAs: "images/Barcodes.csv"
    path plugins, stageAs: "plugins/*"

    output:
    tuple val(meta), path("*.tiff"), emit: preprocessed_images
    path "overlay/*.tiff", optional: true, emit: overlay
    tuple val(meta), path("BarcodePreprocessing*.csv"), emit: preprocess_stats
    path "load_data.csv", emit: load_data_csv
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    // Serialize image metadata directly - it already contains all fields (plate, well, site, channels, filename, etc.)
    def metadata_json = groovy.json.JsonOutput.toJson(image_metas)

    """
    # Create metadata JSON file
    cat > metadata.json << 'EOF'
${metadata_json}
EOF

    # Generate load_data.csv
    generate_load_data_csv.py \\
        --metadata-json metadata.json \\
        --pipeline-type preprocess \\
        --images-dir ./images \\
        --output load_data.csv

    cellprofiler -c -r \\
        ${task.ext.args ?: ''} \\
        -p ${preprocess_cppipe} \\
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
    touch BarcodePreprocessing_Experiment.csv
    touch BarcodePreprocessing_Image.csv
    touch BarcodePreprocessing_Nuclei.csv
    touch BarcodePreprocessing_AllFoci.csv
    touch BarcodePreprocessing_BarcodeFoci.csv
    touch BarcodePreprocessing_Foci.csv
    touch Plate_Plate1_Well_A1_Site0_Cycle01_A.tiff
    touch load_data.csv
    mkdir -p overlay
    touch overlay/test.tiff

    cat <<-END_VERSIONS > versions.yml
	"${task.process}":
	    cellprofiler: \$(cellprofiler --version)
	END_VERSIONS
    """
}
