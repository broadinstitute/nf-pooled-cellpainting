/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { MULTIQC                } from '../modules/nf-core/multiqc/main'
include { CELLPAINTING           } from '../subworkflows/local/cellpainting'
include { BARCODING           } from '../subworkflows/local/barcoding'


include { paramsSummaryMap       } from 'plugin/nf-schema'
include { paramsSummaryMultiqc   } from '../subworkflows/nf-core/utils_nfcore_pipeline'
include { softwareVersionsToYAML } from '../subworkflows/nf-core/utils_nfcore_pipeline'
include { methodsDescriptionText } from '../subworkflows/local/utils_nfcore_nf-pooled-cellpainting_pipeline'

/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    RUN MAIN WORKFLOW
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

workflow POOLED_CELLPAINTING {

    take:
    ch_samplesheet           // channel: samplesheet read in from --input
    barcodes                 // file: path to barcodes.csv file
    cppipes                  // array: paths to cpipe template files
    multichannel_parallel // boolean: whether to run cell painting in parallel for multi-channel images per FOV

    main:

    // ch_versions = Channel.empty()
    // ch_multiqc_files = Channel.empty()

    // Generate barcodes channel from barcodes.csv file
    // ch_barcodes = Channel.fromPath(barcodes, checkIfExists: true)

    ch_samplesheet = ch_samplesheet
        .flatMap { meta, image ->
            // Split channels by comma and create a separate entry for each channel
            meta.original_channels = meta.channels
            def channels_string = meta.channels.split(',')
            if (channels_string.size() > 1 & multichannel_parallel) {
                return channels_string.collect { channel_name ->
                    def new_meta = meta.clone()
                    new_meta.channels = channel_name.trim()
                    [new_meta, image]
                }
            } else {
                meta.remove('original_channels')
                return [[meta, image]]
            }
        }
        .branch { meta, _images ->
            cp: meta.arm == 'painting'
            sbs: meta.arm == 'barcoding'
        }

    // Add meta.arm back into each channel
    ch_samplesheet_cp = ch_samplesheet.cp.map { meta, image ->
        [meta + [arm: 'painting'], image]
    }
    ch_samplesheet_sbs = ch_samplesheet.sbs.map { meta, image ->
        [meta + [arm: 'barcoding'], image]
    }

    // Process cell painting (CP) data
    CELLPAINTING (
        ch_samplesheet_cp,
        cppipes,
        params.range_skip
    )

    // Process barcoding (sequencing by synthesis (SBS)) data

    // Run barcoding subworkflow
    BARCODING(
        ch_samplesheet_sbs,
        cppipes
    )


    //
    // Collate and save software versions
    //
    // softwareVersionsToYAML(ch_versions)
    //     .collectFile(
    //         storeDir: "${params.outdir}/pipeline_info",
    //         name:  'nf-pooled-cellpainting_software_'  + 'mqc_'  + 'versions.yml',
    //         sort: true,
    //         newLine: true
    //     ).set { ch_collated_versions }


    //
    // MODULE: MultiQC
    //
    // ch_multiqc_config        = Channel.fromPath(
    //     "$projectDir/assets/multiqc_config.yml", checkIfExists: true)
    // ch_multiqc_custom_config = params.multiqc_config ?
    //     Channel.fromPath(params.multiqc_config, checkIfExists: true) :
    //     Channel.empty()
    // ch_multiqc_logo          = params.multiqc_logo ?
    //     Channel.fromPath(params.multiqc_logo, checkIfExists: true) :
    //     Channel.empty()

    // summary_params      = paramsSummaryMap(
    //     workflow, parameters_schema: "nextflow_schema.json")
    // ch_workflow_summary = Channel.value(paramsSummaryMultiqc(summary_params))
    // ch_multiqc_files = ch_multiqc_files.mix(
    //     ch_workflow_summary.collectFile(name: 'workflow_summary_mqc.yaml'))
    // ch_multiqc_custom_methods_description = params.multiqc_methods_description ?
    //     file(params.multiqc_methods_description, checkIfExists: true) :
    //     file("$projectDir/assets/methods_description_template.yml", checkIfExists: true)
    // ch_methods_description                = Channel.value(
    //     methodsDescriptionText(ch_multiqc_custom_methods_description))

    // ch_multiqc_files = ch_multiqc_files.mix(ch_collated_versions)
    // ch_multiqc_files = ch_multiqc_files.mix(
    //     ch_methods_description.collectFile(
    //         name: 'methods_description_mqc.yaml',
    //         sort: true
    //     )
    // )

    // MULTIQC (
    //     ch_multiqc_files.collect(),
    //     ch_multiqc_config.toList(),
    //     ch_multiqc_custom_config.toList(),
    //     ch_multiqc_logo.toList(),
    //     [],
    //     []
    // )

    // emit:multiqc_report = MULTIQC.out.report.toList() // channel: /path/to/multiqc_report.html
    // versions       = ch_versions                 // channel: [ path(versions.yml) ]

}

/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    THE END
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
