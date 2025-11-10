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

    // Group images by well for ILLUMAPPLY
    // Each well should get all its images across all cycles
    ch_samplesheet_sbs
        .map { meta, image ->
            def group_key = [
                batch: meta.batch,
                plate: meta.plate,
                well: meta.well,
                channels: meta.channels,
                arm: meta.arm,
                id: "${meta.batch}_${meta.plate}_${meta.well}"
            ]
            [group_key, image, meta.cycle]
        }
        .groupTuple()
        .map { meta, images, cycles ->
            // Get unique images and cycles
            def unique_images = images.unique()
            def unique_cycles = cycles.unique().sort()
            [meta, meta.channels, unique_cycles, unique_images]
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

    CELLPROFILER_ILLUMAPPLY_BARCODING (
        ch_illumapply_input,
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

    // Reshape CELLPROFILER_ILLUMAPPLY output for PREPROCESS
    CELLPROFILER_ILLUMAPPLY_BARCODING.out.corrected_images.map{ meta, images, _csv ->
            [meta, images]
    }.set { ch_sbs_corr_images }

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
        FIJI_STITCHCROP (
            CELLPROFILER_PREPROCESS.out.preprocessed_images,
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
