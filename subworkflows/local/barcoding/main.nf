/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

include { CELLPROFILER_LOAD_DATA_CSV as ILLUMINATION_LOAD_DATA_CSV }                  from '../cellprofiler_load_data_csv'
include { CELLPROFILER_ILLUMCALC }                                                    from '../../../modules/local/cellprofiler/illumcalc'
include { QC_MONTAGEILLUM as QC_MONTAGE_ILLUM }                                       from '../../../modules/local/qc/montageillum'
include { CELLPROFILER_LOAD_DATA_CSV_WITH_ILLUM as ILLUMINATION_APPLY_LOAD_DATA_CSV } from '../cellprofiler_load_data_csv_with_illum'
include { CELLPROFILER_ILLUMAPPLY as CELLPROFILER_ILLUMAPPLY_BARCODING }              from '../../../modules/local/cellprofiler/illumapply'
include { CELLPROFILER_PREPROCESS }                                                   from '../../../modules/local/cellprofiler/preprocess'
include { FIJI_STITCHCROP }                                                           from '../../../modules/local/fiji/stitchcrop'
workflow BARCODING {

    take:
    ch_samplesheet_sbs
    cppipes
    barcodes
    crop_percent

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

    QC_MONTAGE_ILLUM (
        ch_illumination_corrections_qc,
        ".*Cycle.*\\.npy\$"  // Pattern for barcoding: files with Cycle in name
    )

    // //// Apply illumination correction ////
    ILLUMINATION_APPLY_LOAD_DATA_CSV(
        ch_samplesheet_sbs,
        ['batch', 'plate','arm','well'],
        CELLPROFILER_ILLUMCALC.out.illumination_corrections,
        'illumination_sbs_apply',
        true
    )

    CELLPROFILER_ILLUMAPPLY_BARCODING (
        ILLUMINATION_APPLY_LOAD_DATA_CSV.out.images_with_illum_load_data_csv,
        cppipes['illumination_apply_sbs']
    )

    // Reshape CELLPROFILER_ILLUMAPPLY output for PREPROCESS
    CELLPROFILER_ILLUMAPPLY_BARCODING.out.corrected_images.map{ meta, images, _csv ->
            [meta, images]
    }.set { ch_sbs_corr_images }

    //// Barcoding preprocessing ////
    CELLPROFILER_PREPROCESS (
        ch_sbs_corr_images,
        cppipes['preprocess_sbs'],
        barcodes,
        Channel.fromPath("${projectDir}/assets/cellprofiler_plugins/*").collect()  // All Cellprofiler plugins
    )

    // Combine all load_data.csv files with shared header, grouped by batch and plate
    CombineLoadDataCSV.combine(
        CELLPROFILER_PREPROCESS.out.load_data_csv,
        ['batch', 'plate', 'arm'],
        "${params.outdir}/workspace/load_data_csv",
        'barcoding-preprocess'
    )

    // STITCH & CROP IMAGES ////
    FIJI_STITCHCROP (
        CELLPROFILER_PREPROCESS.out.preprocessed_images,
        file("${projectDir}/bin/stitch_crop.py"),
        crop_percent
    )

    emit:
    // bam      = SAMTOOLS_SORT.out.bam           // channel: [ val(meta), [ bam ] ]
    // bai      = SAMTOOLS_INDEX.out.bai          // channel: [ val(meta), [ bai ] ]
    // csi      = SAMTOOLS_INDEX.out.csi          // channel: [ val(meta), [ csi ] ]

    versions = ch_versions                     // channel: [ versions.yml ]
}
