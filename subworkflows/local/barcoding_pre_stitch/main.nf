/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { CELLPROFILER_ILLUMCALC } from '../../../modules/local/cellprofiler/illumcalc'
include { QC_MONTAGEILLUM as QC_MONTAGEILLUM_BARCODING } from '../../../modules/local/qc/montageillum'
// Aliased separately from the CELLPROFILER_ILLUMAPPLY_BARCODING used by barcoding/main.nf and
// barcoding_no_stitch/main.nf so this entrypoint can publish to its own folder name below -
// "images_aligned" is misleading here since alignment moved out of illumapply into ALIGN_BARCODING.
include { CELLPROFILER_ILLUMAPPLY as CELLPROFILER_ILLUMAPPLY_BARCODING_PRESTITCH } from '../../../modules/local/cellprofiler/illumapply'
include { expandImageChannels; buildLoadDataMetadata } from '../utils_nfcore_nf-pooled-cellpainting_pipeline'

workflow BARCODING_PRE_STITCH {
    take:
    ch_samplesheet_sbs
    barcoding_illumcalc_cppipe
    barcoding_illumapply_cppipe
    outdir
    barcoding_illumapply_grouping

    main:
    ch_versions = channel.empty()

    // Group images by batch, plate, and cycle for illumination calculation
    // All channels for a given cycle are processed together
    ch_illumcalc_input = ch_samplesheet_sbs
        .map { meta, image ->
            def group_id = "${meta.batch}_${meta.plate}_${meta.cycle}"
            def group_key = meta.subMap(['batch', 'plate', 'cycle']) + [id: group_id]

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

    //// QC illumination correction profiles ////
    ch_illumination_corrections_qc = CELLPROFILER_ILLUMCALC.out.illumination_corrections
        .map { meta, npy_files ->
            [meta.subMap(['batch', 'plate']) + [arm: "barcoding"], npy_files]
        }
        .groupTuple()
        .map { meta, npy_files_list ->
            [meta, npy_files_list.flatten()]
        }

    QC_MONTAGEILLUM_BARCODING(
        ch_illumination_corrections_qc,
        ".*Cycle.*\\.npy\$",
    )
    ch_versions = ch_versions.mix(QC_MONTAGEILLUM_BARCODING.out.versions)

    // Group images for ILLUMAPPLY based on parameter setting
    // Two modes:
    //   - "site": Group by site (current behavior) - each site processed separately
    //   - "well": Group by well (new behavior) - all sites in a well processed together
    // Site information is always preserved in image metadata for downstream regrouping
    ch_images_by_site = ch_samplesheet_sbs
        .map { meta, image ->
            // Determine grouping key based on parameter
            def group_key
            def group_id

            if (barcoding_illumapply_grouping == "site") {
                // Site-level grouping (current behavior)
                group_key = meta.subMap(['batch', 'plate', 'well', 'site', 'arm'])
                group_id = "${meta.batch}_${meta.plate}_${meta.well}_Site${meta.site}"
            }
            else {
                // Well-level grouping (new behavior)
                // Site is NOT in the grouping key, but preserved in image metadata
                group_key = meta.subMap(['batch', 'plate', 'well', 'arm'])
                group_id = "${meta.batch}_${meta.plate}_${meta.well}"
            }

            // illumapply's cppipe selects input images named Orig{channel} /
            // Cycle{NN}_Orig{channel}; the Cycle prefix is added downstream by
            // generate_load_data_csv.py when the group spans >1 cycle.
            [group_key + [id: group_id], expandImageChannels(meta, image, 'Orig'), image]
        }
        .groupTuple()
        .map { group_meta, images_meta_list, images_list ->
            def image_metas = images_meta_list.flatten()
            // Get unique cycles and channels for this group
            // For barcoding, we expect multiple cycles
            def all_cycles = image_metas.collect { m -> m.cycle }.findAll { c -> c != null }.unique().sort()
            def unique_cycles = all_cycles.size() > 1 ? all_cycles : null
            def all_channels = image_metas.channel.unique().join(",")
            // See the illumcalc staged_names comment above for why this exists.
            def staged_names = images_meta_list.collect { it[0].filename }

            // Return tuple: (shared meta, channels, cycles, images, load_data metadata, staged names)
            [group_meta, all_channels, unique_cycles, images_list, buildLoadDataMetadata(group_meta, image_metas), staged_names]
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
            [plate_key, site_meta, channels, cycles, images, image_metas, staged_names]
        }
        .combine(ch_npy_by_plate, by: 0)
        .map { _plate_key, site_meta, channels, cycles, images, image_metas, staged_names, npy_files ->
            [site_meta, channels, cycles, images, image_metas, staged_names, npy_files]
        }

    // Apply illumination correction to images (no QC attached here - alignment/QC
    // now happens downstream, post-stitch, in STITCH_ALIGN_CROP_JOINT)
    CELLPROFILER_ILLUMAPPLY_BARCODING_PRESTITCH(
        ch_illumapply_input,
        barcoding_illumapply_cppipe,
        true,
    )
    ch_versions = ch_versions.mix(CELLPROFILER_ILLUMAPPLY_BARCODING_PRESTITCH.out.versions)
    // Merge load_data CSVs per plate
    CELLPROFILER_ILLUMAPPLY_BARCODING_PRESTITCH.out.load_data_csv.collectFile(keepHeader: true, skip: 1) { meta, csv ->
        def dir = file("${outdir}/workspace/load_data_csv/${meta.batch}/${meta.plate}")
        dir.mkdirs()
        [
            "${dir}/barcoding-illumapply.load_data.csv",
            csv.text.replaceFirst(/(?m)^(.*)$/) { line ->
                line[0]
                    .replace('FinalFileName_', '__FINAL__')
                    .replace('FileName_', 'StagedFileName_')
                    .replace('__FINAL__', 'FileName_')
            },
        ]
    }

    // ILLUMAPPLY outputs may be per site or per well depending on grouping mode,
    // and always bundle every cycle together. Normalize to per-(site, cycle) first
    // (widening the original site-only filename-regex recovery to also recover
    // cycle - barcoding filenames already carry a _CycleNN_ token), then regroup
    // to (well, cycle) level for STITCH - one task per cycle, mirroring
    // cellpainting_pre_stitch's ch_corrected_images_by_well.
    ch_corr_images_by_site = CELLPROFILER_ILLUMAPPLY_BARCODING_PRESTITCH.out.corrected_images.flatMap { group_meta, images, _csv ->
        // Group images by (site, cycle) based on filename
        def images_by_site_cycle = images.groupBy { img ->
            // Extract site and cycle from filename: Plate_X_Well_Y_Site_Z_Cycle01_DNA.tiff
            def m = (img.name =~ /.*_Site_?(\d+)_Cycle(\d+)_/)
            m ? [site: m[0][1] as Integer, cycle: m[0][2] as Integer] : [site: group_meta.site, cycle: group_meta.cycle]
        }

        // Create one tuple per (site, cycle) with all its images
        images_by_site_cycle.collect { key, site_cycle_images ->
            def site_cycle_meta = group_meta.clone()
            site_cycle_meta.site = key.site
            site_cycle_meta.cycle = key.cycle
            site_cycle_meta.id = "${group_meta.batch}_${group_meta.plate}_${group_meta.well}_Site${key.site}_Cycle${key.cycle}"
            [site_cycle_meta, site_cycle_images]
        }
    }

    ch_corrected_images_by_well = ch_corr_images_by_site
        .map { meta, images ->
            // Create well+cycle key (without site or channels - channels is
            // descriptive, order-sensitive text, not a legitimate grouping key)
            def well_key = meta.subMap(['batch', 'plate', 'well', 'arm']) + [
                cycle: meta.cycle,
                id: "${meta.batch}_${meta.plate}_${meta.well}_Cycle${meta.cycle}",
            ]
            [well_key, meta.site, images]
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
