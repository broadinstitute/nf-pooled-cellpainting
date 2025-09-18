/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

include { CELLPROFILER_LOAD_DATA_CSV as ILLUMINATION_LOAD_DATA_CSV } from '../cellprofiler_load_data_csv'
include { CELLPROFILER_ILLUMCALC }                                   from '../../../modules/local/cellprofiler/illumcalc'
include { QC_MONTAGEILLUM }                                          from '../../../modules/local/qc/montageillum'

workflow SEQ_BY_SYNTHESIS {

    take:
    ch_samplesheet_sbs
    cppipes

    main:
    ch_versions = Channel.empty()

    ILLUMINATION_LOAD_DATA_CSV (
        ch_samplesheet_sbs,
        ['batch', 'plate','cycle','channels'],
        'illumination_sbs_calc',
        true
    )

    CELLPROFILER_ILLUMCALC (
        ILLUMINATION_LOAD_DATA_CSV.out.images_with_load_data_csv,
        cppipes['illumination_calc_sbs']
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

    QC_MONTAGEILLUM (
        ch_illumination_corrections_qc
    )

    emit:
    // bam      = SAMTOOLS_SORT.out.bam           // channel: [ val(meta), [ bam ] ]
    // bai      = SAMTOOLS_INDEX.out.bai          // channel: [ val(meta), [ bai ] ]
    // csi      = SAMTOOLS_INDEX.out.csi          // channel: [ val(meta), [ csi ] ]

    versions = ch_versions                     // channel: [ versions.yml ]
}
