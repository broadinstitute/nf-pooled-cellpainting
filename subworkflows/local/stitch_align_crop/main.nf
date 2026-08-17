/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT MODULES / SUBWORKFLOWS / FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
include { STITCH as STITCH_PAINTING } from '../../../modules/local/stitch'
include { STITCH as STITCH_BARCODING } from '../../../modules/local/stitch'
include { CROP as CROP_PAINTING } from '../../../modules/local/crop'
include { CROP as CROP_BARCODING } from '../../../modules/local/crop'
include { ALIGN_INTRAARM as ALIGN_INTRAARM_PAINTING } from '../../../modules/local/align_intraarm'
include { ALIGN_INTRAARM as ALIGN_INTRAARM_BARCODING } from '../../../modules/local/align_intraarm'
include { ALIGN_COMBINED } from '../../../modules/local/align_combined'
include { QC_MONTAGEILLUM as QC_MONTAGE_STITCH_PAINTING } from '../../../modules/local/qc/montageillum'
include { QC_MONTAGEILLUM as QC_MONTAGE_STITCH_BARCODING } from '../../../modules/local/qc/montageillum'

workflow STITCH_ALIGN_CROP_JOINT {
    take:
    ch_painting_corrected_by_well // channel: [ val(meta), [ images ] ] from CELLPAINTING_PRE_STITCH
    ch_barcoding_corrected_by_well // channel: [ val(meta), [ images ] ] from BARCODING_PRE_STITCH (all cycles)
    painting_round_or_square
    painting_quarter_if_round
    painting_overlap_pct
    painting_scalingstring
    painting_imperwell
    painting_rows
    painting_columns
    painting_stitchorder
    compress
    phenix
    painting_channame
    barcoding_round_or_square
    barcoding_quarter_if_round
    barcoding_overlap_pct
    barcoding_scalingstring
    barcoding_imperwell
    barcoding_rows
    barcoding_columns
    barcoding_stitchorder
    barcoding_channame
    tileperside
    final_tile_size
    shift_threshold
    corr_threshold

    main:
    ch_versions = channel.empty()

    //// STITCH each arm independently (unconditional - no qc_*_passed gate) ////

    ch_well_site_layouts_json = file("${projectDir}/assets/stitchcrop/well_site_layouts.json")

    ch_painting_stitch_out = STITCH_PAINTING(
        ch_painting_corrected_by_well,
        ch_well_site_layouts_json,
        painting_round_or_square,
        painting_quarter_if_round,
        painting_overlap_pct,
        painting_imperwell,
        painting_rows,
        painting_columns,
        painting_stitchorder,
        compress,
        phenix,
        painting_channame,
    )
    ch_versions = ch_versions.mix(ch_painting_stitch_out.versions)

    ch_barcoding_stitch_out = STITCH_BARCODING(
        ch_barcoding_corrected_by_well,
        ch_well_site_layouts_json,
        barcoding_round_or_square,
        barcoding_quarter_if_round,
        barcoding_overlap_pct,
        barcoding_imperwell,
        barcoding_rows,
        barcoding_columns,
        barcoding_stitchorder,
        compress,
        phenix,
        barcoding_channame,
    )
    ch_versions = ch_versions.mix(ch_barcoding_stitch_out.versions)

    //// QC montage of stitched (downsampled) images - side output only, does not gate anything ////

    ch_painting_stitch_qc = ch_painting_stitch_out.downsampled_images
        .map { meta, tiff_files -> [meta.subMap(['batch', 'plate']) + [arm: "painting"], tiff_files] }
        .groupTuple()
        .map { meta, tiff_files_list -> [meta, tiff_files_list.flatten().sort { it -> it.name }] }

    QC_MONTAGE_STITCH_PAINTING(
        ch_painting_stitch_qc,
        ".*\\.tiff\$",
    )
    ch_versions = ch_versions.mix(QC_MONTAGE_STITCH_PAINTING.out.versions)

    ch_barcoding_stitch_qc = ch_barcoding_stitch_out.downsampled_images
        .map { meta, tiff_files -> [meta.subMap(['batch', 'plate']) + [arm: "barcoding"], tiff_files] }
        .groupTuple()
        .map { meta, tiff_files_list -> [meta, tiff_files_list.flatten().sort { it -> it.name }] }

    QC_MONTAGE_STITCH_BARCODING(
        ch_barcoding_stitch_qc,
        ".*\\.tiff\$",
    )
    ch_versions = ch_versions.mix(QC_MONTAGE_STITCH_BARCODING.out.versions)

    //// Re-aggregate STITCH's per-(well, cycle) outputs back to per-well ////
    // STITCH now runs one task per (well, cycle) for both arms (for parallelism),
    // but ALIGN_INTRAARM needs every cycle of a well together to do cross-cycle
    // alignment. Regroup by well only, dropping cycle - first_site_index is
    // deliberately NOT part of the key since it's per-cycle and not guaranteed
    // identical across cycles (a cycle that only re-images a subset of sites,
    // e.g. painting's DNA2-only cycle, can have a different min site) - including
    // it would silently re-fragment groups, recreating the bug this fix addresses.

    ch_painting_stitch_by_well = ch_painting_stitch_out.stitched_images
        .map { meta, images -> [meta.subMap(['batch', 'plate', 'well', 'arm']) + [id: "${meta.batch}_${meta.plate}_${meta.well}"], meta.first_site_index, images] }
        .groupTuple()
        .map { well_meta, first_site_index_list, images_list -> [well_meta + [first_site_index: first_site_index_list.min()], images_list.flatten().sort { it -> it.name }] }

    ch_barcoding_stitch_by_well = ch_barcoding_stitch_out.stitched_images
        .map { meta, images -> [meta.subMap(['batch', 'plate', 'well', 'arm']) + [id: "${meta.batch}_${meta.plate}_${meta.well}"], meta.first_site_index, images] }
        .groupTuple()
        .map { well_meta, first_site_index_list, images_list -> [well_meta + [first_site_index: first_site_index_list.min()], images_list.flatten().sort { it -> it.name }] }

    //// Within-arm, cross-cycle alignment on full stitched images ////
    // Barcoding always has multiple cycles (parsed from filenames); painting only
    // does when its samplesheet's cycle_phenotyping column varies (cycle instead
    // comes from the "Cycle\d+_" infix bin/stitch.py adds to output filenames -
    // see its stitch_one_channel_set naming). Both arms run through ALIGN_INTRAARM
    // unconditionally - it's a no-op pass-through when only one cycle is present,
    // so painting's normal (single-cycle) case is unaffected.

    ch_painting_stitched_with_metas = ch_painting_stitch_by_well
        .map { meta, images ->
            def image_metas = [images].flatten().collect { img ->
                def cycle_channel_match = (img.name =~ /.*_Stitched_(?:Cycle(\d+)_)?Corr(.+?)\.tiff?$/)
                def cycle = (cycle_channel_match && cycle_channel_match[0][1]) ? cycle_channel_match[0][1] as Integer : null
                def channel = cycle_channel_match ? cycle_channel_match[0][2] : 'UNKNOWN'
                meta + [filename: img.name, cycle: cycle, channel: channel]
            }
            [meta, images, image_metas]
        }

    ALIGN_INTRAARM_PAINTING(ch_painting_stitched_with_metas, painting_channame, shift_threshold, corr_threshold)
    ch_versions = ch_versions.mix(ALIGN_INTRAARM_PAINTING.out.versions)

    ch_barcoding_stitched_with_metas = ch_barcoding_stitch_by_well
        .map { meta, images ->
            def image_metas = [images].flatten().collect { img ->
                def cycle_channel_match = (img.name =~ /.*_Cycle(\d+)_(.+?)\.tiff?$/)
                def cycle = cycle_channel_match ? cycle_channel_match[0][1] as Integer : null
                def channel = cycle_channel_match ? cycle_channel_match[0][2] : 'UNKNOWN'
                meta + [filename: img.name, cycle: cycle, channel: channel]
            }
            [meta, images, image_metas]
        }

    ALIGN_INTRAARM_BARCODING(ch_barcoding_stitched_with_metas, barcoding_channame, shift_threshold, corr_threshold)
    ch_versions = ch_versions.mix(ALIGN_INTRAARM_BARCODING.out.versions)

    //// Cross-arm join by well, then cross-arm alignment ////

    ch_painting_keyed = ALIGN_INTRAARM_PAINTING.out.aligned_images
        .map { meta, images -> [[batch: meta.batch, plate: meta.plate, well: meta.well], meta, images] }

    ch_barcoding_aligned_keyed = ALIGN_INTRAARM_BARCODING.out.aligned_images
        .map { meta, images -> [[batch: meta.batch, plate: meta.plate, well: meta.well], meta, images] }

    // NOTE: .join() silently drops any well missing from either arm's channel - if wells
    // seem to be going missing downstream, verify well-key sets from both arms match
    // (e.g. temporarily branch each *_keyed channel through .count().view() before the
    // join below; a channel can only be consumed once, so don't do this and the join in
    // the same run without splitting via .tap()/.multiMap{}).
    ch_joined = ch_painting_keyed
        .join(ch_barcoding_aligned_keyed, by: 0)
        .map { _key, p_meta, p_images, b_meta, b_images ->
            def combined_meta = [
                batch: p_meta.batch,
                plate: p_meta.plate,
                well: p_meta.well,
                id: "${p_meta.batch}_${p_meta.plate}_${p_meta.well}",
                first_site_index: p_meta.first_site_index,
            ]
            def painting_metas = [p_images].flatten().collect { img ->
                // "Cycle\d+_" infix always present now (see bin/stitch.py's
                // stitch_one_channel_set naming) - the optional match group here
                // just tolerates any pre-existing images without it.
                def cycle_channel_match = (img.name =~ /.*_Stitched_(?:Cycle(\d+)_)?Corr(.+?)\.tiff?$/)
                def cycle = (cycle_channel_match && cycle_channel_match[0][1]) ? cycle_channel_match[0][1] as Integer : null
                def channel = cycle_channel_match ? cycle_channel_match[0][2] : img.name.replaceAll(/.*_Corr(.+?)\.tiff?$/, '$1')
                [arm_source: 'cellpainting', filename: img.name, cycle: cycle, channel: channel] + combined_meta
            }
            def barcoding_metas = [b_images].flatten().collect { img ->
                def cycle_channel_match = (img.name =~ /.*_Cycle(\d+)_(.+?)\.tiff?$/)
                def cycle = cycle_channel_match ? cycle_channel_match[0][1] as Integer : null
                def channel = cycle_channel_match ? cycle_channel_match[0][2] : 'UNKNOWN'
                [arm_source: 'barcoding', filename: img.name, cycle: cycle, channel: channel] + combined_meta
            }
            [combined_meta, p_images, b_images, painting_metas + barcoding_metas]
        }

    ALIGN_COMBINED(ch_joined, painting_scalingstring, barcoding_scalingstring, painting_channame, barcoding_channame)
    ch_versions = ch_versions.mix(ALIGN_COMBINED.out.versions)

    //// CROP each arm's now-aligned full-well images separately ////

    ch_painting_crop_out = CROP_PAINTING(
        // ALIGN_COMBINED emits one shared meta (no arm field) for both arms' outputs -
        // re-tag arm explicitly so CROP's stub/script branching and downstream metadata are correct.
        ALIGN_COMBINED.out.painting_aligned_images.map { meta, images -> [meta + [arm: 'painting'], images] },
        tileperside,
        final_tile_size,
        compress,
        phenix,
        painting_channame,
    )
    ch_versions = ch_versions.mix(ch_painting_crop_out.versions)

    ch_barcoding_crop_out = CROP_BARCODING(
        ALIGN_COMBINED.out.barcoding_aligned_images.map { meta, images -> [meta + [arm: 'barcoding'], images] },
        tileperside,
        final_tile_size,
        compress,
        phenix,
        barcoding_channame,
    )
    ch_versions = ch_versions.mix(ch_barcoding_crop_out.versions)

    //// Re-split each arm's per-well cropped output into per-site tuples ////
    // Same pattern as cellpainting/main.nf:386-410 and barcoding/main.nf:440-463.

    ch_painting_cropped_images = ch_painting_crop_out.cropped_images
        .flatMap { meta, images ->
            def images_by_site = [images].flatten().groupBy { img ->
                def site_match = (img.name =~ /Site_(\d+)/)
                site_match ? site_match[0][1] as Integer : null
            }
            images_by_site.collect { site, site_images ->
                if (site == null) {
                    log.error("Could not parse site from painting cropped images")
                    return null
                }
                def new_meta = meta.subMap(['batch', 'plate', 'well', 'channels', 'arm']) + [
                    id: "${meta.batch}_${meta.plate}_${meta.well}_${site}",
                    site: site,
                ]
                [new_meta, site_images]
            }
        }
        .filter { item -> item != null }

    ch_barcoding_cropped_images = ch_barcoding_crop_out.cropped_images
        .flatMap { meta, images ->
            def images_by_site = [images].flatten().groupBy { img ->
                def site_match = (img.name =~ /Site_(\d+)/)
                site_match ? site_match[0][1] as Integer : null
            }
            images_by_site.collect { site, site_images ->
                if (site == null) {
                    log.error("Could not parse site from barcoding cropped images")
                    return null
                }
                def new_meta = meta.subMap(['batch', 'plate', 'well', 'cycles', 'arm']) + [
                    id: "${meta.batch}_${meta.plate}_${meta.well}_${site}",
                    site: site,
                ]
                [new_meta, site_images]
            }
        }
        .filter { item -> item != null }

    emit:
    painting_cropped_images = ch_painting_cropped_images // channel: [ val(meta), [ cropped_images ] ]
    barcoding_cropped_images = ch_barcoding_cropped_images // channel: [ val(meta), [ cropped_images ] ]
    versions = ch_versions // channel: [ versions.yml ]
}
