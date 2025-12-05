process CELLPROFILER_ILLUMAPPLY {
    tag "${meta.id}"
    label 'cellprofiler_basic'

    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(meta), val(channels), val(cycles), path(images, stageAs: "images/img?/*"), val(image_metas), path(npy_files, stageAs: "images/")
    path illumination_apply_cppipe
    val has_cycles

    output:
    tuple val(meta), path("*.tiff"), path("*.csv"), emit: corrected_images
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
        --pipeline-type illumapply \\
        --images-dir ./images \\
        --illum-dir ./images \\
        --output load_data.csv \\
        --metadata-json metadata.json \\
        --channels "${channels}" \\
        --cycle-metadata-name "${params.cycle_metadata_name}" \\
        ${has_cycles ? '--has-cycles' : ''}

    # Patch Base image location to use Default Input Folder (staged images)
    # We need to copy the input file to a writable file first if it's a symlink or read-only
    cp -L ${illumination_apply_cppipe} illumination_apply_patched.cppipe
    sed -i 's/Base image location:None|/Base image location:Default Input Folder|/g' illumination_apply_patched.cppipe

    cellprofiler -c -r \\
        -p illumination_apply_patched.cppipe \\
        -o . \\
        --data-file=load_data.csv \\
        --image-directory ./images/

    cat <<-END_VERSIONS > versions.yml
	"${task.process}":
	    cellprofiler: \$(cellprofiler --version)
	END_VERSIONS
    """

    stub:
    // For barcoding (has_cycles=true): create files with _Cycle pattern that downstream regex expects
    // For painting (has_cycles=false): create painting-style files
    def stub_files = has_cycles ?
        """
        touch load_data.csv
        touch Plate_${meta.plate}_Well_${meta.well}_Site_${meta.site ?: 1}_Cycle01_DNA.tiff
        touch Plate_${meta.plate}_Well_${meta.well}_Site_${meta.site ?: 1}_Cycle01_A.tiff
        touch BarcodingIllumApplication_Cells.csv
        touch BarcodingIllumApplication_ConfluentRegions.csv
        touch BarcodingIllumApplication_Experiment.csv
        touch BarcodingIllumApplication_Image.csv
        touch BarcodingIllumApplication_Nuclei.csv
        """ :
        """
        touch load_data.csv
        touch Plate_${meta.plate}_Well_${meta.well}_Site_${meta.site ?: 1}_CorrPhalloidin.tiff
        touch PaintingIllumApplication_Cells.csv
        touch PaintingIllumApplication_ConfluentRegions.csv
        touch PaintingIllumApplication_Experiment.csv
        touch PaintingIllumApplication_Image.csv
        touch PaintingIllumApplication_Nuclei.csv
        """
    """
    ${stub_files}

    cat <<-END_VERSIONS > versions.yml
	"${task.process}":
	    cellprofiler: \$(cellprofiler --version)
	END_VERSIONS
    """
}
