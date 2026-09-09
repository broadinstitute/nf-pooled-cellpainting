process CELLPROFILER_PLUGINS_UPDATE {
    tag "${repo}"
    label 'process_single'

    // Referenced by tag, not digest: pinning by digest breaks under -profile arm's forced
    // --platform=linux/amd64, since Docker refuses to reassign an already-cached digest to a
    // different platform's manifest ("cannot overwrite digest ..."). Bitnami no longer publishes
    // versioned tags for this image, so 'latest' is the only stable name available.
    container 'bitnami/git:latest'
    // Image's default entrypoint prints a banner and breaks Nextflow's script invocation; clear it.
    containerOptions '--entrypoint ""'

    input:
    val repo

    output:
    path "CellProfiler-plugins/active_plugins/*.py", emit: plugin_files
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    git clone --depth 1 ${repo} CellProfiler-plugins

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        git: \$(git --version | sed 's/git version //')
    END_VERSIONS
    """

    stub:
    """
    mkdir -p CellProfiler-plugins/active_plugins
    touch CellProfiler-plugins/active_plugins/callbarcodes.py
    touch CellProfiler-plugins/active_plugins/compensatecolors.py

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        git: 2.55.0
    END_VERSIONS
    """
}
