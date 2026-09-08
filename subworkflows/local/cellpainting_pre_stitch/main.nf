/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPROFILER_ILLUMCALC } from '../../../modules/local/cellprofiler/illumcalc'
include { QC_MONTAGEILLUM as QC_MONTAGEILLUM_PAINTING } from '../../../modules/local/qc/montageillum'
include { QC_CHECKDUPLICATEIMAGES as QC_CHECKDUPLICATES_ILLUMCALC_PAINTING } from '../../../modules/local/qc/checkduplicateimages'
include { QC_CHECKDUPLICATEIMAGES as QC_CHECKDUPLICATES_ILLUMAPPLY_PAINTING } from '../../../modules/local/qc/checkduplicateimages'
include { CELLPROFILER_ILLUMAPPLY as CELLPROFILER_ILLUMAPPLY_PAINTING } from '../../../modules/local/cellprofiler/illumapply'
include { expandImageChannels; buildLoadDataMetadata } from '../utils_nfcore_nf-pooled-cellpainting_pipeline'

workflow CELLPAINTING_PRE_STITCH {
    take:
    ch_samplesheet_cp // channel: [ val(meta), val(image) ]
    painting_illumcalc_cppipe // file: CellProfiler pipeline for illumination calculation
    painting_illumapply_cppipe // file: CellProfiler pipeline for illumination application
    outdir

    main:
    ch_versions = channel.empty()

    //// Calculate illumination correction profiles ////

    // Painting always groups illumcalc by batch/plate only (cycle is null) -
    // illumination correction doesn't need per-cycle grouping since painting's
    // channel names are already unique per cycle (e.g. DNA vs DNA2), and
    // painting_illumcalc_cppipe/painting_illumapply_cppipe are not built to
    // expect has_cycles-driven behavior. Multi-cycle awareness for STITCH's
    // task-splitting comes from the samplesheet's `cycle` column, handled
    // entirely below in ch_corrected_images_by_well - it never reaches
    // illumcalc/illumapply (expandImageChannels's record_cycle=false).
    ch_illumcalc_input = ch_samplesheet_cp
        .map { meta, image ->
            def group_id = "${meta.batch}_${meta.plate}"
            def group_key = meta.subMap(['batch', 'plate']) + [id: group_id]

            // One metadata entry per (file, channel) pair - see expandImageChannels().
            // illumcalc's cppipe selects input images named Orig{channel}.
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

    // Fail the pipeline if any two illumination-correction .npy files for this
    // plate are pixel-identical - a safety net against staging/matching bugs
    // that silently reuse one physical image where a different one should
    // have been produced.
    QC_CHECKDUPLICATES_ILLUMCALC_PAINTING(
        ch_illumination_corrections_qc,
    )
    ch_versions = ch_versions.mix(QC_CHECKDUPLICATES_ILLUMCALC_PAINTING.out.versions)

    // Group images by site for ILLUMAPPLY
    // Each site should get all its images
    ch_images_by_site = ch_samplesheet_cp
        .map { meta, image ->
            def site_id = "${meta.batch}_${meta.plate}_${meta.well}_Site${meta.site}"
            def site_key = meta.subMap(['batch', 'plate', 'well', 'site', 'arm']) + [id: site_id]

            // illumapply's cppipe selects input images named Orig{channel} /
            // Cycle{NN}_Orig{channel}; the Cycle prefix is added downstream by
            // generate_load_data_csv.py when the group spans >1 cycle.
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

    // Apply illumination correction to images (no QC attached here - alignment/QC
    // now happens downstream, post-stitch, in STITCH_ALIGN_CROP_JOINT)
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

    // Fail the pipeline if any two corrected .tiff images for this plate are
    // pixel-identical - see the illumcalc dedup check above for rationale.
    ch_corrected_images_dedup_qc = CELLPROFILER_ILLUMAPPLY_PAINTING.out.corrected_images
        .map { meta, tiff_files, _csv_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "painting"], tiff_files]
        }
        .groupTuple()
        .map { meta, tiff_files_list -> [meta, tiff_files_list.flatten()] }

    QC_CHECKDUPLICATES_ILLUMAPPLY_PAINTING(
        ch_corrected_images_dedup_qc,
    )
    ch_versions = ch_versions.mix(QC_CHECKDUPLICATES_ILLUMAPPLY_PAINTING.out.versions)

    // The real per-round `cycle` value is used only for STITCH's task splitting
    // (parallelism) and cross-round alignment below - never fed into
    // illumcalc/illumapply (their has_cycles/column generation must stay exactly
    // as today; see expandImageChannels's record_cycle=false above). Recovered
    // post-illumapply by channel name, since painting filenames never carry a
    // cycle token themselves. Built directly from the samplesheet - no external
    // file, no flag. meta.channels is a comma-joined string (one samplesheet
    // row/file can hold multiple channel frames, e.g. an OME-TIFF), so split it
    // before mapping each individual channel name to its cycle.
    ch_channel_to_cycle_by_plate = ch_samplesheet_cp
        .flatMap { meta, _image ->
            meta.channels.split(',').collect { ch -> [meta.subMap(['batch', 'plate']), [ch.trim(), meta.cycle]] }
        }
        .groupTuple()
        .map { plate_key, pairs ->
            def by_channel = pairs.groupBy { it[0] }
            by_channel.each { channel, entries ->
                def cycles = entries.collect { it[1] }.unique()
                if (cycles.size() > 1) {
                    error("Channel '${channel}' maps to multiple distinct cycle values (${cycles}) for plate ${plate_key} - " +
                          "channel names must be unique per cycle (e.g. DNA vs DNA2), not reused across cycles with different cycle values")
                }
            }
            [plate_key, by_channel.collectEntries { channel, entries -> [(channel): entries[0][1]] }]
        }

    // ILLUMAPPLY outputs are per site (bundling all of that site's cycles/channels
    // together), but STITCH needs one task per (well, cycle) for parallelism -
    // split each site's output by cycle (recovered from the output channel
    // name), then regroup by well+cycle.
    ch_corrected_images_by_well = CELLPROFILER_ILLUMAPPLY_PAINTING.out.corrected_images
        .map { meta, images, _csv -> [meta.subMap(['batch', 'plate']), meta, images] }
        .combine(ch_channel_to_cycle_by_plate, by: 0)
        .flatMap { _plate_key, meta, images, channel_to_cycle ->
            def images_by_cycle = [images].flatten().groupBy { img ->
                def m = (img.name =~ /.*_Corr(.+)\.tiff?$/)
                def channel = m ? m[0][1] : null
                def cycle = channel_to_cycle[channel]
                if (cycle == null) {
                    error("Could not resolve cycle for painting image '${img.name}' (channel '${channel}') - " +
                          "not found in this plate's samplesheet-derived channel->cycle map")
                }
                cycle
            }
            images_by_cycle.collect { cycle, cyc_images ->
                def well_key = meta.subMap(['batch', 'plate', 'well', 'arm']) + [
                    cycle: cycle,
                    id: "${meta.batch}_${meta.plate}_${meta.well}_Cycle${cycle}",
                ]
                [well_key, meta.site, cyc_images]
            }
        }
        .groupTuple()
        .map { well_meta, site_list, images_list ->
            // Flatten all site images into one list for the well
            // Calculate the starting site number from metadata
            def min_site = site_list.min()
            def enriched_meta = well_meta + [first_site_index: min_site]
            [enriched_meta, images_list.flatten().sort { it -> it.name }]
        }

    emit:
    corrected_images_by_well = ch_corrected_images_by_well // channel: [ val(meta), [ images ] ]
    versions = ch_versions // channel: [ versions.yml ]
}
