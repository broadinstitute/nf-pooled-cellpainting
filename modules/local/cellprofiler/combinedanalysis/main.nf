process CELLPROFILER_COMBINEDANALYSIS {
    tag "${meta.id}"
    label 'cellprofiler_medium'

    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(meta), path(cropped_images, stageAs: "images/"), val(image_metas)
    path combinedanalysis_cppipe
    path barcodes, stageAs: "images/Barcodes.csv"
    path plugins, stageAs: "plugins/"

    output:
    tuple val(meta), path("*.png"), emit: overlay_images
    tuple val(meta), path("*.csv"), emit: csv_stats
    tuple val(meta), path("segmentation_masks/*.tiff"), emit: segmentation_masks, optional: true
    path "load_data.csv", emit: load_data_csv
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    // Serialize metadata directly - structure prepared in workflow (no transformation here!)
    // Base64 encode to reduce log verbosity
    def metadata_json_content = groovy.json.JsonOutput.toJson(image_metas)
    def metadata_base64 = metadata_json_content.bytes.encodeBase64().toString()

    """
    # Set writable cache directories for CellProfiler and dependencies
    export MPLCONFIGDIR=\${PWD}/.matplotlib
    export HOME=\${PWD}
    export XDG_CACHE_HOME=\${PWD}/.cache
    mkdir -p \${MPLCONFIGDIR} \${XDG_CACHE_HOME}

    # Create metadata JSON file from base64 (reduces log verbosity)
    echo '${metadata_base64}' | base64 -d > metadata.json

    # Generate load_data.csv using the unified script with 'combined' pipeline type
    generate_load_data_csv.py \\
        --metadata-json metadata.json \\
        --pipeline-type combined \\
        --images-dir ./images \\
        --output load_data.csv \\
        --cycle-metadata-name "${params.cycle_metadata_name}"

    # Patch Base image location to use Default Input Folder (staged images)
    cp -L ${combinedanalysis_cppipe} combinedanalysis_patched.cppipe
    sed -i 's/Base image location:None|/Base image location:Default Input Folder|/g' combinedanalysis_patched.cppipe

    cellprofiler -c -r \\
        -p combinedanalysis_patched.cppipe \\
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
    # Set writable cache directories for CellProfiler and dependencies
    export MPLCONFIGDIR=\${PWD}/.matplotlib
    export HOME=\${PWD}
    export XDG_CACHE_HOME=\${PWD}/.cache
    mkdir -p \${MPLCONFIGDIR} \${XDG_CACHE_HOME}

    mkdir -p segmentation_masks

    # Create stub overlay PNG files
    touch Plate1-B1_CorrDNA_Site_4_Overlay.png
    touch Plate1-B1_CorrDNA_Site_4_SpotOverlay.png

    # Create stub CSV statistics files
    touch BarcodeFoci.csv
    touch Cells.csv
    touch ConfluentRegions.csv
    touch Cytoplasm.csv
    touch Experiment.csv
    touch Foci_NonCellEdge.csv
    touch Foci_PreMask.csv
    touch Foci.csv
    touch Image.csv
    touch Nuclei.csv
    touch PreCells.csv
    touch RelateObjects.csv
    touch ResizeConfluent.csv
    touch ResizeCells.csv
    touch Resize_Foci.csv
    touch ResizeNuclei.csv

    # Create stub segmentation masks
    touch segmentation_masks/stub_mask.tiff

    # Create stub load_data.csv
    touch load_data.csv

    cat <<-END_VERSIONS > versions.yml
	"${task.process}":
	    cellprofiler: \$(cellprofiler --version)
	END_VERSIONS
    """
}
