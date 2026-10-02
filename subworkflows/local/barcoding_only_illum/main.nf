/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPROFILER_ILLUMCALC } from '../../../modules/local/cellprofiler/illumcalc'
include { ILLUM_MEANILLUM } from '../../../modules/local/illum/meanillum'
include { QC_MONTAGEILLUM as QC_MONTAGEILLUM_BARCODING } from '../../../modules/local/qc/montageillum'
include { QC_CHECKDUPLICATEIMAGES as QC_CHECKDUPLICATES_ILLUMCALC_BARCODING } from '../../../modules/local/qc/checkduplicateimages'
include { expandImageChannels; buildLoadDataMetadata } from '../utils_nfcore_nf-pooled-cellpainting_pipeline'

workflow BARCODING_ONLY_ILLUM {
    take:
    ch_samplesheet_sbs
    barcoding_illumcalc_cppipe
    outdir
    distributeillum

    main:
    ch_versions = channel.empty()

    // Group images by batch, plate, and cycle for illumination calculation - or
    // additionally by well when --distributeillum splits illumcalc into
    // smaller, per-well jobs (averaged back into a per-plate illum below).
    // All channels for a given cycle are processed together
    ch_illumcalc_input = ch_samplesheet_sbs
        .map { meta, image ->
            def group_fields = distributeillum ? ['batch', 'plate', 'well', 'cycle'] : ['batch', 'plate', 'cycle']
            def group_id = distributeillum
                ? "${meta.batch}_${meta.plate}_${meta.well}_${meta.cycle}"
                : "${meta.batch}_${meta.plate}_${meta.cycle}"
            def group_key = meta.subMap(group_fields) + [id: group_id]

            // One metadata entry per (file, channel) pair - see expandImageChannels().
            // illumcalc's cppipe selects input images named Orig{channel}.
            [group_key, expandImageChannels(meta, image, 'Orig'), image]
        }
        .groupTuple()
        .map { meta, images_meta_list, images_list ->
            def image_metas = images_meta_list.flatten()
            def all_channels = image_metas.channel.unique().join(",")
            // Each images_list[i] is staged as images/imgN/ (1-based); this is
            // the disambiguated name the module renames it to (see
            // expandImageChannels/stagedImageName) so generate_load_data_csv.py
            // never has to reverse-engineer which staged copy is which.
            def staged_names = images_meta_list.collect { it[0].filename }
            // Return tuple: (shared meta, channels, cycle, images, load_data metadata, staged names)
            [meta, all_channels, meta.cycle, images_list, buildLoadDataMetadata(meta, image_metas), staged_names]
        }

    CELLPROFILER_ILLUMCALC(
        ch_illumcalc_input,
        barcoding_illumcalc_cppipe,
        true,
    )
    ch_versions = ch_versions.mix(CELLPROFILER_ILLUMCALC.out.versions)
    // Merge load_data CSVs per plate
    CELLPROFILER_ILLUMCALC.out.load_data_csv.collectFile(keepHeader: true, skip: 1) { meta, csv ->
        def dir = file("${outdir}/workspace/load_data_csv/${meta.batch}/${meta.plate}")
        dir.mkdirs()
        [
            "${dir}/barcoding-illumcalc.load_data.csv",
            csv.text.replaceFirst(/(?m)^(.*)$/) { line ->
                line[0]
                    .replace('FinalFileName_', '__FINAL__')
                    .replace('FileName_', 'StagedFileName_')
                    .replace('__FINAL__', 'FileName_')
            },
        ]
    }

    if (distributeillum) {
        // Average the per-well illum functions into a single mean function,
        // used downstream exactly like a normal per-plate illumcalc output.
        ch_meanillum_input = CELLPROFILER_ILLUMCALC.out.illumination_corrections
            .map { meta, npy_files ->
                def plate_key = meta.subMap(['batch', 'plate', 'cycle'])
                [plate_key + [id: "${plate_key.batch}_${plate_key.plate}_${plate_key.cycle}"], npy_files]
            }
            .groupTuple()
            .map { meta, npy_files_list -> [meta, npy_files_list.flatten().sort { it -> it.name }] }

        ILLUM_MEANILLUM(ch_meanillum_input)
        ch_versions = ch_versions.mix(ILLUM_MEANILLUM.out.versions)
        ch_illumination_corrections = ILLUM_MEANILLUM.out.illumination_corrections
    }
    else {
        ch_illumination_corrections = CELLPROFILER_ILLUMCALC.out.illumination_corrections
    }

    //// QC illumination correction profiles ////
    ch_illumination_corrections_qc = ch_illumination_corrections
        .map { meta, npy_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "barcoding"], npy_files]
        }
        .groupTuple()
        .map { meta, npy_files_list ->
            [meta, npy_files_list.flatten().sort { it -> it.name }]
        }

    QC_MONTAGEILLUM_BARCODING(
        ch_illumination_corrections_qc,
        ".*Cycle.*\\.npy\$",
    )
    ch_versions = ch_versions.mix(QC_MONTAGEILLUM_BARCODING.out.versions)

    // Fail the pipeline if any two illumination-correction .npy files for this
    // plate are pixel-identical - a safety net against staging/matching bugs
    // that silently reuse one physical image where a different one should
    // have been produced.
    QC_CHECKDUPLICATES_ILLUMCALC_BARCODING(
        ch_illumination_corrections_qc,
    )
    ch_versions = ch_versions.mix(QC_CHECKDUPLICATES_ILLUMCALC_BARCODING.out.versions)

    emit:
    illumination_corrections = ch_illumination_corrections // channel: [ val(meta), [ npy_files ] ]
    versions = ch_versions // channel: [ versions.yml ]
}
