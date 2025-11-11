/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPROFILER_ILLUMCALC }                                                    from '../../../modules/local/cellprofiler/illumcalc'
include { QC_MONTAGEILLUM as QC_MONTAGEILLUM_BARCODING }                                       from '../../../modules/local/qc/montageillum'
include { QC_MONTAGEILLUM as QC_MONTAGE_STITCHCROP_BARCODING }                        from '../../../modules/local/qc/montageillum'
include { CELLPROFILER_ILLUMAPPLY as CELLPROFILER_ILLUMAPPLY_BARCODING }              from '../../../modules/local/cellprofiler/illumapply'
include { CELLPROFILER_PREPROCESS }                                                   from '../../../modules/local/cellprofiler/preprocess'
include { QC_PREPROCESS }                                                             from '../../../modules/local/qc/preprocess'
include { FIJI_STITCHCROP }                                                           from '../../../modules/local/fiji/stitchcrop'
include { QC_BARCODEALIGN }                                                           from '../../../modules/local/qc/barcodealign'

workflow BARCODING {

    take:
    ch_samplesheet_sbs
    barcoding_illumcalc_cppipe
    barcoding_illumapply_cppipe
    barcoding_preprocess_cppipe
    barcodes

    main:
    ch_versions = channel.empty()
    ch_cropped_images = channel.empty()

    ////==========================================================================
    //// PARALLELIZATION STRATEGY OVERVIEW
    ////==========================================================================
    // This workflow processes barcoding images through several steps, each with
    // different parallelization granularity:
    //
    // 1. ILLUMCALC:  batch, plate, cycle, channels
    //    - One job per plate per cycle per channel set
    //
    // 2. ILLUMAPPLY: batch, plate, well
    //    - One job per well (processes all cycles/sites together)
    //
    // 3. PREPROCESS: batch, plate, well, site
    //    - One job per site (splits well-level output from ILLUMAPPLY)
    //    - See detailed comments at PREPROCESS section below for how to change this
    //
    // 4. STITCHCROP: batch, plate, well, site
    //    - One job per site (inherits from PREPROCESS)
    ////==========================================================================

    // Group images by batch, plate, cycle, and channels for illumination calculation
    ch_samplesheet_sbs
        .map { meta, image ->
            def group_key = [
                batch: meta.batch,
                plate: meta.plate,
                cycle: meta.cycle,
                channels: meta.channels,
                id: "${meta.batch}_${meta.plate}_${meta.cycle}_${meta.channels}"
            ]
            [group_key, image]
        }
        .groupTuple()
        .map { meta, images ->
            // Get unique images
            def unique_images = images.unique()
            [meta, meta.channels, meta.cycle, unique_images]
        }
        .set { ch_illumcalc_input }

    CELLPROFILER_ILLUMCALC (
        ch_illumcalc_input,
        barcoding_illumcalc_cppipe,
        true  // has_cycles = true for barcoding
    )
    ch_versions = ch_versions.mix(CELLPROFILER_ILLUMCALC.out.versions)
    // Merge load_data CSVs across all samples
    CELLPROFILER_ILLUMCALC.out.load_data_csv.collectFile(
        name: "barcoding-illumcalc.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/"
    )

    //// QC illumination correction profiles ////
    CELLPROFILER_ILLUMCALC.out.illumination_corrections
        .map{ meta, npy_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "barcoding"], npy_files]
        }
        .groupTuple()
        .map{ meta, npy_files_list ->
            [meta, npy_files_list.flatten()]
        }
        .set { ch_illumination_corrections_qc }

    QC_MONTAGEILLUM_BARCODING (
        ch_illumination_corrections_qc,
        ".*Cycle.*\\.npy\$"  // Pattern for barcoding: files with Cycle in name
    )
    ch_versions = ch_versions.mix(QC_MONTAGEILLUM_BARCODING.out.versions)

    // Group images by well for ILLUMAPPLY, preserving full metadata for each image
    // Keep all original meta maps so we can use them after ILLUMAPPLY
    ch_samplesheet_sbs
        .map { meta, image ->
            def well_key = [
                batch: meta.batch,
                plate: meta.plate,
                well: meta.well,
                channels: meta.channels,
                arm: meta.arm,
                id: "${meta.batch}_${meta.plate}_${meta.well}"
            ]
            // Keep full meta alongside image
            [well_key, [image: image, meta: meta]]
        }
        .groupTuple()
        .map { well_meta, image_meta_list ->
            // Extract images and cycles for ILLUMAPPLY
            def images = image_meta_list.collect { it.image }.unique()
            def cycles = image_meta_list.collect { it.meta.cycle }.unique().sort()

            // Keep all the original metadata maps
            def image_metas = image_meta_list.collect { it.meta }

            [well_meta, well_meta.channels, cycles, images, image_metas]
        }
        .set { ch_images_by_well_with_metas }

    // Group npy files by batch and plate
    // All wells in a plate share the same illumination correction files
    CELLPROFILER_ILLUMCALC.out.illumination_corrections
        .map { meta, npy_files ->
            def group_key = [
                batch: meta.batch,
                plate: meta.plate
            ]
            [group_key, npy_files]
        }
        .groupTuple()
        .map { meta, npy_files_list ->
            [meta, npy_files_list.flatten()]
        }
        .set { ch_npy_by_plate }

    // Combine images with npy files
    // Each well gets all the npy files for its plate
    ch_images_by_well_with_metas
        .map { well_meta, channels, cycles, images, image_metas ->
            def plate_key = [
                batch: well_meta.batch,
                plate: well_meta.plate
            ]
            [plate_key, well_meta, channels, cycles, images, image_metas]
        }
        .combine(ch_npy_by_plate, by: 0)
        .map { _plate_key, well_meta, channels, cycles, images, image_metas, npy_files ->
            [
                [well_meta, channels, cycles, images, npy_files],  // ILLUMAPPLY input
                [well_meta, image_metas]  // All original metadata to pass through
            ]
        }
        .multiMap { illumapply_input, meta_passthrough ->
            illumapply: illumapply_input
            metas: meta_passthrough
        }
        .set { ch_split_for_illumapply }

    CELLPROFILER_ILLUMAPPLY_BARCODING (
        ch_split_for_illumapply.illumapply,
        barcoding_illumapply_cppipe,
        true  // has_cycles = true for barcoding
    )
    ch_versions = ch_versions.mix(CELLPROFILER_ILLUMAPPLY_BARCODING.out.versions)
    // Merge load_data CSVs across all samples
    CELLPROFILER_ILLUMAPPLY_BARCODING.out.load_data_csv.collectFile(
        name: "barcoding-illumapply.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/"
    )

    // QC of barcode alignment
    // First, collect cycle information from the samplesheet to infer num_cycles
    ch_samplesheet_sbs
        .map { meta, _image ->
            def plate_key = [
                batch: meta.batch,
                plate: meta.plate
            ]
            [plate_key, meta.cycle]
        }
        .groupTuple()
        .map { plate_key, cycles ->
            def num_cycles = cycles.unique().max()
            [plate_key, num_cycles]
        }
        .set { ch_plate_cycles }

    // Group CSV files by plate for QC analysis, keeping well-CSV correspondence
    CELLPROFILER_ILLUMAPPLY_BARCODING.out.corrected_images
        .map { meta, _images, csv_files ->
            def plate_key = [
                batch: meta.batch,
                plate: meta.plate
            ]
            // Find the BarcodingApplication_Image.csv file
            def image_csv = csv_files.find { file -> file.name.contains('Image.csv') }
            [plate_key, meta.well, image_csv]
        }
        .groupTuple()
        .combine(ch_plate_cycles, by: 0)
        .map { plate_key, wells, csv_files, num_cycles ->
            def qc_meta = plate_key + [
                arm: "barcoding",
                id: "${plate_key.batch}_${plate_key.plate}"
            ]
            [qc_meta, wells, csv_files, num_cycles]
        }
        .set { ch_qc_barcode_input }

    QC_BARCODEALIGN (
        ch_qc_barcode_input,
        file("${projectDir}/bin/qc_barcode_align.py"),
        params.barcoding_shift_threshold,
        params.barcoding_corr_threshold,
        params.acquisition_geometry_rows,
        params.acquisition_geometry_columns
    )
    ch_versions = ch_versions.mix(QC_BARCODEALIGN.out.versions)

    ////==========================================================================
    //// PREPROCESS PARALLELIZATION: Split well-level jobs into site-level jobs
    ////==========================================================================
    // CURRENT GROUPING: batch, plate, well, site
    // This creates separate PREPROCESS jobs for each site within a well
    //
    // TO CHANGE PARALLELIZATION:
    // - For well-level (coarser): Remove the site-splitting logic below and use:
    //     CELLPROFILER_ILLUMAPPLY_BARCODING.out.corrected_images.map{ meta, images, _csv -> [meta, images] }
    // - For plate-level: Also change ILLUMAPPLY grouping to batch,plate
    // - For even finer: Could add channel-level or cycle-level splitting
    ////==========================================================================

    // Split ILLUMAPPLY output (grouped by well) into separate jobs per site
    // Use the preserved metadata from samplesheet to know which sites exist
    CELLPROFILER_ILLUMAPPLY_BARCODING.out.corrected_images
        .map { well_meta, images, _csv ->
            def well_key = [
                batch: well_meta.batch,
                plate: well_meta.plate,
                well: well_meta.well
            ]
            [well_key, well_meta, images]
        }
        .join(
            ch_split_for_illumapply.metas.map { well_meta, image_metas ->
                def well_key = [
                    batch: well_meta.batch,
                    plate: well_meta.plate,
                    well: well_meta.well
                ]
                [well_key, image_metas]
            }
        )
        .flatMap { _well_key, well_meta, images, image_metas ->
            // image_metas contains all original metadata maps from samplesheet
            // Each has site, cycle, and all other metadata

            // Get valid sites from samplesheet metadata (source of truth)
            def valid_sites = image_metas.collect { meta -> meta.site }.unique().sort()

            // Detect if there's an indexing offset between samplesheet and ILLUMAPPLY output
            // Samplesheet might use 1-indexed (1,2,3,4) while ILLUMAPPLY uses 0-indexed (0,1,2,3)
            def min_samplesheet_site = valid_sites.min()
            def site_offset = min_samplesheet_site // If min is 1, offset is 1; if min is 0, offset is 0

            // Group images by site using metadata as source of truth
            def images_by_site = [:].withDefault { [] }

            // Group images by extracted site, mapping to samplesheet site values
            images.each { img ->
                // Extract site from filename (ILLUMAPPLY output includes site in filename)
                def site_matcher = img.name =~ /Site_(\d+)/
                if (site_matcher.find()) {
                    def filename_site = site_matcher.group(1).toInteger()

                    // Convert filename site to samplesheet site (handle 0-indexing vs 1-indexing)
                    def samplesheet_site = filename_site + site_offset

                    // Validate that this site exists in samplesheet metadata (source of truth)
                    if (valid_sites.contains(samplesheet_site)) {
                        images_by_site[samplesheet_site] << img
                    } else {
                        log.warn "PREPROCESS: Image ${img.name} has filename site ${filename_site} (maps to ${samplesheet_site}), but samplesheet only has: ${valid_sites.join(', ')}"
                    }
                } else {
                    log.warn "PREPROCESS: Could not extract site from filename: ${img.name}"
                }
            }

            // Create separate channel emissions for each site found in metadata
            def site_jobs = images_by_site.collect { site, site_images ->
                def site_meta = well_meta.clone()
                site_meta.site = site
                site_meta.id = "${well_meta.id}_Site${site}"
                [site_meta, site_images]
            }

            log.info "PREPROCESS: Split ${well_meta.id} into ${site_jobs.size()} site-level jobs (sites: ${images_by_site.keySet().sort().join(', ')}) - samplesheet has sites: ${valid_sites.join(', ')}"
            return site_jobs
        }
        .set { ch_sbs_corr_images }

    //// Barcoding preprocessing ////
    CELLPROFILER_PREPROCESS (
        ch_sbs_corr_images,
        barcoding_preprocess_cppipe,
        barcodes,
        channel.fromPath([params.callbarcodes_plugin, params.compensatecolors_plugin]).collect()  // CellProfiler plugins
    )
    ch_versions = ch_versions.mix(CELLPROFILER_PREPROCESS.out.versions)
    // Merge load_data CSVs across all samples
    CELLPROFILER_PREPROCESS.out.load_data_csv.collectFile(
        name: "barcoding-preprocess.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/"
    )

    //// QC: Barcode preprocessing ////
    // Group preprocessing stats by plate and collect wells
    CELLPROFILER_PREPROCESS.out.preprocess_stats
        .map { meta, csv_files ->
            def plate_key = [
                batch: meta.batch,
                plate: meta.plate
            ]
            // Find the BarcodePreprocess_Image.csv file
            def image_csv = csv_files.find { file -> file.name.contains('BarcodePreprocessing_Foci.csv') }
            [plate_key, meta.well, image_csv]
        }
        .groupTuple()
        .combine(ch_plate_cycles, by: 0)
        .map { plate_key, wells, csvs, num_cycles ->
            def qc_meta = plate_key + [
                arm: "barcoding",
                id: "${plate_key.batch}_${plate_key.plate}"
            ]
            [qc_meta, wells, csvs, num_cycles]
        }
        .set { ch_preprocess_qc_input }

    QC_PREPROCESS (
        ch_preprocess_qc_input,
        file("${projectDir}/bin/qc_barcode_preprocess.py"),
        barcodes,
        params.acquisition_geometry_rows,
        params.acquisition_geometry_columns
    )
    ch_versions = ch_versions.mix(QC_PREPROCESS.out.versions)

    if (params.qc_barcoding_passed) {
        // STITCH & CROP IMAGES ////
        // PREPROCESS outputs are per site, but STITCHCROP needs all sites together per well
        // Re-group by well before stitching
        CELLPROFILER_PREPROCESS.out.preprocessed_images
            .map { meta, images ->
                // Create well key (without site)
                def well_key = [
                    batch: meta.batch,
                    plate: meta.plate,
                    well: meta.well,
                    channels: meta.channels,
                    arm: meta.arm,
                    id: "${meta.batch}_${meta.plate}_${meta.well}"
                ]
                [well_key, images]
            }
            .groupTuple()
            .map { well_meta, images_list ->
                // Flatten all site images into one list for the well
                [well_meta, images_list.flatten()]
            }
            .set { ch_preprocess_by_well }

        FIJI_STITCHCROP (
            ch_preprocess_by_well,
            file("${projectDir}/bin/stitch_crop.py")
        )
        ch_cropped_images = FIJI_STITCHCROP.out.cropped_images
        ch_versions = ch_versions.mix(FIJI_STITCHCROP.out.versions)

        // QC montage for stitchcrop results
        FIJI_STITCHCROP.out.downsampled_images
            .map{ meta, tiff_files ->
                [meta.subMap(['batch', 'plate']) + [arm: "barcoding"], tiff_files]
            }
            .groupTuple()
            .map{ meta, tiff_files_list ->
                [meta, tiff_files_list.flatten()]
            }
            .set { ch_stitchcrop_qc }

        QC_MONTAGE_STITCHCROP_BARCODING (
            ch_stitchcrop_qc,
            ".*\\.tiff\$"  // Pattern for stitchcrop: all TIFF files
        )
        ch_versions = ch_versions.mix(QC_MONTAGE_STITCHCROP_BARCODING.out.versions)

    } else {
        log.info "Stopping before FIJI_STITCHCROP for barcoding arm: QC not passed (params.qc_barcoding_passed = false). Perform QC for barcoding assay and set qc_barcoding_passed=true to proceed."
    }

    emit:
    cropped_images  = ch_cropped_images // channel: [ val(meta), [ cropped_images ] ]
    versions                  = ch_versions       // channel: [ versions.yml ]
}
