/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

include { CELLPROFILER_LOAD_DATA_CSV as ILLUMINATION_LOAD_DATA_CSV } from '../cellprofiler_load_data_csv'
include { CELLPROFILER_ILLUMINATIONCORRECTION } from '../../../modules/local/cellprofiler/illuminationcorrection'

workflow SEQ_BY_SYNTHESIS {

    take:
    ch_samplesheet_sbs
    cppipes

    main:

    ch_versions = Channel.empty()

    ILLUMINATION_LOAD_DATA_CSV (
        ch_samplesheet_sbs,
        ['batch', 'plate','cycle','channels'],
        'illumination_sbs',
        true
    )

    ILLUMINATION_LOAD_DATA_CSV.out.images_with_load_data_csv
        .flatMap { group_meta, meta_list, image_list, csv_file ->
            // Create a tuple for each metadata entry with the full image list and the CSV file
            return meta_list.collect { meta ->
                [group_meta, meta, image_list, csv_file]
            }
        }
        .set { ch_images_with_csv }

    CELLPROFILER_ILLUMINATIONCORRECTION (
        ch_images_with_csv,
        cppipes['illumination_calc_sbs'],
        ['plate','cycle']
    )

    emit:
    // bam      = SAMTOOLS_SORT.out.bam           // channel: [ val(meta), [ bam ] ]
    // bai      = SAMTOOLS_INDEX.out.bai          // channel: [ val(meta), [ bai ] ]
    // csi      = SAMTOOLS_INDEX.out.csi          // channel: [ val(meta), [ csi ] ]

    versions = ch_versions                     // channel: [ versions.yml ]
}
