/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPROFILER_ILLUMCALC } from '../../../modules/local/cellprofiler/illumcalc'
include { QC_MONTAGEILLUM as QC_MONTAGEILLUM_PAINTING } from '../../../modules/local/qc/montageillum'
include { CELLPROFILER_ILLUMAPPLY as CELLPROFILER_ILLUMAPPLY_PAINTING } from '../../../modules/local/cellprofiler/illumapply'

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
    // task-splitting comes from the separate cycle_phenotyping samplesheet
    // column, handled entirely below in ch_corrected_images_by_well - it never
    // reaches illumcalc/illumapply.
    ch_illumcalc_input = ch_samplesheet_cp
        .map { meta, image ->
            def group_id = "${meta.batch}_${meta.plate}"
            def group_key = meta.subMap(['batch', 'plate']) + [id: group_id]

            // Preserve full metadata for each image
            def image_meta = meta + [filename: image.name, original_path: image.toString(), original_filename: image.name]
            [group_key, image_meta, image]
        }
        .groupTuple()
        .map { meta, images_meta_list, images_list ->
            def all_channels = images_meta_list.channels.unique().join(", ")
            // Return tuple: (shared meta, channels, cycles, images, per-image metadata)
            [meta, all_channels, null, images_list, images_meta_list]
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

            // Preserve full metadata for each image
            def image_meta = meta + [filename: image.name, original_path: image.toString(), original_filename: image.name]

            [site_key, image_meta, image]
        }
        .groupTuple()
        .map { site_meta, images_meta_list, images_list ->
            def all_channels = images_meta_list.channels.unique().join(", ")
            // Check if images have MULTIPLE cycles (not just a single cycle value)
            def all_cycles = images_meta_list.collect { m -> m.cycle }.findAll { c -> c != null }.unique().sort()
            def unique_cycles = all_cycles.size() > 1 ? all_cycles : null

            // Return tuple: (shared meta, channels, cycles, images, per-image metadata)
            [site_meta, all_channels, unique_cycles, images_list, images_meta_list]
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
        .map { site_meta, channels, cycles, images, image_metas ->
            def plate_key = [
                batch: site_meta.batch,
                plate: site_meta.plate,
            ]
            // Store channels in meta for downstream use
            def enriched_meta = site_meta + [channels: channels]
            [plate_key, enriched_meta, channels, cycles, images, image_metas]
        }
        .combine(ch_npy_by_plate, by: 0)
        .map { _plate_key, enriched_meta, channels, cycles, images, image_metas, npy_files ->
            [enriched_meta, channels, cycles, images, image_metas, npy_files]
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

    // cycle_phenotyping is optional/painting-only bookkeeping for STITCH's task
    // splitting - never fed into illumcalc/illumapply (their has_cycles/column
    // generation must stay exactly as today). Recovered post-illumapply by
    // channel name below, since painting filenames never carry a cycle token
    // themselves. Built directly from the samplesheet - no external file, no flag.
    // meta.channels is a comma-joined string (one samplesheet row/file can hold
    // multiple channel frames, e.g. an OME-TIFF), so split it before mapping each
    // individual channel name to its cycle.
    ch_channel_to_cycle_by_plate = ch_samplesheet_cp
        .flatMap { meta, _image ->
            meta.channels.split(',').collect { ch -> [meta.subMap(['batch', 'plate']), [ch.trim(), (meta.cycle_phenotyping ?: 1)]] }
        }
        .groupTuple()
        .map { plate_key, pairs ->
            def by_channel = pairs.groupBy { it[0] }
            by_channel.each { channel, entries ->
                def cycles = entries.collect { it[1] }.unique()
                if (cycles.size() > 1) {
                    error("Channel '${channel}' maps to multiple distinct cycle_phenotyping values (${cycles}) for plate ${plate_key} - " +
                          "channel names must be unique per cycle (e.g. DNA vs DNA2), not reused across cycles with different cycle_phenotyping values")
                }
            }
            [plate_key, by_channel.collectEntries { channel, entries -> [(channel): entries[0][1]] }]
        }

    // ILLUMAPPLY outputs are per site (bundling all of that site's cycles/channels
    // together), but STITCH needs one task per (well, cycle) for parallelism -
    // split each site's output by cycle_phenotyping (recovered from the output
    // channel name), then regroup by well+cycle.
    ch_corrected_images_by_well = CELLPROFILER_ILLUMAPPLY_PAINTING.out.corrected_images
        .map { meta, images, _csv -> [meta.subMap(['batch', 'plate']), meta, images] }
        .combine(ch_channel_to_cycle_by_plate, by: 0)
        .flatMap { _plate_key, meta, images, channel_to_cycle ->
            def images_by_cycle = [images].flatten().groupBy { img ->
                def m = (img.name =~ /.*_Corr(.+)\.tiff?$/)
                def channel = m ? m[0][1] : null
                def cycle = channel_to_cycle[channel]
                if (cycle == null) {
                    error("Could not resolve cycle_phenotyping for painting image '${img.name}' (channel '${channel}') - " +
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
