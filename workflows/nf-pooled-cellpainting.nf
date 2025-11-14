/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { MULTIQC                       } from '../modules/nf-core/multiqc/main'
include { CELLPAINTING                  } from '../subworkflows/local/cellpainting'
include { BARCODING                     } from '../subworkflows/local/barcoding'
include { CELLPROFILER_COMBINEDANALYSIS } from '../modules/local/cellprofiler/combinedanalysis/main'


include { paramsSummaryMap              } from 'plugin/nf-schema'
include { paramsSummaryMultiqc          } from '../subworkflows/nf-core/utils_nfcore_pipeline'
include { softwareVersionsToYAML        } from '../subworkflows/nf-core/utils_nfcore_pipeline'
include { methodsDescriptionText        } from '../subworkflows/local/utils_nfcore_nf-pooled-cellpainting_pipeline'

/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    RUN MAIN WORKFLOW
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

workflow POOLED_CELLPAINTING {
    take:
    ch_samplesheet // channel: samplesheet read in from --input
    barcodes // file: path to barcodes.csv file

    main:

    ch_versions = Channel.empty()
    ch_multiqc_files = Channel.empty()

    ch_samplesheet = ch_samplesheet
        .flatMap { meta, image ->
            // Split imaging channels by comma and create a separate entry for each channel
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

    // Process painting arm of pipeline
    CELLPAINTING(
        ch_samplesheet_painting,
        params.painting_illumcalc_cppipe,
        params.painting_illumapply_cppipe,
        params.painting_segcheck_cppipe,
        params.range_skip,
    )
    ch_versions = ch_versions.mix(CELLPAINTING.out.versions)

    // Process barcoding arm of pipeline
    BARCODING(
        ch_samplesheet_barcoding,
        params.barcoding_illumcalc_cppipe,
        params.barcoding_illumapply_cppipe,
        params.barcoding_preprocess_cppipe,
        barcodes,
    )
    ch_versions = ch_versions.mix(BARCODING.out.versions)

    //// Combined analysis of painting and barcoding data ////
    // Only run if both painting and barcoding QC have been marked as pass

    // Combine cropped images from both arms
    // Combine cell painting and barcoding cropped images for combined analysis
    // Both subworkflows now output: [ meta (with site), [ images ] ]
    // Group by (batch, plate, well, site) only - NOT arm, since that differs between painting and barcoding
    CELLPAINTING.out.cropped_images
        .mix(BARCODING.out.cropped_images)
        .map { meta, images ->
            // Create SIMPLE STRING grouping key for proper groupTuple operation
            def group_key = "${meta.batch}_${meta.plate}_${meta.well}_${meta.site}"
            def group_meta = [
                batch: meta.batch,
                plate: meta.plate,
                well: meta.well,
                site: meta.site,
                id: group_key,
            ]
            [group_key, group_meta, images]
        }
        .groupTuple(by: 0, size: 2)
        .map { group_key, meta_list, images_lists ->
            // Use first meta (they should all be identical since grouped by same key)
            def meta = meta_list[0]
            // Flatten images from both arms into single list
            def all_images = images_lists.flatten()

            // Build image metadata for each image - parse ONLY cycle/channel from filename
            // Site and well come from metadata (no filename parsing for metadata!)
            def image_metas = all_images.collect { img ->
                // Parse cycle and channel from filename (FIJI_STITCHCROP stable format)
                // Barcoding: Plate_Plate1_Well_A1_Site_3_Cycle01_DNA.tiff
                // Cell painting: Plate_Plate1_Well_A1_Site_3_CorrDNA.tiff
                def barcode_match = (img.name =~ /Cycle(\d+)_([A-Z]+|DNA|DAPI)\.tiff?$/)
                def cp_match = (img.name =~ /Corr([A-Za-z0-9]+)\.tiff?$/)

                if (barcode_match) {
                    // Barcoding image
                    [
                        well: meta.well,
                        site: meta.site,
                        filename: img.name,
                        cycle: barcode_match[0][1] as Integer,
                        channel: barcode_match[0][2],
                        type: 'barcoding',
                    ]
                }
                else if (cp_match) {
                    // Cell painting image
                    [
                        well: meta.well,
                        site: meta.site,
                        filename: img.name,
                        channel: cp_match[0][1],
                        type: 'cellpainting',
                    ]
                }
                else {
                    log.warn("Unknown image type in combined analysis: ${img.name}")
                    [
                        well: meta.well,
                        site: meta.site,
                        filename: img.name,
                        type: 'unknown',
                    ]
                }
            }

            [meta, all_images, image_metas]
        }
        .set { ch_cropped_images }

    CELLPROFILER_COMBINEDANALYSIS(
        ch_cropped_images,
        params.combinedanalysis_cppipe,
        barcodes,
        file(params.callbarcodes_plugin),
    )
    ch_versions = ch_versions.mix(CELLPROFILER_COMBINEDANALYSIS.out.versions)
    // Merge load_data CSVs across all samples
    CELLPROFILER_COMBINEDANALYSIS.out.load_data_csv.collectFile(
        name: "combined_analysis.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/",
    )


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
    ch_multiqc_config = Channel.fromPath(
        "${projectDir}/assets/multiqc_config.yml",
        checkIfExists: true
    )
    ch_multiqc_custom_config = params.multiqc_config
        ? Channel.fromPath(params.multiqc_config, checkIfExists: true)
        : Channel.empty()
    ch_multiqc_logo = params.multiqc_logo
        ? Channel.fromPath(params.multiqc_logo, checkIfExists: true)
        : Channel.empty()

    summary_params = paramsSummaryMap(
        workflow,
        parameters_schema: "nextflow_schema.json"
    )
    ch_workflow_summary = Channel.value(paramsSummaryMultiqc(summary_params))
    ch_multiqc_files = ch_multiqc_files.mix(
        ch_workflow_summary.collectFile(name: 'workflow_summary_mqc.yaml')
    )
    ch_multiqc_custom_methods_description = params.multiqc_methods_description
        ? file(params.multiqc_methods_description, checkIfExists: true)
        : file("${projectDir}/assets/methods_description_template.yml", checkIfExists: true)
    ch_methods_description = Channel.value(
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
        ch_multiqc_files.collect(),
        ch_multiqc_config.toList(),
        ch_multiqc_custom_config.toList(),
        ch_multiqc_logo.toList(),
        [],
        [],
    )

    emit:
    multiqc_report = MULTIQC.out.report.toList() // channel: /path/to/multiqc_report.html
    versions       = ch_versions // channel: [ path(versions.yml) ]
}
