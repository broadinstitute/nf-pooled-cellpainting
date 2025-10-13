/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPROFILER_LOAD_DATA_CSV as ILLUMINATION_CALC_LOAD_DATA_CSV }             from '../cellprofiler_load_data_csv'
include { CELLPROFILER_LOAD_DATA_CSV_WITH_ILLUM as ILLUMINATION_APPLY_LOAD_DATA_CSV } from '../cellprofiler_load_data_csv_with_illum'
include { CELLPROFILER_ILLUMCALC }                                                    from '../../../modules/local/cellprofiler/illumcalc'
include { QC_MONTAGEILLUM as QC_MONTAGE_ILLUM }                                       from '../../../modules/local/qc/montageillum'
include { QC_MONTAGEILLUM as QC_MONTAGE_SEGCHECK }                                    from '../../../modules/local/qc/montageillum'
include { CELLPROFILER_ILLUMAPPLY }                                                   from '../../../modules/local/cellprofiler/illumapply'
include { CELLPROFILER_SEGCHECK }                                                     from '../../../modules/local/cellprofiler/segcheck'
include { PYTHON_STITCHCROP }                                                         from '../../../modules/local/python/stitchcrop'
include { FIJI_STITCHCROP }                                                           from '../../../modules/local/fiji/stitchcrop'
workflow CELLPAINTING {

    take:
    ch_samplesheet_cp
    cppipes
    range_skip

    main:

    //// Calculate illumination correction profiles ////

    // Generate load_data.csv files for calculating illumination correction profiles
    ILLUMINATION_CALC_LOAD_DATA_CSV (
        ch_samplesheet_cp,
        ['batch', 'plate', 'channels'],
        'illumination_cp_calc',
        false
    )

    // Calculate illumination correction profiles
    CELLPROFILER_ILLUMCALC (
        ILLUMINATION_CALC_LOAD_DATA_CSV.out.images_with_load_data_csv,
        cppipes['illumination_calc_cp']
    )

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

    QC_MONTAGE_ILLUM (
        ch_illumination_corrections_qc,
        ".*\\.npy\$"  // Pattern for painting: all .npy files
    )

    //// Apply illumination correction ////

    // Generate load_data.csv files for applying illumination correction
    ILLUMINATION_APPLY_LOAD_DATA_CSV(
        ch_samplesheet_cp,
        ['batch', 'plate','arm','well'],
        CELLPROFILER_ILLUMCALC.out.illumination_corrections,
        'illumination_cp_apply',
        false
    )

    // Apply illumination correction to images
    CELLPROFILER_ILLUMAPPLY (
        ILLUMINATION_APPLY_LOAD_DATA_CSV.out.images_with_illum_load_data_csv,
        cppipes['illumination_apply_cp']
    )

    // Reshape CELLPROFILER_ILLUMAPPLY output for SEGCHECK
    CELLPROFILER_ILLUMAPPLY.out.corrected_images.map{ meta, images, _csv ->
            [meta, images]
    }.set { ch_sub_corr_images }

    //// Segmentation quality check ////
    CELLPROFILER_SEGCHECK (
        ch_sub_corr_images,
        cppipes['segcheck_cp'],
        range_skip
    )

    // Reshape CELLPROFILER_SEGCHECK output for QC montage
    CELLPROFILER_SEGCHECK.out.segcheck_res
        .map{ meta, csv_files, png_files ->
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

    // STITCH & CROP IMAGES ////
    CELLPROFILER_ILLUMAPPLY.out.corrected_images.map{
        meta, images, _csv ->
            [meta, images]
        }
    .set { ch_corrected_images }

     PYTHON_STITCHCROP (
        ch_corrected_images,
        'painting'
    )

    FIJI_STITCHCROP (
        ch_corrected_images,
        'painting',
        file("${projectDir}/bin/stitch_crop.py")
    )

    // emit:
    // // TODO nf-core: edit emitted channels
    // versions = ch_versions                     // channel: [ versions.yml ]
}
