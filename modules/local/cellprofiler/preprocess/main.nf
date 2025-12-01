process CELLPROFILER_PREPROCESS {
    tag "${meta.id}"
    label 'cellprofiler_medium'

    conda "${moduleDir}/environment.yml"
    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(meta), path(aligned_images, stageAs: "images/"), val(image_metas)
    path preprocess_cppipe
    path barcodes, stageAs: "images/Barcodes.csv"
    path plugins, stageAs: "plugins/"

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
    // Base64 encode to reduce log verbosity
    def metadata_json_content = groovy.json.JsonOutput.toJson(image_metas)
    def metadata_base64 = metadata_json_content.bytes.encodeBase64().toString()

    """
    # Create metadata JSON file from base64 (reduces log verbosity)
    echo '${metadata_base64}' | base64 -d > metadata.json

    # Generate load_data.csv
    generate_load_data_csv.py \\
        --metadata-json metadata.json \\
        --pipeline-type preprocess \\
        --images-dir ./images \\
        --output load_data.csv \\
        --cycle-metadata-name "${params.cycle_metadata_name}"

    # Patch Base image location to use Default Input Folder (staged images)
    cp -L ${preprocess_cppipe} preprocess_patched.cppipe
    sed -i 's/Base image location:None|/Base image location:Default Input Folder|/g' preprocess_patched.cppipe

    cellprofiler -c -r \\
        ${task.ext.args ?: ''} \\
        -p preprocess_patched.cppipe \\
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
    touch ${meta.id}_Cycle01_A.tiff
    touch ${meta.id}_Cycle01_C.tiff
    touch load_data.csv
    mkdir -p overlay
    touch overlay/test.tiff

    cat <<-END_VERSIONS > versions.yml
	"${task.process}":
	    cellprofiler: 4.2.8
	END_VERSIONS
    """
}
