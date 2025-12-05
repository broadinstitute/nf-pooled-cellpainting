/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPAINTING                  } from '../subworkflows/local/cellpainting'
include { BARCODING                     } from '../subworkflows/local/barcoding'
include { CELLPROFILER_COMBINEDANALYSIS } from '../modules/local/cellprofiler/combinedanalysis/main'
include { MULTIQC                       } from '../modules/nf-core/multiqc/main'

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

    // Process painting arm of pipeline
    CELLPAINTING(
        ch_samplesheet_painting,
        params.painting_illumcalc_cppipe,
        params.painting_illumapply_cppipe,
        params.painting_segcheck_cppipe,
        params.range_skip,
        params.outdir,
        params.fiji_stitchcrop_script,
        params.painting_round_or_square,
        params.painting_quarter_if_round,
        params.painting_overlap_pct,
        params.painting_scalingstring,
        params.painting_imperwell,
        params.painting_rows,
        params.painting_columns,
        params.painting_stitchorder,
        params.tileperside,
        params.final_tile_size,
        params.painting_xoffset_tiles,
        params.painting_yoffset_tiles,
        params.compress,
        params.painting_channame,
        params.qc_painting_passed,
    )
    ch_versions = ch_versions.mix(CELLPAINTING.out.versions)

    // Process barcoding arm of pipeline
    BARCODING(
        ch_samplesheet_barcoding,
        params.barcoding_illumcalc_cppipe,
        params.barcoding_illumapply_cppipe,
        params.barcoding_preprocess_cppipe,
        barcodes,
        params.outdir,
        params.barcoding_illumapply_grouping,
        params.barcoding_shift_threshold,
        params.barcoding_corr_threshold,
        params.acquisition_geometry_rows,
        params.acquisition_geometry_columns,
        params.callbarcodes_plugin,
        params.compensatecolors_plugin,
        params.fiji_stitchcrop_script,
        params.barcoding_round_or_square,
        params.barcoding_quarter_if_round,
        params.barcoding_overlap_pct,
        params.barcoding_scalingstring,
        params.barcoding_imperwell,
        params.barcoding_rows,
        params.barcoding_columns,
        params.barcoding_stitchorder,
        params.tileperside,
        params.final_tile_size,
        params.barcoding_xoffset_tiles,
        params.barcoding_yoffset_tiles,
        params.compress,
        params.barcoding_channame,
        params.qc_barcoding_passed,
    )
    ch_versions = ch_versions.mix(BARCODING.out.versions)

    //// Combined analysis of painting and barcoding data ////
    // Only run if BOTH painting and barcoding QC have been marked as pass
    if (params.qc_painting_passed && params.qc_barcoding_passed) {
        // Combine cropped images from both arms
        CELLPAINTING.out.cropped_images
            .map { meta, images -> [meta + [arm_source: 'cellpainting'], images] }
            .mix(
                BARCODING.out.cropped_images.map { meta, images -> [meta + [arm_source: 'barcoding'], images] }
            )
            .flatMap { meta, images ->
                // Flatten images and associate each image file with its metadata (including arm_source)
                images.collect { img -> [meta, img] }
            }
            .map { meta, image ->
                // Create SIMPLE STRING grouping key for proper groupTuple operation
                def group_key = "${meta.batch}_${meta.plate}_${meta.well}_${meta.site}"
                def group_meta = [
                    batch: meta.batch,
                    plate: meta.plate,
                    well: meta.well,
                    site: meta.site,
                    id: group_key,
                    arm_source: meta.arm_source,
                ]
                [group_key, group_meta, image]
            }
            .groupTuple(by: 0)
            .map { _group_key, meta_list, images_list ->
                // Use first meta (they should all be identical for common fields like batch, plate, well, site)
                def common_meta = meta_list[0]

                // Build image metadata for each image, using the preserved arm_source and existing channel info
                def image_metas = (0..<images_list.size()).collect { i ->
                    def img = images_list[i]
                    def current_meta = meta_list[i]
                    // Get the specific meta for this image
                    def img_meta = [
                        well: common_meta.well,
                        site: common_meta.site,
                        filename: img.name,
                        type: current_meta.arm_source,
                    ]

                    // Add channel and cycle information based on arm_source
                    if (current_meta.arm_source == 'barcoding') {
                        // For barcoding, channels are typically 'DNA' and 'CycleXX'
                        // We need to infer the channel from the filename or assume a default if not explicitly in meta
                        // Assuming channel is part of the filename for barcoding as before, or could be passed in meta
                        def barcode_match = (img.name =~ /Cycle(\d+)_([A-Z]+|DNA|DAPI)\.tiff?$/)
                        if (barcode_match) {
                            img_meta.cycle = barcode_match[0][1] as Integer
                            img_meta.channel = barcode_match[0][2]
                        }
                        else {
                            log.warn("Could not parse cycle/channel for barcoding image: ${img.name}")
                            img_meta.channel = 'unknown'
                        }
                    }
                    else if (current_meta.arm_source == 'cellpainting') {
                        // For painting, channels are typically defined in the samplesheet (meta.channels)
                        // We need to infer the channel from the filename as it's not directly in meta for individual image
                        def cp_match = (img.name =~ /Corr([A-Za-z0-9_]+)\.tiff?$/)
                        if (cp_match) {
                            img_meta.channel = cp_match[0][1]
                        }
                        else {
                            log.warn("Could not parse channel for painting image: ${img.name}")
                            img_meta.channel = 'unknown'
                        }
                    }
                    else {
                        log.warn("Unknown arm_source for image: ${img.name} (arm: ${current_meta.arm_source})")
                        img_meta.channel = 'unknown'
                    }
                    img_meta
                }

                // Prepare metadata structure for combined analysis
                def metadata_for_json = [
                    plate: common_meta.plate,
                    image_metadata: image_metas,
                ]
                // Add optional fields if present
                if (common_meta.batch) {
                    metadata_for_json.batch = common_meta.batch
                }

                [common_meta, images_list, metadata_for_json]
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
    } else {
        log.info "Skipping combined analysis: Both qc_painting_passed (${params.qc_painting_passed}) and qc_barcoding_passed (${params.qc_barcoding_passed}) must be true. Review QC montages for both arms and set both parameters to true to proceed."
    }


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
    ch_multiqc_config = channel.fromPath(
        "${projectDir}/assets/multiqc_config.yml",
        checkIfExists: true
    )
    ch_multiqc_custom_config = params.multiqc_config
        ? channel.fromPath(params.multiqc_config, checkIfExists: true)
        : channel.empty()
    ch_multiqc_logo = params.multiqc_logo
        ? channel.fromPath(params.multiqc_logo, checkIfExists: true)
        : channel.empty()

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
