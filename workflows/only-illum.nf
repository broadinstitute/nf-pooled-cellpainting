/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPAINTING_ONLY_ILLUM } from '../subworkflows/local/cellpainting_only_illum'
include { BARCODING_ONLY_ILLUM } from '../subworkflows/local/barcoding_only_illum'
include { MULTIQC } from '../modules/nf-core/multiqc/main'

include { paramsSummaryMap } from 'plugin/nf-schema'
include { paramsSummaryMultiqc } from '../subworkflows/nf-core/utils_nfcore_pipeline'
include { softwareVersionsToYAML } from '../subworkflows/nf-core/utils_nfcore_pipeline'
include { methodsDescriptionText } from '../subworkflows/local/utils_nfcore_nf-pooled-cellpainting_pipeline'

/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    RUN ONLYILLUM WORKFLOW
    Runs only Phase 1 (illumination calculation + its QC) for both arms - no
    illumapply, segmentation/preprocessing, stitching, or combined analysis.
    Defaults to per-plate illumcalc; pass --distributeillum for per-well
    illumcalc jobs averaged back into a per-plate illum. --skipillum is
    rejected, since skipping the only thing this entrypoint does is pointless.
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

workflow ONLYILLUM_POOLED_CELLPAINTING {
    take:
    ch_samplesheet // channel: samplesheet read in from --input

    main:

    if (params.skipillum) {
        error("--skipillum cannot be used with -entry ONLYILLUM, which only runs illumination calculation.")
    }

    ch_versions = channel.empty()
    ch_multiqc_files = channel.empty()

    ch_samplesheet_flat = ch_samplesheet.flatMap { meta, image ->
        // Split imaging channels by comma and create a separate entry for each channel
        meta.original_channels = meta.channels
        meta.remove('original_channels')
        return [[meta, image]]
    }

    // Add meta.arm back into each channel
    ch_samplesheet_painting = ch_samplesheet_flat
        .filter { meta, _image ->
            meta.arm == "painting"
        }
        .map { meta, image ->
            [meta + [arm: 'painting'], image]
        }
    ch_samplesheet_barcoding = ch_samplesheet_flat
        .filter { meta, _image ->
            meta.arm == "barcoding"
        }
        .map { meta, image ->
            [meta + [arm: 'barcoding'], image]
        }

    // Calculate illumination correction profiles for the painting arm
    CELLPAINTING_ONLY_ILLUM(
        ch_samplesheet_painting,
        params.painting_illumcalc_cppipe,
        params.outdir,
        params.distributeillum,
    )
    ch_versions = ch_versions.mix(CELLPAINTING_ONLY_ILLUM.out.versions)

    // Calculate illumination correction profiles for the barcoding arm
    BARCODING_ONLY_ILLUM(
        ch_samplesheet_barcoding,
        params.barcoding_illumcalc_cppipe,
        params.outdir,
        params.distributeillum,
    )
    ch_versions = ch_versions.mix(BARCODING_ONLY_ILLUM.out.versions)

    //
    // Collate and save software versions

    softwareVersionsToYAML(ch_versions)
        .collectFile(
            storeDir: "${params.outdir}/pipeline_info",
            name: 'nf-pooled-cellpainting_software_' + 'mqc_' + 'versions.yml',
            newLine: true,
        )
        .set { ch_collated_versions }


    //
    // MODULE: MultiQC
    //
    summary_params = paramsSummaryMap(
        workflow,
        parameters_schema: "nextflow_schema.json"
    )
    ch_workflow_summary = channel.value(paramsSummaryMultiqc(summary_params))
    ch_multiqc_files = ch_multiqc_files.mix(
        ch_workflow_summary.collectFile(name: 'workflow_summary_mqc.yaml')
    )
    ch_multiqc_custom_methods_description = params.multiqc_methods_description
        ? file(params.multiqc_methods_description, checkIfExists: true)
        : file("${projectDir}/assets/methods_description_template.yml", checkIfExists: true)
    ch_methods_description = channel.value(
        methodsDescriptionText(ch_multiqc_custom_methods_description)
    )

    ch_multiqc_files = ch_multiqc_files.mix(ch_collated_versions)
    ch_multiqc_files = ch_multiqc_files.mix(
        ch_methods_description.collectFile(
            name: 'methods_description_mqc.yaml',
            sort: true,
        )
    )

    MULTIQC(
        ch_multiqc_files.collect().map { files ->
            def config_list = [file("${projectDir}/assets/multiqc_config.yml")]
            if (params.multiqc_config) {
                config_list << file(params.multiqc_config)
            }
            def logo_list = params.multiqc_logo ? [file(params.multiqc_logo)] : []
            [[id: 'multiqc'], files, config_list, logo_list, [], []]
        }
    )

    emit:
    multiqc_report = MULTIQC.out.report.toList() // channel: /path/to/multiqc_report.html
    versions = ch_versions // channel: [ path(versions.yml) ]
}
