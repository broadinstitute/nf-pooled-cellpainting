/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPROFILER_ILLUMCALC } from '../../../modules/local/cellprofiler/illumcalc'
include { QC_MONTAGEILLUM as QC_MONTAGEILLUM_PAINTING } from '../../../modules/local/qc/montageillum'
include { QC_MONTAGEILLUM as QC_MONTAGE_ALIGNFAIL_PAINTING } from '../../../modules/local/qc/montageillum'
include { QC_MONTAGEILLUM as QC_MONTAGE_SEGCHECK } from '../../../modules/local/qc/montageillum'
include { QC_PAINTINGALIGN } from '../../../modules/local/qc/paintingalign'
include { CELLPROFILER_ILLUMAPPLY as CELLPROFILER_ILLUMAPPLY_PAINTING } from '../../../modules/local/cellprofiler/illumapply'
include { CELLPROFILER_SEGCHECK } from '../../../modules/local/cellprofiler/segcheck'
include { expandImageChannels; buildLoadDataMetadata } from '../utils_nfcore_nf-pooled-cellpainting_pipeline'

workflow CELLPAINTING_NO_STITCH {
    take:
    ch_samplesheet_cp // channel: [ val(meta), val(image) ]
    painting_illumcalc_cppipe // file: CellProfiler pipeline for illumination calculation
    painting_illumapply_cppipe // file: CellProfiler pipeline for illumination application
    painting_segcheck_cppipe // file: CellProfiler pipeline for segmentation check
    range_skip // val: range of QC segcheck images to skip
    segcheck_plugins // path(s): Cellprofiler plugin file(s) for segmentation check
    outdir
    acquisition_geometry_rows
    acquisition_geometry_columns

    main:
    ch_versions = channel.empty()

    //// Calculate illumination correction profiles ////

    // Group images by batch and plate for illumination calculation
    // Keep metadata for each image to generate load_data.csv
    ch_illumcalc_input = ch_samplesheet_cp
        .map { meta, image ->

            def group_id = "${meta.batch}_${meta.plate}"
            def group_key = meta.subMap(['batch', 'plate']) + [id: group_id]

            // One metadata entry per (file, channel) pair - see expandImageChannels().
            // illumcalc's cppipe selects input images named Orig{channel}.
            // record_cycle=false: painting channel names (DNA vs DNA2) already
            // disambiguate rounds, so illumcalc must never see >1 distinct cycle.
            [group_key, expandImageChannels(meta, image, 'Orig', false), image]
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
            // Return tuple: (shared meta, channels, cycles, images, load_data metadata, staged names)
            [meta, all_channels, null, images_list, buildLoadDataMetadata(meta, image_metas), staged_names]
        }

    // Calculate illumination correction profiles
    CELLPROFILER_ILLUMCALC(
        ch_illumcalc_input,
        painting_illumcalc_cppipe,
        false,
    )
    // Merge load_data CSVs per plate
    CELLPROFILER_ILLUMCALC.out.load_data_csv.collectFile(keepHeader: true, skip: 1) { meta, csv ->
        def dir = file("${outdir}/workspace/load_data_csv/${meta.batch}/${meta.plate}")
        dir.mkdirs()
        [
            "${dir}/painting-illumcalc.load_data.csv",
            csv.text.replaceFirst(/(?m)^(.*)$/) { line ->
                line[0]
                    .replace('FinalFileName_', '__FINAL__')
                    .replace('FileName_', 'StagedFileName_')
                    .replace('__FINAL__', 'FileName_')
            },
        ]
    }

    ch_versions = ch_versions.mix(CELLPROFILER_ILLUMCALC.out.versions)

    //// QC illumination correction profiles ////
    ch_illumination_corrections_qc = CELLPROFILER_ILLUMCALC.out.illumination_corrections
        .map { meta, npy_files ->
            def npy_meta = meta.subMap(['batch', 'plate']) + [arm: "painting"]
            [npy_meta, npy_files]
        }
        .groupTuple()
        .map { meta, npy_files_list ->
            [meta, npy_files_list.flatten().sort { it -> it.name }]
        }

    QC_MONTAGEILLUM_PAINTING(
        ch_illumination_corrections_qc,
        ".*\\.npy\$",
    )
    ch_versions = ch_versions.mix(QC_MONTAGEILLUM_PAINTING.out.versions)

    // Group images by site for ILLUMAPPLY
    // Each site should get all its images
    ch_images_by_site = ch_samplesheet_cp
        .map { meta, image ->
            def site_id = "${meta.batch}_${meta.plate}_${meta.well}_Site${meta.site}"
            def site_key = meta.subMap(['batch', 'plate', 'well', 'site', 'arm']) + [id: site_id]

            // illumapply's cppipe selects input images named Orig{channel} /
            // Cycle{NN}_Orig{channel}; the Cycle prefix is added downstream by
            // generate_load_data_csv.py when the group spans >1 cycle.
            // record_cycle=false: painting channel names (DNA vs DNA2) already
            // disambiguate rounds, so illumapply must never see >1 distinct cycle.
            [site_key, expandImageChannels(meta, image, 'Orig', false), image]
        }
        .groupTuple()
        .map { site_meta, images_meta_list, images_list ->
            def image_metas = images_meta_list.flatten()
            def all_channels = image_metas.channel.unique().join(",")
            // Check if images have MULTIPLE cycles (not just a single cycle value)
            def all_cycles = image_metas.collect { m -> m.cycle }.findAll { c -> c != null }.unique().sort()
            def unique_cycles = all_cycles.size() > 1 ? all_cycles : null
            // See the illumcalc staged_names comment above for why this exists.
            def staged_names = images_meta_list.collect { it[0].filename }

            // Return tuple: (shared meta, channels, cycles, images, load_data metadata, staged names)
            [site_meta, all_channels, unique_cycles, images_list, buildLoadDataMetadata(site_meta, image_metas), staged_names]
        }

    // Group npy files by batch and plate
    // All wells in a plate share the same illumination correction files
    ch_npy_by_plate = CELLPROFILER_ILLUMCALC.out.illumination_corrections
        .map { meta, npy_files ->
            def group_key = [
                batch: meta.batch,
                plate: meta.plate,
            ]
            [group_key, npy_files]
        }
        .groupTuple()
        .map { meta, npy_files_list ->
            [meta, npy_files_list.flatten()]
        }

    // Combine images with npy files
    // Each site gets all the npy files for its plate
    ch_illumapply_input = ch_images_by_site
        .map { site_meta, channels, cycles, images, image_metas, staged_names ->
            def plate_key = [
                batch: site_meta.batch,
                plate: site_meta.plate,
            ]
            // Store channels in meta for downstream use
            def enriched_meta = site_meta + [channels: channels]
            [plate_key, enriched_meta, channels, cycles, images, image_metas, staged_names]
        }
        .combine(ch_npy_by_plate, by: 0)
        .map { _plate_key, enriched_meta, channels, cycles, images, image_metas, staged_names, npy_files ->
            [enriched_meta, channels, cycles, images, image_metas, staged_names, npy_files]
        }

    // Apply illumination correction to images
    CELLPROFILER_ILLUMAPPLY_PAINTING(
        ch_illumapply_input,
        painting_illumapply_cppipe,
        false,
    )
    ch_versions = ch_versions.mix(CELLPROFILER_ILLUMAPPLY_PAINTING.out.versions)
    // Merge load_data CSVs per plate
    CELLPROFILER_ILLUMAPPLY_PAINTING.out.load_data_csv.collectFile(keepHeader: true, skip: 1) { meta, csv ->
        def dir = file("${outdir}/workspace/load_data_csv/${meta.batch}/${meta.plate}")
        dir.mkdirs()
        [
            "${dir}/painting-illumapply.load_data.csv",
            csv.text.replaceFirst(/(?m)^(.*)$/) { line ->
                line[0]
                    .replace('FinalFileName_', '__FINAL__')
                    .replace('FileName_', 'StagedFileName_')
                    .replace('__FINAL__', 'FileName_')
            },
        ]
    }

    // QC montage of any PNG QC images output by illumapply (optional)
    ch_illumapply_qc = CELLPROFILER_ILLUMAPPLY_PAINTING.out.qc_images
        .map { meta, png_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "painting"], png_files]
        }
        .groupTuple()
        .map { meta, png_files_list ->
            [meta, png_files_list.flatten().sort { it -> it.name }]
        }

    QC_MONTAGE_ALIGNFAIL_PAINTING(
        ch_illumapply_qc,
        ".*\\.png\$",
    )
    ch_versions = ch_versions.mix(QC_MONTAGE_ALIGNFAIL_PAINTING.out.versions)

    // QC of multicycle painting alignment
    // First, collect cycle information from the samplesheet to infer num_cycles
    ch_plate_cycles = ch_samplesheet_cp
        .map { meta, _image ->
            def plate_key = [
                batch: meta.batch,
                plate: meta.plate,
            ]
            [plate_key, meta.cycle]
        }
        .groupTuple()
        .map { plate_key, cycles ->
            def num_cycles = cycles.unique().max()
            [plate_key, num_cycles]
        }
    // Group CSV files by plate for QC analysis, keeping well-CSV correspondence
    ch_qc_painting_input = CELLPROFILER_ILLUMAPPLY_PAINTING.out.corrected_images
        .map { meta, _images, csv_files ->
            def plate_key = [
                batch: meta.batch,
                plate: meta.plate,
            ]
            // Find the PaintingIllumApplication_Image.csv file
            def image_csv = csv_files.find { file -> file.name.contains('Image.csv') }
            [plate_key, meta.well, image_csv]
        }
        .groupTuple()
        .combine(ch_plate_cycles, by: 0)
        .map { plate_key, wells, csv_files, num_cycles ->
            def qc_meta = plate_key + [
                arm: "painting",
                id: "${plate_key.batch}_${plate_key.plate}",
            ]
            // Remove duplicate wells since we now have site-level data
            def unique_wells = wells.unique()
            [qc_meta, unique_wells, csv_files, num_cycles]
        }

    QC_PAINTINGALIGN(
        ch_qc_painting_input,
        file("${projectDir}/bin/qc_painting_align.py"),
        acquisition_geometry_rows,
        acquisition_geometry_columns,
    )
    ch_versions = ch_versions.mix(QC_PAINTINGALIGN.out.versions)

    // Reshape CELLPROFILER_ILLUMAPPLY_PAINTING output for SEGCHECK
    // Group by well (not site) so range_skip can select every nth image from the well
    ch_sub_corr_images = CELLPROFILER_ILLUMAPPLY_PAINTING.out.corrected_images
        .map { meta, images, _csv ->
            // Create well key (without site)
            def well_key = [
                batch: meta.batch,
                plate: meta.plate,
                well: meta.well,
                arm: meta.arm,
                id: "${meta.batch}_${meta.plate}_${meta.well}",
            ]
            // Build image_metas for corrected images. Only the load_data schema
            // fields are emitted - the inherited `channels` well-string that used
            // to ride along here was never read and is dropped.
            // segcheck's cppipe selects input images by bare channel name (DNA,
            // Phalloidin, CHN2), so column_prefix is empty. No cycle: segcheck
            // operates on a single painting cycle's corrected images.
            def image_metas = images.collect { img ->
                def channel = img.name.replaceAll(/.*_Corr(.+?)\.tiff?$/, '$1')
                [
                    well         : meta.well,
                    site         : meta.site,
                    arm          : meta.arm,
                    cycle        : null,
                    channel      : channel,
                    frame_index  : null,
                    column_prefix: '',
                    filename     : img.name,
                    original_path: "${outdir}/images/${meta.batch}/images_corrected/${meta.arm}/${meta.plate}/${meta.plate}-${meta.well}-${meta.site}/${img.name}",
                ]
            }
            [well_key, meta.site, images, image_metas]
        }
        .groupTuple()
        .map { well_meta, _site_list, images_list, image_metas_list ->
            // Flatten all site images and metadata into one list for the well
            def flat_images = images_list.flatten().sort { img -> img.name }
            def flat_metas = image_metas_list.flatten().sort { m -> m.filename }
            [well_meta, flat_images, buildLoadDataMetadata(well_meta, flat_metas)]
        }

    //// Segmentation quality check ////
    CELLPROFILER_SEGCHECK(
        ch_sub_corr_images,
        painting_segcheck_cppipe,
        range_skip,
        segcheck_plugins,
    )
    ch_versions = ch_versions.mix(CELLPROFILER_SEGCHECK.out.versions)
    // Merge load_data CSVs per plate
    CELLPROFILER_SEGCHECK.out.load_data_csv.collectFile(keepHeader: true, skip: 1) { meta, csv ->
        def dir = file("${outdir}/workspace/load_data_csv/${meta.batch}/${meta.plate}")
        dir.mkdirs()
        [
            "${dir}/painting-segcheck.load_data.csv",
            csv.text.replaceFirst(/(?m)^(.*)$/) { line ->
                line[0]
                    .replace('FinalFileName_', '__FINAL__')
                    .replace('FileName_', 'StagedFileName_')
                    .replace('__FINAL__', 'FileName_')
            },
        ]
    }

    // Reshape CELLPROFILER_SEGCHECK output for QC montage
    ch_segcheck_qc = CELLPROFILER_SEGCHECK.out.segcheck_res
        .map { meta, _ch_versionscsv_files, png_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "painting"], png_files]
        }
        .groupTuple()
        .map { meta, png_files_list ->
            [meta, png_files_list.flatten().sort { it -> it.name }]
        }

    QC_MONTAGE_SEGCHECK(
        ch_segcheck_qc,
        ".*\\.png\$",
    )
    ch_versions = ch_versions.mix(QC_MONTAGE_SEGCHECK.out.versions)

    // NO STITCH/CROP: emit ILLUMAPPLY's per-site corrected images directly ////
    // Unlike the full pipeline, we skip FIJI_STITCHCROP entirely. The corrected
    // images from ILLUMAPPLY are already per-site, so no filename-based site
    // recovery is needed (that's only required post-stitch, since Fiji
    // recombines and re-splits images).
    //
    // Still create a synchronization barrier - wait for ALL QC_MONTAGE_SEGCHECK
    // to complete before emitting images for downstream (combined) analysis.
    ch_qc_complete = QC_MONTAGE_SEGCHECK.out.versions.collect()

    ch_precrop_images = CELLPROFILER_ILLUMAPPLY_PAINTING.out.corrected_images
        .combine(ch_qc_complete)
        .map { meta, images, _csv, _qc_signal ->
            def new_meta = meta.subMap(['batch', 'plate', 'well', 'channels', 'arm']) + [
                id: "${meta.batch}_${meta.plate}_${meta.well}_${meta.site}",
                site: meta.site,
            ]
            [new_meta, images]
        }

    emit:
    precrop_images = ch_precrop_images // channel: [ val(meta), [ images ] ]
    versions = ch_versions // channel: [ versions.yml ]
}
