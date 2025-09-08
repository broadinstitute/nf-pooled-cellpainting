/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPROFILER_LOAD_DATA_CSV as ILLUMINATION_LOAD_DATA_CSV } from '../cellprofiler_load_data_csv'
include { CELLPROFILER_ILLUMINATIONCORRECTION }                      from '../../../modules/local/cellprofiler/illuminationcorrection'
include { CELLPROFILER_ILLUMINATIONCORRECTIONAPPLY }                 from '../../../modules/local/cellprofiler/illuminationcorrectionapply'

workflow CELLPAINTING {

    take:
    ch_samplesheet_cp
    cppipes

    main:

    // Generate load_data.csv files for illumination correction calculation
    ILLUMINATION_LOAD_DATA_CSV (
        ch_samplesheet_cp,
        ['batch', 'plate', 'channels'],
        'illumination_cp',
        false
    )

    ILLUMINATION_LOAD_DATA_CSV.out.images_with_load_data_csv
        .flatMap { group_meta, meta_list, image_list, csv_file ->

            // Create a tuple for each metadata entry with the full image list and the CSV file
            return meta_list.collect { meta ->
                [group_meta, meta, image_list, csv_file]
            }
        }
        .set { ch_images_with_csv }
        

    // Calculate illumination correction profiles
    CELLPROFILER_ILLUMINATIONCORRECTION (
        ch_images_with_csv,
        cppipes['illumination_calc_cp'],
        ['plate']
    )

    // Create load_data.csv files for illumination correction application
    CELLPROFILER_ILLUMINATIONCORRECTION.out.illumination_corrections
        .map { meta, channels, images, npy_files, load_data_csv ->
            def csv_lines = load_data_csv.text.split('\n')
            def channel_names = channels.contains(',') ? channels.split(',').collect { it.trim() } : [channels]
            def illum_columns = channel_names.collect { "FileName_Illum${it}" }.join(',')
            def new_header = csv_lines[0] + ',' + illum_columns
            
            def new_rows = csv_lines[1..-1].findAll { it.trim() }.collect { row ->
                def illum_values = channel_names.collect { channel ->
                    npy_files.find { it.name.contains(channel) }?.name ?: ''
                }.join(',')
                row + ',' + illum_values
            }
            
            def new_csv_content = ([new_header] + new_rows).join('\n')
            [meta, channels, images, npy_files, new_csv_content]
        }
        .map { meta, channels, images, npy_files, csv_content ->
            // Create a temporary file for the new CSV content
            def csv_file = file("${workflow.workDir}/${workflow.sessionId}/cellprofiler/load_data_csvs/illumination_apply/${meta.id}.csv")
            csv_file.parent.mkdirs()
            csv_file.text = csv_content
            
            // Return the original structure but with the new CSV file
            [meta + [arm: 'CP'], channels, images, npy_files, csv_file]
        }
        .set { ch_illumination_apply_csv }

    CELLPROFILER_ILLUMINATIONCORRECTIONAPPLY (
        ch_illumination_apply_csv,
        cppipes['illumination_apply_cp']
    )


    // emit:
    // // TODO nf-core: edit emitted channels
    // versions = ch_versions                     // channel: [ versions.yml ]
}