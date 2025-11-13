/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPROFILER_ILLUMCALC }                                                    from '../../../modules/local/cellprofiler/illumcalc'
include { QC_MONTAGEILLUM as QC_MONTAGEILLUM_PAINTING }                               from '../../../modules/local/qc/montageillum'
include { QC_MONTAGEILLUM as QC_MONTAGE_SEGCHECK }                                    from '../../../modules/local/qc/montageillum'
include { QC_MONTAGEILLUM as QC_MONTAGE_STITCHCROP_PAINTING }                         from '../../../modules/local/qc/montageillum'
include { CELLPROFILER_ILLUMAPPLY as CELLPROFILER_ILLUMAPPLY_PAINTING }                                                   from '../../../modules/local/cellprofiler/illumapply'
include { CELLPROFILER_SEGCHECK }                                                     from '../../../modules/local/cellprofiler/segcheck'
include { FIJI_STITCHCROP }                                                           from '../../../modules/local/fiji/stitchcrop'
workflow CELLPAINTING {

    take:
    ch_samplesheet_cp
    painting_illumcalc_cppipe
    painting_illumapply_cppipe
    painting_segcheck_cppipe
    range_skip

    main:
    ch_versions = channel.empty()
    ch_cropped_images = channel.empty()

    //// Calculate illumination correction profiles ////

    // Group images by batch and plate for illumination calculation
    // All channels are processed together
    ch_samplesheet_cp
        .map { meta, image ->
            def group_key = [
                batch: meta.batch,
                plate: meta.plate,
                id: "${meta.batch}_${meta.plate}"
            ]
            [group_key, image, meta]
        }
        .groupTuple()
        .map { meta, images, meta_list ->
            // Zip images with metadata to keep them synchronized
            def paired = [images, meta_list].transpose().unique()
            def unique_images = paired.collect { it[0] }
            def unique_metas = paired.collect { it[1] }

            def all_channels = meta_list[0].channels
            // Enrich metadata with filenames to enable matching
            def metas_with_filenames = []
            unique_images.eachWithIndex { img, idx ->
                def m = unique_metas[idx]
                def basename = img.name
                // Create new map with filename added
                def enriched = [:]
                enriched.putAll(m)
                enriched.filename = basename
                metas_with_filenames << enriched
            }
            // Pass the group metadata and the full list of individual image metadata with filenames
            [meta, all_channels, null, unique_images, metas_with_filenames]
        }
        .set { ch_illumcalc_input }

    // Calculate illumination correction profiles
    CELLPROFILER_ILLUMCALC (
        ch_illumcalc_input,
        painting_illumcalc_cppipe,
        false  // has_cycles = false for cellpainting
    )
    // Merge load_data CSVs across all samples
    CELLPROFILER_ILLUMCALC.out.load_data_csv.collectFile(
        name: "painting-illumcalc.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/"
    )

    ch_versions = ch_versions.mix(CELLPROFILER_ILLUMCALC.out.versions)

    //// QC illumination correction profiles ////
    CELLPROFILER_ILLUMCALC.out.illumination_corrections
        .map{ meta, npy_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "painting"], npy_files]
        }
        .groupTuple()
        .map{ meta, npy_files_list ->
            [meta, npy_files_list.flatten()]
        }
        .set { ch_illumination_corrections_qc }

    QC_MONTAGEILLUM_PAINTING (
        ch_illumination_corrections_qc,
        ".*\\.npy\$"  // Pattern for painting: all .npy files
    )
    ch_versions = ch_versions.mix(QC_MONTAGEILLUM_PAINTING.out.versions)

    // Group images by site for ILLUMAPPLY
    // Each site should get all its images
    ch_samplesheet_cp
        .map { meta, image ->
            def site_key = [
                batch: meta.batch,
                plate: meta.plate,
                well: meta.well,
                site: meta.site,
                arm: meta.arm,
                id: "${meta.batch}_${meta.plate}_${meta.well}_Site${meta.site}"
            ]
            [site_key, image, meta]
        }
        .groupTuple()
        .map { site_meta, images, meta_list ->
            // Zip images with metadata to keep them synchronized
            def paired = [images, meta_list].transpose().unique()
            def unique_images = paired.collect { it[0] }
            def unique_metas = paired.collect { it[1] }

            def all_channels = meta_list[0].channels
            // Check if images have MULTIPLE cycles (not just a single cycle value)
            // Only treat as multi-cycle if there are 2+ distinct cycle values
            def all_cycles = unique_metas.collect { it.cycle }.findAll { it != null }.unique().sort()
            def unique_cycles = (all_cycles.size() > 1) ? all_cycles : null

            // Enrich metadata with filenames to enable matching
            def metas_with_filenames = []
            unique_images.eachWithIndex { img, idx ->
                def m = unique_metas[idx]
                def basename = img.name
                // Create new map with filename added
                def enriched = [:]
                enriched.putAll(m)
                enriched.filename = basename
                // Only include cycle if we have multiple cycles
                if (unique_cycles == null && enriched.containsKey('cycle')) {
                    enriched.remove('cycle')
                }
                metas_with_filenames << enriched
            }
            // Pass the group metadata, channels, cycles (null or list), unique images, and metadata with filenames
            [site_meta, all_channels, unique_cycles, unique_images, metas_with_filenames]
        }
        .set { ch_images_by_site }

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
    // Each site gets all the npy files for its plate
    ch_images_by_site
        .map { site_meta, channels, cycles, images, image_metas ->
            def plate_key = [
                batch: site_meta.batch,
                plate: site_meta.plate
            ]
            // Store channels in meta for downstream use
            def enriched_meta = site_meta + [channels: channels]
            [plate_key, enriched_meta, channels, cycles, images, image_metas]
        }
        .combine(ch_npy_by_plate, by: 0)
        .map { _plate_key, enriched_meta, channels, cycles, images, image_metas, npy_files ->
            [enriched_meta, channels, cycles, images, image_metas, npy_files]
        }
        .set { ch_illumapply_input }

    // Apply illumination correction to images
    CELLPROFILER_ILLUMAPPLY_PAINTING (
        ch_illumapply_input,
        painting_illumapply_cppipe,
        false  // has_cycles = false for cellpainting
    )
    ch_versions = ch_versions.mix(CELLPROFILER_ILLUMAPPLY_PAINTING.out.versions)
    // Merge load_data CSVs across all samples
    CELLPROFILER_ILLUMAPPLY_PAINTING.out.load_data_csv.collectFile(
        name: "painting-illumapply.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/"
    )

    // Reshape CELLPROFILER_ILLUMAPPLY_PAINTING output for SEGCHECK
    // Build image metadata for corrected images
    CELLPROFILER_ILLUMAPPLY_PAINTING.out.corrected_images.map{ meta, images, _csv ->
        // Build image_metas for corrected images with filenames and channel extracted
        def image_metas = images.collect { img ->
            // Extract channel from corrected image filename: Plate_X_Well_Y_Site_Z_CorrCHANNEL.tiff
            def channel = img.name.replaceAll(/.*_Corr(.+?)\.tiff?$/, '$1')
            [
                well: meta.well,
                site: meta.site,
                filename: img.name,
                channel: channel
            ]
        }
        [meta, images, image_metas]
    }.set { ch_sub_corr_images }

    //// Segmentation quality check ////
    CELLPROFILER_SEGCHECK (
        ch_sub_corr_images,
        painting_segcheck_cppipe,
        range_skip
    )
    ch_versions = ch_versions.mix(CELLPROFILER_SEGCHECK.out.versions)
    // Merge load_data CSVs across all samples
    CELLPROFILER_SEGCHECK.out.load_data_csv.collectFile(
        name: "painting-segcheck.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/"
    )

    // Reshape CELLPROFILER_SEGCHECK output for QC montage
    CELLPROFILER_SEGCHECK.out.segcheck_res
        .map{ meta, ch_versionscsv_files, png_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "painting"], png_files]
        }
        .groupTuple()
        .map{ meta, png_files_list ->
            [meta, png_files_list.flatten()]
        }
        .set { ch_segcheck_qc }

    QC_MONTAGE_SEGCHECK (
        ch_segcheck_qc,
        ".*\\.png\$"  // Pattern for segcheck: all PNG files
    )
    ch_versions = ch_versions.mix(QC_MONTAGE_SEGCHECK.out.versions)

    // STITCH & CROP IMAGES ////
    // Conditional execution: only run if params.qc_painting_passed is true
    // This allows the painting arm to stop at stitching/cropping if QC fails,
    // while allowing the barcoding arm to proceed independently

    // ILLUMAPPLY outputs are per site, but STITCHCROP needs all sites together per well
    // Re-group by well before stitching
    CELLPROFILER_ILLUMAPPLY_PAINTING.out.corrected_images
        .map { meta, images, _csv ->
            // Create well key (without site)
            def well_key = [
                batch: meta.batch,
                plate: meta.plate,
                well: meta.well,
                channels: meta.channels,
                arm: meta.arm,
                id: "${meta.batch}_${meta.plate}_${meta.well}"
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
        .set { ch_corrected_images_by_well }

    // Create synchronization barrier - wait for ALL QC_MONTAGE_SEGCHECK to complete
    // This ensures all QC is done before checking params.qc_painting_passed
    QC_MONTAGE_SEGCHECK.out.versions
        .collect()  // Wait for all QC jobs across all plates/wells
        .set { ch_qc_complete }

    // Conditionally proceed with stitching based on QC parameter
    if (params.qc_painting_passed) {
        // Combine corrected images with QC completion signal
        // This makes each stitching job depend on QC completion, but allows parallel stitching
        ch_corrected_images_by_well
            .combine(ch_qc_complete)  // Add QC barrier - broadcasts to all items
            .map { meta, images, _qc_signal -> [meta, images] }  // Drop signal, keep data
            .set { ch_corrected_images_synced }

        FIJI_STITCHCROP (
            ch_corrected_images_synced,
            file("${projectDir}/bin/stitch_crop.py"),
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
            params.compress
        )

        // Split cropped images into individual tuples with site in metadata
        // FIJI_STITCHCROP outputs multiple files (one per site) but meta doesn't have site
        // Extract site from filename and create one tuple per site with all channels for that site
        ch_cropped_images = FIJI_STITCHCROP.out.cropped_images
            .flatMap { meta, images ->
                // Group images by site
                def images_by_site = images.groupBy { img ->
                    def site_match = (img.name =~ /Site_(\d+)/)
                    site_match ? site_match[0][1] as Integer : null
                }

                // Create one tuple per site with all its channel images
                images_by_site.collect { site, site_images ->
                    if (site == null) {
                        log.error "Could not parse site from painting cropped images"
                        return null
                    }

                    // Create new meta with site
                    def new_meta = meta.subMap(['batch', 'plate', 'well', 'channels', 'arm']) + [
                        id: "${meta.batch}_${meta.plate}_${meta.well}_${site}",
                        site: site
                    ]

                    [new_meta, site_images]
                }
            }
            .filter { item -> item != null }

        ch_versions = ch_versions.mix(FIJI_STITCHCROP.out.versions)

        // QC montage for stitchcrop results
        FIJI_STITCHCROP.out.downsampled_images
            .map{ meta, tiff_files ->
                [meta.subMap(['batch', 'plate']) + [arm: "painting"], tiff_files]
            }
            .groupTuple()
            .map{ meta, tiff_files_list ->
                [meta, tiff_files_list.flatten()]
            }
            .set { ch_stitchcrop_qc }

        QC_MONTAGE_STITCHCROP_PAINTING (
            ch_stitchcrop_qc,
            ".*\\.tiff\$"  // Pattern for stitchcrop: all TIFF files
        )
        ch_versions = ch_versions.mix(QC_MONTAGE_STITCHCROP_PAINTING.out.versions)
    } else {
        log.info "Stopping before FIJI_STITCHCROP for painting arm: QC not passed (params.qc_painting_passed = false). Perform QC for painting assay and set qc_painting_passed=true to proceed."
    }

    emit:
    cropped_images            = ch_cropped_images // channel: [ val(meta), [ cropped_images ] ]
    versions                  = ch_versions       // channel: [ versions.yml ]
}
