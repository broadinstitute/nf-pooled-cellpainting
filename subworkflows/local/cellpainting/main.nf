/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPROFILER_ILLUMCALC                                      } from '../../../modules/local/cellprofiler/illumcalc'
include { QC_MONTAGEILLUM as QC_MONTAGEILLUM_PAINTING                 } from '../../../modules/local/qc/montageillum'
include { QC_MONTAGEILLUM as QC_MONTAGE_SEGCHECK                      } from '../../../modules/local/qc/montageillum'
include { QC_MONTAGEILLUM as QC_MONTAGE_STITCHCROP_PAINTING           } from '../../../modules/local/qc/montageillum'
include { CELLPROFILER_ILLUMAPPLY as CELLPROFILER_ILLUMAPPLY_PAINTING } from '../../../modules/local/cellprofiler/illumapply'
include { CELLPROFILER_SEGCHECK                                       } from '../../../modules/local/cellprofiler/segcheck'
include { FIJI_STITCHCROP                                             } from '../../../modules/local/fiji/stitchcrop'
workflow CELLPAINTING {
    take:
    ch_samplesheet_cp // channel: [ val(meta), val(image) ]
    painting_illumcalc_cppipe // file: CellProfiler pipeline for illumination calculation
    painting_illumapply_cppipe // file: CellProfiler pipeline for illumination application
    painting_segcheck_cppipe // file: CellProfiler pipeline for segmentation check
    range_skip // val: range of QC segcheck images to skip

    main:
    ch_versions = channel.empty()
    ch_cropped_images = channel.empty()

    //// Calculate illumination correction profiles ////

    // Group images by batch and plate for illumination calculation
    // Keep metadata for each image to generate load_data.csv
    ch_samplesheet_cp
        .map { meta, image ->
            def group_key = meta.subMap(['batch', 'plate'])
            def group_id = "${meta.batch}_${meta.plate}"

            // Preserve full metadata for each image
            def image_meta = meta.clone()
            image_meta.filename = image.name

            [group_key + [id: group_id], image_meta, image]
        }
        .groupTuple()
        .map { meta, images_meta_list, images_list ->
            def all_channels = images_meta_list[0].channels
            // Return tuple: (shared meta, channels, cycles, images, per-image metadata)
            [meta, all_channels, null, images_list, images_meta_list]
        }
        .set { ch_illumcalc_input }

    // Calculate illumination correction profiles
    CELLPROFILER_ILLUMCALC(
        ch_illumcalc_input,
        painting_illumcalc_cppipe,
        false,
    )
    // Merge load_data CSVs across all samples
    CELLPROFILER_ILLUMCALC.out.load_data_csv.collectFile(
        name: "painting-illumcalc.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/",
    )

    ch_versions = ch_versions.mix(CELLPROFILER_ILLUMCALC.out.versions)

    //// QC illumination correction profiles ////
    CELLPROFILER_ILLUMCALC.out.illumination_corrections
        .map { meta, npy_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "painting"], npy_files]
        }
        .groupTuple()
        .map { meta, npy_files_list ->
            [meta, npy_files_list.flatten()]
        }
        .set { ch_illumination_corrections_qc }

    QC_MONTAGEILLUM_PAINTING(
        ch_illumination_corrections_qc,
        ".*\\.npy\$",
    )
    ch_versions = ch_versions.mix(QC_MONTAGEILLUM_PAINTING.out.versions)

    // Group images by site for ILLUMAPPLY
    // Each site should get all its images
    ch_samplesheet_cp
        .map { meta, image ->
            def site_key = meta.subMap(['batch', 'plate', 'well', 'site', 'arm'])
            def site_id = "${meta.batch}_${meta.plate}_${meta.well}_Site${meta.site}"

            // Preserve full metadata for each image
            def image_meta = meta.clone()
            image_meta.filename = image.name

            [site_key + [id: site_id], image_meta, image]
        }
        .groupTuple()
        .map { site_meta, images_meta_list, images_list ->
            def all_channels = images_meta_list[0].channels
            // Check if images have MULTIPLE cycles (not just a single cycle value)
            def all_cycles = images_meta_list.collect { m -> m.cycle }.findAll { c -> c != null }.unique().sort()
            def unique_cycles = all_cycles.size() > 1 ? all_cycles : null

            // Return tuple: (shared meta, channels, cycles, images, per-image metadata)
            [site_meta, all_channels, unique_cycles, images_list, images_meta_list]
        }
        .set { ch_images_by_site }

    // Group npy files by batch and plate
    // All wells in a plate share the same illumination correction files
    CELLPROFILER_ILLUMCALC.out.illumination_corrections
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
        .set { ch_npy_by_plate }

    // Combine images with npy files
    // Each site gets all the npy files for its plate
    ch_images_by_site
        .map { site_meta, channels, cycles, images, image_metas ->
            def plate_key = [
                batch: site_meta.batch,
                plate: site_meta.plate,
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
    CELLPROFILER_ILLUMAPPLY_PAINTING(
        ch_illumapply_input,
        painting_illumapply_cppipe,
        false,
    )
    ch_versions = ch_versions.mix(CELLPROFILER_ILLUMAPPLY_PAINTING.out.versions)
    // Merge load_data CSVs across all samples
    CELLPROFILER_ILLUMAPPLY_PAINTING.out.load_data_csv.collectFile(
        name: "painting-illumapply.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/",
    )

    // Reshape CELLPROFILER_ILLUMAPPLY_PAINTING output for SEGCHECK
    // Build image metadata for corrected images
    CELLPROFILER_ILLUMAPPLY_PAINTING.out.corrected_images
        .map { meta, images, _csv ->
            // Build image_metas for corrected images with full metadata + filename + channel
            def image_metas = images.collect { img ->
                // Extract channel from corrected image filename: Plate_X_Well_Y_Site_Z_CorrCHANNEL.tiff
                def channel = img.name.replaceAll(/.*_Corr(.+?)\.tiff?$/, '$1')
                // Clone metadata and add filename + channel
                def image_meta = meta.clone()
                image_meta.filename = img.name
                image_meta.channel = channel
                image_meta
            }
            [meta, images, image_metas]
        }
        .set { ch_sub_corr_images }

    //// Segmentation quality check ////
    CELLPROFILER_SEGCHECK(
        ch_sub_corr_images,
        painting_segcheck_cppipe,
        range_skip,
    )
    ch_versions = ch_versions.mix(CELLPROFILER_SEGCHECK.out.versions)
    // Merge load_data CSVs across all samples
    CELLPROFILER_SEGCHECK.out.load_data_csv.collectFile(
        name: "painting-segcheck.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/",
    )

    // Reshape CELLPROFILER_SEGCHECK output for QC montage
    CELLPROFILER_SEGCHECK.out.segcheck_res
        .map { meta, _ch_versionscsv_files, png_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "painting"], png_files]
        }
        .groupTuple()
        .map { meta, png_files_list ->
            [meta, png_files_list.flatten()]
        }
        .set { ch_segcheck_qc }

    QC_MONTAGE_SEGCHECK(
        ch_segcheck_qc,
        ".*\\.png\$",
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
        .set { ch_corrected_images_by_well }

    // Create synchronization barrier - wait for ALL QC_MONTAGE_SEGCHECK to complete
    // This ensures all QC is done before attempting to run FIJI_STITCHCROP
    QC_MONTAGE_SEGCHECK.out.versions
        .collect()
        .set { ch_qc_complete }

    // Combine corrected images with QC completion signal
    // This makes each stitching job depend on QC completion, but allows parallel stitching
    ch_corrected_images_by_well
        .combine(ch_qc_complete)
        .map { meta, images, _qc_signal -> [meta, images] }
        .set { ch_corrected_images_synced }

    FIJI_STITCHCROP(
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
        params.compress,
        params.qc_painting_passed,
    )

    // Split cropped images into individual tuples with site in metadata
    // FIJI_STITCHCROP outputs multiple files (one per site) but meta doesn't have site
    // Extract site from filename and create one tuple per site with all channels for that site
    FIJI_STITCHCROP.out.cropped_images
        .flatMap { meta, images ->
            // Group images by site
            def images_by_site = images.groupBy { img ->
                def site_match = (img.name =~ /Site_(\d+)/)
                site_match ? site_match[0][1] as Integer : null
            }

            // Create one tuple per site with all its channel images
            images_by_site.collect { site, site_images ->
                if (site == null) {
                    log.error("Could not parse site from painting cropped images")
                    return null
                }

                // Create new meta with site
                def new_meta = meta.subMap(['batch', 'plate', 'well', 'channels', 'arm']) + [
                    id: "${meta.batch}_${meta.plate}_${meta.well}_${site}",
                    site: site,
                ]

                [new_meta, site_images]
            }
        }
        .filter { item -> item != null }
        .set { ch_cropped_images }

    ch_versions = ch_versions.mix(FIJI_STITCHCROP.out.versions)

    // QC montage for stitchcrop results
    FIJI_STITCHCROP.out.downsampled_images
        .map { meta, tiff_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "painting"], tiff_files]
        }
        .groupTuple()
        .map { meta, tiff_files_list ->
            [meta, tiff_files_list.flatten()]
        }
        .set { ch_stitchcrop_qc }

    QC_MONTAGE_STITCHCROP_PAINTING(
        ch_stitchcrop_qc,
        ".*\\.tiff\$",
    )
    ch_versions = ch_versions.mix(QC_MONTAGE_STITCHCROP_PAINTING.out.versions)

    emit:
    cropped_images = ch_cropped_images // channel: [ val(meta), [ cropped_images ] ]
    versions       = ch_versions // channel: [ versions.yml ]
}
