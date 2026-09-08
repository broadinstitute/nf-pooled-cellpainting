/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPAINTING_PRE_STITCH } from '../subworkflows/local/cellpainting_pre_stitch'
include { BARCODING_PRE_STITCH } from '../subworkflows/local/barcoding_pre_stitch'
include { STITCH_ALIGN_CROP_JOINT } from '../subworkflows/local/stitch_align_crop'
include { CELLPROFILER_SEGCHECK } from '../modules/local/cellprofiler/segcheck'
include { CELLPROFILER_PREPROCESS as CELLPROFILER_PREPROCESS_STITCHALIGNCROP } from '../modules/local/cellprofiler/preprocess'
include { CELLPROFILER_COMBINEDANALYSIS } from '../modules/local/cellprofiler/combinedanalysis/main'
include { CELLPROFILER_PLUGINS_UPDATE } from '../modules/local/cellprofiler_plugins/update'
include { QC_MONTAGEILLUM as QC_MONTAGE_SEGCHECK } from '../modules/local/qc/montageillum'
include { QC_PREPROCESS } from '../modules/local/qc/preprocess'
include { QC_CHECKDUPLICATEIMAGES as QC_CHECKDUPLICATES_PREPROCESS_STITCHALIGNCROP } from '../modules/local/qc/checkduplicateimages'
include { MULTIQC } from '../modules/nf-core/multiqc/main'

include { paramsSummaryMap } from 'plugin/nf-schema'
include { paramsSummaryMultiqc } from '../subworkflows/nf-core/utils_nfcore_pipeline'
include { softwareVersionsToYAML } from '../subworkflows/nf-core/utils_nfcore_pipeline'
include { methodsDescriptionText } from '../subworkflows/local/utils_nfcore_nf-pooled-cellpainting_pipeline'
include { buildLoadDataMetadata } from '../subworkflows/local/utils_nfcore_nf-pooled-cellpainting_pipeline'

/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    RUN STITCH_ALIGN_CROP WORKFLOW
    Reorders processing relative to POOLED_CELLPAINTING: illumcalc -> illumapply (no
    post-apply QC) -> per-arm stitch -> within-cycle barcoding alignment -> cross-arm
    alignment (on full stitched wells, before crop) -> per-arm crop -> the existing
    SEGCHECK/PREPROCESS modules, reused as-is -> a single QC gate -> combined analysis.
    Stitch/align/crop run unconditionally; only combined analysis is gated by
    qc_painting_passed/qc_barcoding_passed.
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

workflow STITCH_ALIGN_CROP_POOLED_CELLPAINTING {
    take:
    ch_samplesheet // channel: samplesheet read in from --input
    barcodes // file: path to barcodes.csv file

    main:

    ch_versions = channel.empty()
    ch_multiqc_files = channel.empty()

    // Cellprofiler plugins (shared by segmentation check and combined analysis)
    if (params.update_cellprofiler_plugins) {
        CELLPROFILER_PLUGINS_UPDATE(params.cellprofiler_plugins_repo)
        ch_versions = ch_versions.mix(CELLPROFILER_PLUGINS_UPDATE.out.versions)

        // runcellpose_plugin always takes precedence over the same-named file pulled by the
        // update. callbarcodes_plugin/compensatecolors_plugin only override if the user actually
        // changed them from their defaults - otherwise the freshly-cloned versions pass through.
        def plugin_overrides = [file(params.runcellpose_plugin)]
        if (params.callbarcodes_plugin != params.callbarcodes_plugin_default) {
            plugin_overrides << file(params.callbarcodes_plugin)
        }
        if (params.compensatecolors_plugin != params.compensatecolors_plugin_default) {
            plugin_overrides << file(params.compensatecolors_plugin)
        }
        def override_names = plugin_overrides.collect { it.name }
        ch_cellprofiler_plugins = CELLPROFILER_PLUGINS_UPDATE.out.plugin_files
            .map { cloned_files -> cloned_files.findAll { !(it.name in override_names) } + plugin_overrides }
    }
    else {
        // runcellpose.py is only needed (and only guaranteed to exist) when a Cellpose-enabled flavor is in use.
        ch_cellprofiler_plugins = params.cellprofiler_flavor == 'default'
            ? [file(params.callbarcodes_plugin), file(params.compensatecolors_plugin)]
            : [file(params.callbarcodes_plugin), file(params.compensatecolors_plugin), file(params.runcellpose_plugin)]
    }

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

    // Illumcalc + illumapply only (no post-apply QC, no segcheck/preprocess/stitch yet)
    CELLPAINTING_PRE_STITCH(
        ch_samplesheet_painting,
        params.painting_illumcalc_cppipe,
        params.painting_illumapply_cppipe,
        params.outdir,
    )
    ch_versions = ch_versions.mix(CELLPAINTING_PRE_STITCH.out.versions)

    BARCODING_PRE_STITCH(
        ch_samplesheet_barcoding,
        params.barcoding_illumcalc_cppipe,
        params.barcoding_illumapply_cppipe,
        params.outdir,
        params.barcoding_illumapply_grouping,
    )
    ch_versions = ch_versions.mix(BARCODING_PRE_STITCH.out.versions)

    // Stitch (per arm) -> align barcoding cycles -> align across arms -> crop (per arm)
    STITCH_ALIGN_CROP_JOINT(
        CELLPAINTING_PRE_STITCH.out.corrected_images_by_well,
        BARCODING_PRE_STITCH.out.corrected_images_by_well,
        params.painting_round_or_square,
        params.painting_quarter_if_round,
        params.painting_overlap_pct,
        params.painting_scalingstring,
        params.painting_imperwell,
        params.painting_rows,
        params.painting_columns,
        params.painting_stitchorder,
        params.compress,
        params.phenix,
        params.painting_channame,
        params.barcoding_round_or_square,
        params.barcoding_quarter_if_round,
        params.barcoding_overlap_pct,
        params.barcoding_scalingstring,
        params.barcoding_imperwell,
        params.barcoding_rows,
        params.barcoding_columns,
        params.barcoding_stitchorder,
        params.barcoding_channame,
        params.tileperside,
        params.final_tile_size,
        params.barcoding_shift_threshold,
        params.barcoding_corr_threshold,
    )
    ch_versions = ch_versions.mix(STITCH_ALIGN_CROP_JOINT.out.versions)

    //// Painting: regroup cropped per-site images by well (range_skip subsampling happens inside SEGCHECK) ////
    ch_sub_corr_images = STITCH_ALIGN_CROP_JOINT.out.painting_cropped_images
        .map { meta, images ->
            def well_key = [
                batch: meta.batch,
                plate: meta.plate,
                well: meta.well,
                arm: meta.arm,
                id: "${meta.batch}_${meta.plate}_${meta.well}",
            ]
            // segcheck's cppipe selects input images by bare channel name (DNA,
            // Phalloidin, CHN2), so column_prefix is empty. No cycle: segcheck
            // operates on a single painting cycle's cropped images.
            def image_metas = [images].flatten().collect { img ->
                // Extract channel from cropped image filename: Plate_X_Well_Y_Site_Z_CorrCHANNEL.tiff
                def channel = img.name.replaceAll(/.*_Corr(.+?)\.tiff?$/, '$1')
                [
                    well         : meta.well,
                    site         : meta.site,
                    arm          : meta.arm,
                    cycle        : null,
                    channel      : channel,
                    frame_index  : null,
                    column_prefix: '',
                    filename     : img.name,
                    original_path: "${params.outdir}/images/${meta.batch}/images_corrected_cropped/${meta.arm}/${meta.plate}/${meta.plate}-${meta.well}/${img.name}",
                ]
            }
            [well_key, meta.site, images, image_metas]
        }
        .groupTuple()
        .map { well_meta, _site_list, images_list, image_metas_list ->
            def flat_images = images_list.flatten().sort { img -> img.name }
            def flat_metas = image_metas_list.flatten().sort { m -> m.filename }
            [well_meta, flat_images, buildLoadDataMetadata(well_meta, flat_metas)]
        }

    CELLPROFILER_SEGCHECK(
        ch_sub_corr_images,
        params.painting_segcheck_cppipe,
        params.range_skip,
        ch_cellprofiler_plugins,
    )
    ch_versions = ch_versions.mix(CELLPROFILER_SEGCHECK.out.versions)
    // Merge load_data CSVs per plate
    CELLPROFILER_SEGCHECK.out.load_data_csv.collectFile(keepHeader: true, skip: 1) { meta, csv ->
        def dir = file("${params.outdir}/workspace/load_data_csv/${meta.batch}/${meta.plate}")
        dir.mkdirs()
        [
            "${dir}/painting-segcheck.load_data.csv",
            csv.text.replaceFirst(/(?m)^(.*)$/) { line ->
                line[0]
                    .replace('FinalFileName_', '__FINAL__')
                    .replace('FileName_', 'StagedFileName_')
                    .replace('__FINAL__', 'FileName_')
            },
        ]
    }

    // Reshape CELLPROFILER_SEGCHECK output for QC montage
    ch_segcheck_qc = CELLPROFILER_SEGCHECK.out.segcheck_res
        .map { meta, _csv_files, png_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "painting"], png_files]
        }
        .groupTuple()
        .map { meta, png_files_list ->
            [meta, png_files_list.flatten().sort { it -> it.name }]
        }

    QC_MONTAGE_SEGCHECK(
        ch_segcheck_qc,
        ".*\\.png\$",
    )
    ch_versions = ch_versions.mix(QC_MONTAGE_SEGCHECK.out.versions)

    //// Barcoding: build image_metas for cropped per-site images (already per-site) ////
    ch_sbs_corr_images = STITCH_ALIGN_CROP_JOINT.out.barcoding_cropped_images
        .map { meta, images ->
            // preprocess's cppipe selects input images named Cycle{NN}_{channel} -
            // bare channel name, cycle prefix added by generate_load_data_csv.py
            // from the cycles list.
            def image_metas = [images].flatten().collect { img ->
                // Extract cycle and channel from cropped image filename: Plate_X_Well_Y_Site_Z_CycleNN_CHANNEL.tiff
                def cycle_channel_match = (img.name =~ /.*_Cycle(\d+)_(.+?)\.tiff?$/)
                def cycle = cycle_channel_match ? cycle_channel_match[0][1] as Integer : null
                def channel = cycle_channel_match ? cycle_channel_match[0][2] : 'UNKNOWN'
                [
                    well         : meta.well,
                    site         : meta.site,
                    arm          : meta.arm,
                    cycle        : cycle,
                    channel      : channel,
                    frame_index  : null,
                    column_prefix: '',
                    filename     : img.name,
                    original_path: "${params.outdir}/images/${meta.batch}/images_corrected_cropped/${meta.arm}/${meta.plate}/${meta.plate}-${meta.well}/${img.name}",
                ]
            }
            [meta, images, buildLoadDataMetadata(meta, image_metas)]
        }

    CELLPROFILER_PREPROCESS_STITCHALIGNCROP(
        ch_sbs_corr_images,
        params.barcoding_preprocess_cppipe,
        barcodes,
        ch_cellprofiler_plugins,
    )
    ch_versions = ch_versions.mix(CELLPROFILER_PREPROCESS_STITCHALIGNCROP.out.versions)
    // Merge load_data CSVs per plate
    CELLPROFILER_PREPROCESS_STITCHALIGNCROP.out.load_data_csv.collectFile(keepHeader: true, skip: 1) { meta, csv ->
        def dir = file("${params.outdir}/workspace/load_data_csv/${meta.batch}/${meta.plate}")
        dir.mkdirs()
        [
            "${dir}/barcoding-preprocess.load_data.csv",
            csv.text.replaceFirst(/(?m)^(.*)$/) { line ->
                line[0]
                    .replace('FinalFileName_', '__FINAL__')
                    .replace('FileName_', 'StagedFileName_')
                    .replace('__FINAL__', 'FileName_')
            },
        ]
    }

    // Fail the pipeline if any two preprocessed .tiff images for this plate
    // are pixel-identical - a safety net against staging/matching bugs that
    // silently reuse one physical image where a different one should have
    // been produced.
    ch_preprocessed_images_dedup_qc = CELLPROFILER_PREPROCESS_STITCHALIGNCROP.out.preprocessed_images
        .map { meta, tiff_files -> [meta.subMap(['batch', 'plate']) + [arm: "barcoding"], tiff_files] }
        .groupTuple()
        .map { meta, tiff_files_list -> [meta, tiff_files_list.flatten()] }

    QC_CHECKDUPLICATES_PREPROCESS_STITCHALIGNCROP(
        ch_preprocessed_images_dedup_qc,
    )
    ch_versions = ch_versions.mix(QC_CHECKDUPLICATES_PREPROCESS_STITCHALIGNCROP.out.versions)

    // First, collect cycle information from the samplesheet to infer num_cycles
    ch_plate_cycles = ch_samplesheet_barcoding
        .map { meta, _image ->
            def plate_key = [batch: meta.batch, plate: meta.plate]
            [plate_key, meta.cycle]
        }
        .groupTuple()
        .map { plate_key, cycles ->
            [plate_key, cycles.unique().max()]
        }

    //// QC: Barcode preprocessing (barcode calling) ////
    ch_preprocess_qc_input = CELLPROFILER_PREPROCESS_STITCHALIGNCROP.out.preprocess_stats
        .map { meta, csv_files ->
            def plate_key = [batch: meta.batch, plate: meta.plate]
            def image_csv = csv_files.find { file -> file.name.contains('BarcodePreprocessing_Foci.csv') }
            [plate_key, meta.well, image_csv]
        }
        .groupTuple()
        .combine(ch_plate_cycles, by: 0)
        .map { plate_key, wells, csvs, num_cycles ->
            def qc_meta = plate_key + [arm: "barcoding", id: "${plate_key.batch}_${plate_key.plate}"]
            [qc_meta, wells.unique(), csvs, num_cycles]
        }

    QC_PREPROCESS(
        ch_preprocess_qc_input,
        file("${projectDir}/bin/qc_barcode_preprocess.py"),
        barcodes,
        params.acquisition_geometry_rows,
        params.acquisition_geometry_columns,
    )
    ch_versions = ch_versions.mix(QC_PREPROCESS.out.versions)

    //// Combined analysis of painting and barcoding data ////
    // Only run if BOTH painting and barcoding QC have been marked as pass.
    // This is the ONLY qc gate in this entrypoint - stitch/align/crop above always run.
    if (params.qc_painting_passed && params.qc_barcoding_passed) {
        // Combine cropped images from both arms (the same images SEGCHECK/PREPROCESS
        // consumed - those modules are QC/preprocessing side steps, not combined
        // analysis' input; POOLED_CELLPAINTING and NO_STITCH_POOLED_CELLPAINTING both
        // source combined analysis this same way, from the stage feeding the QC gate).
        STITCH_ALIGN_CROP_JOINT.out.painting_cropped_images
            .map { meta, images -> [meta + [arm_source: 'cellpainting'], images] }
            .mix(
                STITCH_ALIGN_CROP_JOINT.out.barcoding_cropped_images.map { meta, images -> [meta + [arm_source: 'barcoding'], images] }
            )
            .flatMap { meta, images ->
                // Flatten images and associate each image file with its metadata (including arm_source).
                // Wrap-then-flatten guards against Nextflow emitting a bare Path (not a List) when a
                // glob output matches exactly one file -- Path implements Iterable<Path> over its
                // filesystem name components, so calling .collect directly on it silently iterates
                // path segments instead of images.
                [images].flatten().collect { img -> [meta, img] }
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

                // Build image metadata for each image, using the preserved arm_source and existing channel info.
                // `arm` uses the samplesheet's painting/barcoding vocabulary, replacing
                // the ad hoc `type: cellpainting/barcoding` this block used to emit.
                // combined_analysis.cppipe selects CorrDNA/CorrCHN2/CorrPhalloidin for
                // painting and Cycle01_DNA/Cycle01_A/... for barcoding.
                def image_metas = (0..<images_list.size()).collect { i ->
                    def img = images_list[i]
                    def current_meta = meta_list[i]
                    def arm = current_meta.arm_source == 'cellpainting' ? 'painting' : 'barcoding'
                    def img_meta = [
                        well         : common_meta.well,
                        site         : common_meta.site,
                        arm          : arm,
                        cycle        : null,
                        frame_index  : null,
                        column_prefix: arm == 'painting' ? 'Corr' : '',
                        filename     : img.name,
                        original_path: "${params.outdir}/images/${common_meta.batch}/images_corrected_cropped/${arm}/${common_meta.plate}/${common_meta.plate}-${common_meta.well}/${img.name}",
                    ]

                    // Add channel and cycle information based on arm_source
                    if (current_meta.arm_source == 'barcoding') {
                        def barcode_match = (img.name =~ /Cycle(\d+)_(A488|A568|A647|DNA|DAPI|[ACGT])(?:_Site_\d+)?\.tiff?$/)
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

                [common_meta, images_list, buildLoadDataMetadata(common_meta, image_metas)]
            }
            .set { ch_cropped_images }

        CELLPROFILER_COMBINEDANALYSIS(
            ch_cropped_images,
            params.combinedanalysis_cppipe,
            barcodes,
            ch_cellprofiler_plugins,
        )
        ch_versions = ch_versions.mix(CELLPROFILER_COMBINEDANALYSIS.out.versions)

        // Merge load_data CSVs per plate
        CELLPROFILER_COMBINEDANALYSIS.out.load_data_csv.collectFile(keepHeader: true, skip: 1) { meta, csv ->
            def dir = file("${params.outdir}/workspace/load_data_csv/${meta.batch}/${meta.plate}")
            dir.mkdirs()
            [
                "${dir}/combined_analysis.load_data.csv",
                csv.text.replaceFirst(/(?m)^(.*)$/) { line ->
                    line[0]
                        .replace('FinalFileName_', '__FINAL__')
                        .replace('FileName_', 'StagedFileName_')
                        .replace('__FINAL__', 'FileName_')
                },
            ]
        }
    }
    else {
        log.info("Skipping combined analysis: Both qc_painting_passed (${params.qc_painting_passed}) and qc_barcoding_passed (${params.qc_barcoding_passed}) must be true. Review QC montages for both arms and set both parameters to true to proceed.")
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
