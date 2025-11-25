/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPROFILER_ILLUMCALC } from '../../../modules/local/cellprofiler/illumcalc'
include { QC_MONTAGEILLUM as QC_MONTAGEILLUM_BARCODING } from '../../../modules/local/qc/montageillum'
include { QC_MONTAGEILLUM as QC_MONTAGE_STITCHCROP_BARCODING } from '../../../modules/local/qc/montageillum'
include { CELLPROFILER_ILLUMAPPLY as CELLPROFILER_ILLUMAPPLY_BARCODING } from '../../../modules/local/cellprofiler/illumapply'
include { CELLPROFILER_PREPROCESS } from '../../../modules/local/cellprofiler/preprocess'
include { QC_PREPROCESS } from '../../../modules/local/qc/preprocess'
include { FIJI_STITCHCROP } from '../../../modules/local/fiji/stitchcrop'
include { QC_BARCODEALIGN } from '../../../modules/local/qc/barcodealign'

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

    // Group images by batch, plate, and cycle for illumination calculation
    // All channels for a given cycle are processed together
    ch_illumcalc_input = ch_samplesheet_sbs
        .map { meta, image ->
            def group_id = "${meta.batch}_${meta.plate}_${meta.cycle}"
            def group_key = meta.subMap(['batch', 'plate', 'cycle']) + [id: group_id]

            // Preserve full metadata for each image
            def image_meta = meta + [filename: image.name]

            [group_key, image_meta, image]
        }
        .groupTuple()
        .map { meta, images_meta_list, images_list ->
            def all_channels = images_meta_list[0].channels
            // Return tuple: (shared meta, channels, cycle, images, per-image metadata)
            [meta, all_channels, meta.cycle, images_list, images_meta_list]
        }

    CELLPROFILER_ILLUMCALC(
        ch_illumcalc_input,
        barcoding_illumcalc_cppipe,
        true,
    )
    ch_versions = ch_versions.mix(CELLPROFILER_ILLUMCALC.out.versions)
    // Merge load_data CSVs across all samples
    CELLPROFILER_ILLUMCALC.out.load_data_csv.collectFile(
        name: "barcoding-illumcalc.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/",
    )

    //// QC illumination correction profiles ////
    ch_illumination_corrections_qc = CELLPROFILER_ILLUMCALC.out.illumination_corrections
        .map { meta, npy_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "barcoding"], npy_files]
        }
        .groupTuple()
        .map { meta, npy_files_list ->
            [meta, npy_files_list.flatten()]
        }

    QC_MONTAGEILLUM_BARCODING(
        ch_illumination_corrections_qc,
        ".*Cycle.*\\.npy\$",
    )
    ch_versions = ch_versions.mix(QC_MONTAGEILLUM_BARCODING.out.versions)

    // Group images for ILLUMAPPLY based on parameter setting
    // Two modes:
    //   - "site": Group by site (current behavior) - each site processed separately
    //   - "well": Group by well (new behavior) - all sites in a well processed together
    // Site information is always preserved in image metadata for downstream preprocessing
    ch_images_by_site = ch_samplesheet_sbs
        .map { meta, image ->
            // Determine grouping key based on parameter
            def group_key
            def group_id

            if (params.barcoding_illumapply_grouping == "site") {
                // Site-level grouping (current behavior)
                group_key = meta.subMap(['batch', 'plate', 'well', 'site', 'arm'])
                group_id = "${meta.batch}_${meta.plate}_${meta.well}_Site${meta.site}"
            }
            else {
                // Well-level grouping (new behavior)
                // Site is NOT in the grouping key, but preserved in image metadata
                group_key = meta.subMap(['batch', 'plate', 'well', 'arm'])
                group_id = "${meta.batch}_${meta.plate}_${meta.well}"
            }

            // Preserve full metadata for each image (including site)
            def image_meta = meta.clone()
            image_meta.filename = image.name

            [group_key + [id: group_id], image_meta, image]
        }
        .groupTuple()
        .map { group_meta, images_meta_list, images_list ->
            // Get unique cycles and channels for this group
            // For barcoding, we expect multiple cycles
            def all_cycles = images_meta_list.collect { m -> m.cycle }.findAll { c -> c != null }.unique().sort()
            def unique_cycles = all_cycles.size() > 1 ? all_cycles : null
            def all_channels = images_meta_list[0].channels

            // Return tuple: (shared meta, channels, cycles, images, per-image metadata)
            [group_meta, all_channels, unique_cycles, images_list, images_meta_list]
        }

    // Group npy files by batch and plate
    // All wells in a plate share the same illumination correction files
    ch_npy_by_plate = CELLPROFILER_ILLUMCALC.out.illumination_corrections
        .map { meta, npy_files ->
            def group_key = [
                batch: meta.batch,
                plate: meta.plate,
            ]
            [group_key, npy_files]
        }
        .groupTuple()
        .map { meta, npy_files_list ->
            [meta, npy_files_list.flatten()]
        }

    // Combine images with npy files
    // Each site gets all the npy files for its plate
    ch_illumapply_input = ch_images_by_site
        .map { site_meta, channels, cycles, images, image_metas ->
            def plate_key = [
                batch: site_meta.batch,
                plate: site_meta.plate,
            ]
            [plate_key, site_meta, channels, cycles, images, image_metas]
        }
        .combine(ch_npy_by_plate, by: 0)
        .map { _plate_key, site_meta, channels, cycles, images, image_metas, npy_files ->
            [site_meta, channels, cycles, images, image_metas, npy_files]
        }

    CELLPROFILER_ILLUMAPPLY_BARCODING(
        ch_illumapply_input,
        barcoding_illumapply_cppipe,
        true,
    )
    ch_versions = ch_versions.mix(CELLPROFILER_ILLUMAPPLY_BARCODING.out.versions)
    // Merge load_data CSVs across all samples
    CELLPROFILER_ILLUMAPPLY_BARCODING.out.load_data_csv.collectFile(
        name: "barcoding-illumapply.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/",
    )

    // QC of barcode alignment
    // First, collect cycle information from the samplesheet to infer num_cycles
    ch_plate_cycles = ch_samplesheet_sbs
        .map { meta, _image ->
            def plate_key = [
                batch: meta.batch,
                plate: meta.plate,
            ]
            [plate_key, meta.cycle]
        }
        .groupTuple()
        .map { plate_key, cycles ->
            def num_cycles = cycles.unique().max()
            [plate_key, num_cycles]
        }

    // Group CSV files by plate for QC analysis, keeping well-CSV correspondence
    ch_qc_barcode_input = CELLPROFILER_ILLUMAPPLY_BARCODING.out.corrected_images
        .map { meta, _images, csv_files ->
            def plate_key = [
                batch: meta.batch,
                plate: meta.plate,
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
                id: "${plate_key.batch}_${plate_key.plate}",
            ]
            // Remove duplicate wells since we now have site-level data
            def unique_wells = wells.unique()
            [qc_meta, unique_wells, csv_files, num_cycles]
        }

    QC_BARCODEALIGN(
        ch_qc_barcode_input,
        file("${projectDir}/bin/qc_barcode_align.py"),
        params.barcoding_shift_threshold,
        params.barcoding_corr_threshold,
        params.acquisition_geometry_rows,
        params.acquisition_geometry_columns,
    )
    ch_versions = ch_versions.mix(QC_BARCODEALIGN.out.versions)

    // ILLUMAPPLY outputs may be per site or per well depending on grouping mode
    // PREPROCESS always needs site-level grouping, so we need to regroup if illumapply was grouped by well
    // Extract site information from filenames and regroup by site
    ch_sbs_corr_images = CELLPROFILER_ILLUMAPPLY_BARCODING.out.corrected_images.flatMap { group_meta, images, _csv ->
        // Group images by site based on filename
        def images_by_site = images.groupBy { img ->
            // Extract site from filename: Plate_X_Well_Y_Site_Z_Cycle01_DNA.tiff
            def site_match = (img.name =~ /.*_Site_?(\d+)_Cycle/)
            site_match ? site_match[0][1] as Integer : group_meta.site
        }

        // Create one tuple per site with all its images
        images_by_site.collect { site, site_images ->
            // Create site-specific metadata
            def site_meta = group_meta.clone()
            site_meta.site = site
            site_meta.id = "${group_meta.batch}_${group_meta.plate}_${group_meta.well}_Site${site}"

            // Build image_metas for this site's images
            def image_metas = site_images.collect { img ->
                // Extract cycle and channel from corrected image filename
                // Pattern: Plate_X_Well_Y_Site_Z_Cycle01_DNA.tiff
                def cycle_channel_match = (img.name =~ /.*_Cycle(\d+)_(.+?)\.tiff?$/)
                def cycle = cycle_channel_match ? cycle_channel_match[0][1] as Integer : null
                def channel = cycle_channel_match ? cycle_channel_match[0][2] : 'UNKNOWN'

                // Clone metadata and add filename + cycle + channel + site
                site_meta + [
                    filename: img.name,
                    cycle: cycle,
                    channel: channel,
                    site: site,
                ]
            }

            [site_meta, site_images, image_metas]
        }
    }

    //// Barcoding preprocessing ////
    CELLPROFILER_PREPROCESS(
        ch_sbs_corr_images,
        barcoding_preprocess_cppipe,
        barcodes,
        channel.fromPath([params.callbarcodes_plugin, params.compensatecolors_plugin]).collect(),
    )
    ch_versions = ch_versions.mix(CELLPROFILER_PREPROCESS.out.versions)
    // Merge load_data CSVs across all samples
    CELLPROFILER_PREPROCESS.out.load_data_csv.collectFile(
        name: "barcoding-preprocess.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/",
    )

    //// QC: Barcode preprocessing ////
    // Group preprocessing stats by plate and collect wells
    ch_preprocess_qc_input = CELLPROFILER_PREPROCESS.out.preprocess_stats
        .map { meta, csv_files ->
            def plate_key = [
                batch: meta.batch,
                plate: meta.plate,
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
                id: "${plate_key.batch}_${plate_key.plate}",
            ]
            // Remove duplicate wells since we now have site-level data
            def unique_wells = wells.unique()
            [qc_meta, unique_wells, csvs, num_cycles]
        }

    QC_PREPROCESS(
        ch_preprocess_qc_input,
        file("${projectDir}/bin/qc_barcode_preprocess.py"),
        barcodes,
        params.acquisition_geometry_rows,
        params.acquisition_geometry_columns,
    )
    ch_versions = ch_versions.mix(QC_PREPROCESS.out.versions)

    // STITCH & CROP IMAGES ////
    // PREPROCESS outputs are per site, but STITCHCROP needs all sites together per well
    // Re-group by well before stitching
    ch_preprocess_by_well = CELLPROFILER_PREPROCESS.out.preprocessed_images
        .map { meta, images ->
            // Create well key (without site)
            def well_key = [
                batch: meta.batch,
                plate: meta.plate,
                well: meta.well,
                channels: meta.channels,
                arm: meta.arm,
                id: "${meta.batch}_${meta.plate}_${meta.well}",
            ]
            [well_key, meta.site, images]
        }
        .groupTuple()
        .map { well_meta, site_list, images_list ->
            // Flatten all site images into one list for the well
            // Calculate the starting site number from metadata
            def min_site = site_list.min()
            def enriched_meta = well_meta + [first_site_index: min_site]
            [enriched_meta, images_list.flatten()]
        }

    FIJI_STITCHCROP(
        ch_preprocess_by_well,
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
        params.qc_barcoding_passed,
    )

    // Split cropped images into individual tuples with site in metadata
    // FIJI_STITCHCROP outputs multiple files (one per site) but meta doesn't have site
    // Extract site from filename and create one tuple per site with all its cycle/channel images
    ch_cropped_images = FIJI_STITCHCROP.out.cropped_images
        .flatMap { meta, images ->
            // Group images by site
            def images_by_site = images.groupBy { img ->
                def site_match = (img.name =~ /Site_(\d+)/)
                site_match ? site_match[0][1] as Integer : null
            }

            // Create one tuple per site with all its cycle/channel images
            images_by_site.collect { site, site_images ->
                if (site == null) {
                    log.error("Could not parse site from barcoding cropped images")
                    return null
                }

                // Create new meta with site
                def new_meta = meta.subMap(['batch', 'plate', 'well', 'cycles', 'arm']) + [
                    id: "${meta.batch}_${meta.plate}_${meta.well}_${site}",
                    site: site,
                ]

                [new_meta, site_images]
            }
        }
        .filter { item -> item != null }

    ch_versions = ch_versions.mix(FIJI_STITCHCROP.out.versions)

    // QC montage for stitchcrop results
    ch_stitchcrop_qc = FIJI_STITCHCROP.out.downsampled_images
        .map { meta, tiff_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "barcoding"], tiff_files]
        }
        .groupTuple()
        .map { meta, tiff_files_list ->
            [meta, tiff_files_list.flatten()]
        }

    QC_MONTAGE_STITCHCROP_BARCODING(
        ch_stitchcrop_qc,
        ".*\\.tiff\$",
    )
    ch_versions = ch_versions.mix(QC_MONTAGE_STITCHCROP_BARCODING.out.versions)

    emit:
    cropped_images = ch_cropped_images // channel: [ val(meta), [ cropped_images ] ]
    versions = ch_versions // channel: [ versions.yml ]
}
