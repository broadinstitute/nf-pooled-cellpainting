/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPROFILER_LOAD_DATA_CSV as ILLUMINATION_CALC_LOAD_DATA_CSV }             from '../cellprofiler_load_data_csv'
include { CELLPROFILER_LOAD_DATA_CSV_WITH_ILLUM as ILLUMINATION_APPLY_LOAD_DATA_CSV } from '../cellprofiler_load_data_csv_with_illum'
include { CELLPROFILER_ILLUMCALC }                                                    from '../../../modules/local/cellprofiler/illumcalc'
include { QC_MONTAGEILLUM }                                                           from '../../../modules/local/qc/montageillum'
include { CELLPROFILER_ILLUMAPPLY }                                                   from '../../../modules/local/cellprofiler/illumapply'

workflow CELLPAINTING {

    take:
    ch_samplesheet_cp
    cppipes

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
            [meta.subMap(['batch', 'plate']) + [arm: "CP"], npy_files]
        }
        .groupTuple()
        .map{ meta, npy_files_list ->
            [meta, npy_files_list.flatten()]
        }
        .set { ch_illumination_corrections_qc }

    ch_illumination_corrections_qc.view()

    QC_MONTAGEILLUM (
        ch_illumination_corrections_qc
    )

    //// Apply illumination correction ////
    
    // Generate load_data.csv files for applying illumination correction
    ILLUMINATION_APPLY_LOAD_DATA_CSV(
        ch_samplesheet_cp,
        ['batch', 'plate','arm','well'],
        CELLPROFILER_ILLUMCALC.out.illumination_corrections,
        'illumination_cp_apply'
    )

    // Apply illumination correction to images
    CELLPROFILER_ILLUMAPPLY (
        ILLUMINATION_APPLY_LOAD_DATA_CSV.out.images_with_illum_load_data_csv,
        cppipes['illumination_apply_cp']
    )

    // emit:
    // // TODO nf-core: edit emitted channels
    // versions = ch_versions                     // channel: [ versions.yml ]
}