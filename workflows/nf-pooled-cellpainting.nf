/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { MULTIQC                        } from '../modules/nf-core/multiqc/main'
include { CELLPAINTING                   } from '../subworkflows/local/cellpainting'
include { BARCODING                      } from '../subworkflows/local/barcoding'
include { CELLPROFILER_COMBINEDANALYSIS  } from '../modules/local/cellprofiler/combinedanalysis/main'


include { paramsSummaryMap               } from 'plugin/nf-schema'
include { paramsSummaryMultiqc           } from '../subworkflows/nf-core/utils_nfcore_pipeline'
include { softwareVersionsToYAML         } from '../subworkflows/nf-core/utils_nfcore_pipeline'
include { methodsDescriptionText         } from '../subworkflows/local/utils_nfcore_nf-pooled-cellpainting_pipeline'

/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    RUN MAIN WORKFLOW
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

workflow POOLED_CELLPAINTING {

    take:
    ch_samplesheet           // channel: samplesheet read in from --input
    barcodes                 // file: path to barcodes.csv file

    main:

    ch_versions = Channel.empty()
    // ch_multiqc_files = Channel.empty()

    // Generate barcodes channel from barcodes.csv file
    // ch_barcodes = Channel.fromPath(barcodes, checkIfExists: true)

    ch_samplesheet = ch_samplesheet
        .flatMap { meta, image ->
            // Split channels by comma and create a separate entry for each channel
            meta.original_channels = meta.channels
            meta.remove('original_channels')
            return [[meta, image]]

        }
        .branch { meta, _images ->
            painting: meta.arm == 'painting'
            barcoding: meta.arm == 'barcoding'
        }

    // Add meta.arm back into each channel
    ch_samplesheet_painting = ch_samplesheet.painting.map { meta, image ->
        [meta + [arm: 'painting'], image]
    }
    ch_samplesheet_barcoding = ch_samplesheet.barcoding.map { meta, image ->
        [meta + [arm: 'barcoding'], image]
    }

    // Process cell painting (CP) data
    CELLPAINTING (
        ch_samplesheet_painting,
        params.painting_illumcalc_cppipe,
        params.painting_illumapply_cppipe,
        params.painting_segcheck_cppipe,
        params.range_skip,
    )
    ch_versions = ch_versions.mix(CELLPAINTING.out.versions)

    // Process barcoding (sequencing by synthesis (SBS)) data

    // Run barcoding subworkflow
    BARCODING(
        ch_samplesheet_barcoding,
        params.barcoding_illumcalc_cppipe,
        params.barcoding_illumapply_cppipe,
        params.barcoding_preprocess_cppipe,
        barcodes,
    )
    ch_versions = ch_versions.mix(BARCODING.out.versions)

    //// Combined analysis of CP and SBS data ////

    // Extract site from basename, create new ID (without arm), and group by site
    CELLPAINTING.out.cropped_images
        .mix(BARCODING.out.cropped_images)
        .flatMap { meta, images ->
            images.collect { image ->
                // Updated regex to handle new naming: Site_1 (with underscore)
                def site_match = image.baseName =~ /Site_(\d+)/
                def site = site_match ? site_match[0][1].toInteger() : "unknown"
                def new_meta = meta.subMap(['batch', 'plate', 'well']) + [id: "${meta.batch}_${meta.plate}_${meta.well}_${site}", site: site]
                [new_meta, image]
            }
        }
        .groupTuple()
        .map { meta, images -> [meta, images.flatten()] }
        .set { ch_cropped_images }

    CELLPROFILER_COMBINEDANALYSIS (
        ch_cropped_images,
        params.combinedanalysis_cppipe,
        barcodes,
        Channel.fromPath("${projectDir}/assets/cellprofiler_plugins/callbarcodes.py").collect()  // All Cellprofiler plugins
    )
    ch_versions = ch_versions.mix(CELLPROFILER_COMBINEDANALYSIS.out.versions)
    // Merge load_data CSVs across all samples
    CELLPROFILER_COMBINEDANALYSIS.out.load_data_csv.collectFile(
        name: "combined_analysis.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/"
    )
    

    //
    // Collate and save software versions

    softwareVersionsToYAML(ch_versions)
        .collectFile(
            storeDir: "${params.outdir}/pipeline_info",
            name:  'nf-pooled-cellpainting_software_'  + 'mqc_'  + 'versions.yml',
            newLine: true
        ).set { ch_collated_versions }


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
