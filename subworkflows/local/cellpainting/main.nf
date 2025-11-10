/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPROFILER_ILLUMCALC }                                                    from '../../../modules/local/cellprofiler/illumcalc'
include { QC_MONTAGEILLUM as QC_MONTAGEILLUM_PAINTING }                                       from '../../../modules/local/qc/montageillum'
include { QC_MONTAGEILLUM as QC_MONTAGE_SEGCHECK }                                    from '../../../modules/local/qc/montageillum'
include { CELLPROFILER_ILLUMAPPLY }                                                   from '../../../modules/local/cellprofiler/illumapply'
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

    // Group images by batch, plate, and channels for illumination calculation
    ch_samplesheet_cp
        .map { meta, image ->
            def group_key = [
                batch: meta.batch,
                plate: meta.plate,
                channels: meta.channels,
                id: "${meta.batch}_${meta.plate}_${meta.channels}"
            ]
            [group_key, image]
        }
        .groupTuple()
        .map { meta, images ->
            // Get unique images
            def unique_images = images.unique()
            [meta, meta.channels, null, unique_images]  // null for cycle since cellpainting has no cycles
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

    // Group images by well for ILLUMAPPLY
    // Each well should get all its images (no cycles for cellpainting)
    ch_samplesheet_cp
        .map { meta, image ->
            def group_key = [
                batch: meta.batch,
                plate: meta.plate,
                well: meta.well,
                channels: meta.channels,
                arm: meta.arm,
                id: "${meta.batch}_${meta.plate}_${meta.well}"
            ]
            [group_key, image]
        }
        .groupTuple()
        .map { meta, images ->
            // Get unique images
            def unique_images = images.unique()
            [meta, meta.channels, null, unique_images]  // null for cycles since cellpainting has no cycles
        }
        .set { ch_images_by_well }

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
    ch_images_by_well
        .map { meta, channels, cycles, images ->
            def plate_key = [
                batch: meta.batch,
                plate: meta.plate
            ]
            [plate_key, meta, channels, cycles, images]
        }
        .combine(ch_npy_by_plate, by: 0)
        .map { _plate_key, meta, channels, cycles, images, npy_files ->
            [meta, channels, cycles, images, npy_files]
        }
        .set { ch_illumapply_input }

    // Apply illumination correction to images
    CELLPROFILER_ILLUMAPPLY (
        ch_illumapply_input,
        painting_illumapply_cppipe,
        false  // has_cycles = false for cellpainting
    )
    ch_versions = ch_versions.mix(CELLPROFILER_ILLUMAPPLY.out.versions)
    // Merge load_data CSVs across all samples
    CELLPROFILER_ILLUMAPPLY.out.load_data_csv.collectFile(
        name: "painting-illumapply.load_data.csv",
        keepHeader: true,
        skip: 1,
        storeDir: "${params.outdir}/workspace/load_data_csv/"
    )

    // Reshape CELLPROFILER_ILLUMAPPLY output for SEGCHECK
    CELLPROFILER_ILLUMAPPLY.out.corrected_images.map{ meta, images, _csv ->
            [meta, images]
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

    CELLPROFILER_ILLUMAPPLY.out.corrected_images.map{
        meta, images, _csv ->
            [meta, images]
        }
    .set { ch_corrected_images }

    // Create synchronization barrier - wait for ALL QC_MONTAGE_SEGCHECK to complete
    // This ensures all QC is done before checking params.qc_painting_passed
    QC_MONTAGE_SEGCHECK.out.versions
        .collect()  // Wait for all QC jobs across all plates/wells
        .set { ch_qc_complete }

    // Conditionally proceed with stitching based on QC parameter
    if (params.qc_painting_passed) {
        // Combine corrected images with QC completion signal
        // This makes each stitching job depend on QC completion, but allows parallel stitching
        ch_corrected_images
            .combine(ch_qc_complete)  // Add QC barrier - broadcasts to all items
            .map { meta, images, _qc_signal -> [meta, images] }  // Drop signal, keep data
            .set { ch_corrected_images_synced }

        FIJI_STITCHCROP (
            ch_corrected_images_synced,
            file("${projectDir}/bin/stitch_crop.py")
        )
        ch_cropped_images = FIJI_STITCHCROP.out.cropped_images
        ch_versions = ch_versions.mix(FIJI_STITCHCROP.out.versions)
    } else {
        log.info "Stopping before FIJI_STITCHCROP for painting arm: QC not passed (params.qc_painting_passed = false). Perform QC for painting assay and set qc_painting_passed=true to proceed."
    }

    emit:
    cropped_images            = ch_cropped_images // channel: [ val(meta), [ cropped_images ] ]
    versions                  = ch_versions       // channel: [ versions.yml ]
}
