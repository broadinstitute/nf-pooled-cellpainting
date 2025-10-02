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
include { CELLPROFILER_SEGCHECK }                                                     from '../../../modules/local/cellprofiler/segcheck'
include { GENERATE_LOAD_DATA_CSV as GENERATE_LOAD_DATA_CSV_SEGCHECK }                 from '../../../modules/local/generateloaddatacsv'
workflow CELLPAINTING {

    take:
    ch_samplesheet_cp
    input_samplesheet
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

    QC_MONTAGEILLUM (
        ch_illumination_corrections_qc
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

    // Calculate site indices to keep for each well based on range_skip
    ch_samplesheet_cp
        .map { meta, images ->
            def well_meta = meta.subMap(['batch', 'plate', 'well'])
            // Count channels to know how many files per site
            def num_channels = meta.channels ? meta.channels.split(',').size() : 1
            [well_meta, meta.site, num_channels]
        }
        .groupTuple()
        .map { well_meta, sites, num_channels_list ->
            // Sort sites and determine which to keep based on range_skip
            def sorted_sites = sites.sort()
            def num_channels = num_channels_list[0] // Should be same for all sites in a well
            def selected_site_indices = []
            sorted_sites.eachWithIndex { site, idx ->
                if (idx % range_skip == 0) {
                    selected_site_indices << idx
                }
            }
            [well_meta, selected_site_indices, num_channels]
        }
        .set { ch_well_site_indices }

    // Generate load_data.csv files for checking segmentation
    GENERATE_LOAD_DATA_CSV_SEGCHECK (
        input_samplesheet,
        'plate,well',
        '3',
        range_skip
    )

    // Parse CSV filenames to extract metadata and create tuples
    // Filename format: load_data_pipeline3_Plate1_A1_generated.csv
    GENERATE_LOAD_DATA_CSV_SEGCHECK.out.load_data_csv
        .flatten()
        .map { csv_file ->
            def filename = csv_file.name
            // Extract plate and well from filename: load_data_pipeline3_Plate1_A1_generated.csv
            def parts = filename.tokenize('_')
            def plate = parts[3] // Plate1
            def well = parts[4]  // A1
            def meta = [plate: plate, well: well]
            [meta, csv_file]
        }
        .set { ch_load_data_with_meta }

    // Subsample corrected images based on site indices from samplesheet
    CELLPROFILER_ILLUMAPPLY.out.corrected_images
        .map { meta, tiff_files, csv_files ->
            def well_meta = meta.subMap(['batch', 'plate', 'well'])
            [well_meta, meta, tiff_files]
        }
        .combine(ch_well_site_indices, by: 0)
        .map { well_meta, meta, tiff_files, site_indices, num_channels ->
            // Subsample TIFF files based on site indices and number of channels per site
            def tiff_list = tiff_files instanceof List ? tiff_files : [tiff_files]
            def subsampled_tiffs = []
            site_indices.each { site_idx ->
                // Each site has num_channels TIFF files
                def start_idx = site_idx * num_channels
                def end_idx = start_idx + num_channels
                subsampled_tiffs.addAll(tiff_list[start_idx..<end_idx])
            }
            // Remove batch from well_meta for final combine with CSV
            def final_well_meta = well_meta.subMap(['plate', 'well'])
            [final_well_meta, meta, subsampled_tiffs]
        }
        .combine(ch_load_data_with_meta, by: 0)
        .map { well_meta, orig_meta, tiff_files, load_data_csv ->
            [orig_meta, tiff_files, load_data_csv]
        }
        .set { ch_segcheck_input }

    //// Check segmentation ////
    CELLPROFILER_SEGCHECK (
        ch_segcheck_input,
        cppipes['segcheck_cp']
    )

    // emit:
    // // TODO nf-core: edit emitted channels
    // versions = ch_versions                     // channel: [ versions.yml ]
}
