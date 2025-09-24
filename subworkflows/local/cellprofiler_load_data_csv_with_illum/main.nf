// Adapted from nf-core/cellpainting: https://github.com/nf-core/cellpainting/blob/dev/subworkflows/local/cellprofiler_load_data_csv_with_illum/main.nf
// This subworkflow takes images from a samplesheet and creates
// CellProfiler-compatible load_data.csv files grouped by specified metadata keys
// with additional illumination correction file columns
workflow CELLPROFILER_LOAD_DATA_CSV_WITH_ILLUM {

    take:
    ch_samplesheet            // channel: [ val(meta), [ image ] ]
    grouping_keys             // value channel: list of keys to group by (e.g., ['batch','plate','well'])
    ch_illumination_correction // channel: [ val(meta), [illumination_correction] ]
    step_name                 // value channel: name of the pipeline step (determines working directory for load_data.csv files)
    has_cycles                // value channel: true if the data has cycles

    main:

    // Group images by the specified metadata keys
    ch_samplesheet
        .map { meta, image ->
            def group_meta = meta.subMap(grouping_keys) + [id: grouping_keys.collect { meta[it] }.join('_')]
            [group_meta, meta, image]
        }
        .groupTuple()
        .set { ch_images_grouped}

    // Store grouped images for later CSV generation
    ch_images_grouped
        .map { group_meta, meta_list, image_list ->
            [group_meta.id, group_meta, meta_list, image_list]
        }
        .set { ch_images_with_key }

    // Group illumination correction files by keys that exist in illum metadata
    ch_illumination_correction
        .map { illum_meta, illum_file_list ->
            def illum_grouping_keys = grouping_keys.findAll { illum_meta.containsKey(it) }
            def group_meta = illum_meta.subMap(illum_grouping_keys) + [id: illum_grouping_keys.collect { illum_meta[it] }.join('_')]
            [group_meta, illum_meta, illum_file_list]
        }
        .groupTuple()
        .map { group_meta, _illum_meta_list, illum_file_list ->
            [group_meta.id, group_meta, illum_file_list.flatten()]
        }
        .set { ch_illum_with_key }

    // Combine grouped images with illumination files and generate CSV
    ch_images_with_key
        .map { _key, group_meta, _meta_list, image_list ->
            def first_meta = _meta_list[0]
            def illum_keys = ['batch', 'plate'].findAll { first_meta.containsKey(it) }
            def illum_key = illum_keys.collect { first_meta[it] }.join('_')
            [_key, group_meta, _meta_list, image_list, illum_key]
        }
        .combine(ch_illum_with_key)
        .filter { _key, _group_meta, _meta_list, _image_list, illum_key, illum_id, _illum_group_meta, _illum_file_list ->
            illum_key == illum_id
        }
        .map { _key, group_meta, meta_list, image_list, _illum_key, _illum_id, _illum_group_meta, illum_file_list ->
            // Generate CSV content with actual illumination file names
            def has_original_channels = meta_list.any { it.original_channels != null }
            def current_channels = meta_list.collect { it.channels }.unique()
            def all_single_channels = current_channels.every { !it.contains(',') }

            // Extract cycles from meta.cycle for each image
            def cycle_list = [meta_list, image_list].transpose().collect { meta, image ->
                meta.cycle ?: null
            }.findAll { it != null }

            def channels
            if (all_single_channels && has_original_channels) {
                // Single channels after splitting, use only the current channels
                channels = current_channels.sort()
            } else {
                // Multi-channel or original data, derive channels from comma-separated channels
                def all_channels = current_channels.collectMany { it.split(',') as List }.unique().sort()
                channels = all_channels
            }

            // Create a map of illumination files by channel
            def illum_files_by_channel = [:]
            illum_file_list.each { illum_file ->
                // Extract channel from illumination filename (format: "Plate_CycleX_IllumChannelName.npy")
                def filename = illum_file.name
                def channel_match = filename =~ /.*_Cycle(\d+)_Illum(.+)\.npy$/
                if (channel_match) {
                    def cycle = channel_match[0][1]
                    def channel = channel_match[0][2]
                    if (!illum_files_by_channel[cycle]) {
                        illum_files_by_channel[cycle] = [:]
                    }
                    illum_files_by_channel[cycle][channel] = illum_file
                }
            }

            def csv_content
            def unique_images

            if (has_cycles) {
                // Cycle-based format: columns for each cycle
                def cycles = cycle_list.unique().sort()

                // Build headers: metadata, then for each cycle add FileName_CycleXX_{channel}, Frame_CycleXX_{channel}
                def base_headers = ["Metadata_Plate", "Metadata_Site", "Metadata_Well", "Metadata_Well_Value"]
                def filename_headers = []
                def frame_headers = []

                cycles.each { cycle ->
                    channels.each { channel ->
                        filename_headers << "FileName_Cycle${cycle.toString().padLeft(2, '0')}_Orig${channel}"
                        filename_headers << "FileName_Cycle${cycle.toString().padLeft(2, '0')}_Illum${channel}"
                        frame_headers << "Frame_Cycle${cycle.toString().padLeft(2, '0')}_Orig${channel}"
                        frame_headers << "Frame_Cycle${cycle.toString().padLeft(2, '0')}_Illum${channel}"
                    }
                }

                def header = (base_headers + filename_headers + frame_headers).join(',')

                // Group by well+site to create one row per well+site combination
                def grouped_by_well_site = [meta_list, image_list].transpose().collect { meta, image ->
                    def group_key = meta.subMap(['plate', 'well', 'site'])
                    [group_key, meta, image]
                }.groupBy { it[0] }

                def rows = []
                grouped_by_well_site.each { well_site_meta, entries ->
                    // Create data structures for this well+site
                    def images_by_cycle_channel = [:]

                    // Organize by cycle and channel
                    entries.each { entry ->
                        def meta = entry[1]
                        def image = entry[2]
                        def cycle = meta.cycle

                        if (!images_by_cycle_channel[cycle]) {
                            images_by_cycle_channel[cycle] = [:]
                        }

                        // For multichannel images, store the same image for all channels
                        if (meta.channels.contains(',')) {
                            def split_channels = meta.channels.split(',').collect { it.trim() }
                            split_channels.each { channel ->
                                if (channels.contains(channel)) {
                                    images_by_cycle_channel[cycle][channel] = [image: image, meta: meta]
                                }
                            }
                        } else {
                            if (channels.contains(meta.channels)) {
                                images_by_cycle_channel[cycle][meta.channels] = [image: image, meta: meta]
                            }
                        }
                    }

                    // Assign subdirectories based on the original image_list order (not grouped by cycle/channel)
                    def subdirs_by_image = [:]
                    image_list.eachWithIndex { image, index ->
                        subdirs_by_image[image] = "img${index + 1}"
                    }

                    // Build row data
                    def filename_values = []
                    def frame_values = []

                    cycles.each { cycle ->
                        channels.each { channel ->
                            // Original image filename
                            def orig_filename = ""
                            def orig_frame = 0

                            if (images_by_cycle_channel[cycle] && images_by_cycle_channel[cycle][channel]) {
                                def image_data = images_by_cycle_channel[cycle][channel]
                                def image = image_data.image
                                def meta = image_data.meta
                                def subdir = subdirs_by_image[image]

                                orig_filename = "\"${subdir}/${image.name}\""

                                // Frame calculation for multichannel images
                                if (meta.channels.contains(',')) {
                                    def split_channels = meta.channels.split(',').collect { it.trim() }
                                    orig_frame = split_channels.indexOf(channel)
                                    if (orig_frame < 0) orig_frame = 0
                                }
                            }

                            // Illumination filename
                            def illum_filename = ""
                            def illum_frame = 0

                            if (illum_files_by_channel[cycle.toString()] && illum_files_by_channel[cycle.toString()][channel]) {
                                illum_filename = "\"${illum_files_by_channel[cycle.toString()][channel].name}\""
                            }

                            filename_values << orig_filename
                            filename_values << illum_filename
                            frame_values << orig_frame
                            frame_values << illum_frame
                        }
                    }

                    // Create the row
                    def row_data = [
                        well_site_meta.plate,
                        well_site_meta.site,
                        well_site_meta.well,
                        well_site_meta.well
                    ] + filename_values + frame_values

                    rows << row_data.join(',')
                }

                csv_content = ([header] + rows).join('\n')
                unique_images = image_list

            } else {
                // Original non-cycle format
                // Group images by well+site to create one row per well+site combination
                def grouped_by_well_site = [meta_list, image_list].transpose().collect { meta, image ->
                    def group_key = meta.subMap(['batch', 'plate', 'well', 'site'])
                    [group_key, meta, image]
                }.groupBy { it[0] }

                // Header: metadata, for each channel add FileName_Orig{channel}, FileName_Illum{channel}
                def orig_headers = channels.collect { "FileName_Orig${it}" }
                def illum_headers = channels.collect { "FileName_Illum${it}" }
                def header = (["Metadata_Batch", "Metadata_Plate", "Metadata_Well","Metadata_Site"] + orig_headers + illum_headers).join(',')

                // Assign subdirectories based on unique images only
                def subdirs_by_image = [:]
                def distinct_images = image_list.unique()
                distinct_images.eachWithIndex { image, index ->
                    subdirs_by_image[image] = "img${index + 1}"
                }

                // Content: one row per well+site combination
                def rows = []
                grouped_by_well_site.each { well_site_meta, entries ->
                    // Create a map of images by channel for this well+site
                    def images_by_channel = [:]
                    entries.each { entry ->
                        def meta = entry[1]
                        def image = entry[2]

                        if (meta.channels.contains(',')) {
                            // Multichannel image - same image for all channels
                            def split_channels = meta.channels.split(',').collect { it.trim() }
                            split_channels.each { channel ->
                                if (channels.contains(channel)) {
                                    images_by_channel[channel] = image
                                }
                            }
                        } else {
                            // Single channel image
                            if (channels.contains(meta.channels)) {
                                images_by_channel[meta.channels] = image
                            }
                        }
                    }

                    // Create image filename list in channel order with subdirectory prefix
                    def image_filenames = channels.collect { channel ->
                        if (images_by_channel[channel]) {
                            def image = images_by_channel[channel]
                            def subdir = subdirs_by_image[image]
                            "\"${subdir}/${image.name}\""
                        } else {
                            "\"\""
                        }
                    }

                    // Create illumination filename list using actual files (non-cycle format)
                    def illum_filenames = channels.collect { channel ->
                        // For non-cycle format, look for files without cycle prefix
                        def matching_illum = illum_file_list.find { illum_file ->
                            def filename = illum_file.name
                            def channel_match = filename =~ /.*_Illum(.+)\.npy$/
                            channel_match && channel_match[0][1] == channel
                        }
                        matching_illum ? "\"${matching_illum.name}\"" : "\"\""
                    }

                    // Combine: metadata + image files + illum files
                    def row_data = [
                        "\"${well_site_meta.batch}\"",
                        "\"${well_site_meta.plate}\"",
                        "\"${well_site_meta.well}\"",
                        "\"${well_site_meta.site}\""
                    ] + image_filenames + illum_filenames

                    rows << row_data.join(',')
                }

                csv_content = ([header] + rows).join('\n')
                unique_images = image_list
            }

            [group_meta, unique_images, illum_file_list, csv_content, cycle_list]
        }
        .collectFile(
            newLine: true,
            storeDir: "${workflow.workDir}/${workflow.sessionId}/cellprofiler/load_data_csvs_with_illum/${step_name}"
        ) { group_meta, _image_list, _illum_file_list, csv_content, _cycle_list ->
            ["${group_meta.id}.csv", csv_content]
        }
        .map { load_data_csv ->
            def group_id = load_data_csv.baseName
            [load_data_csv, group_id]
        }
        .set { ch_csv_files_with_id }
    
    // Join the CSV files back with the original data
    ch_images_with_key
        .map { _key, group_meta, _meta_list, image_list ->
            // Create illumination key
            def first_meta = _meta_list[0]
            def illum_keys = ['batch', 'plate'].findAll { first_meta.containsKey(it) }
            def illum_key = illum_keys.collect { first_meta[it] }.join('_')
            [_key, group_meta, _meta_list, image_list, illum_key]
        }
        .combine(ch_illum_with_key)
        .filter { _key, _group_meta, _meta_list, _image_list, illum_key, illum_id, _illum_group_meta, _illum_file_list ->
            illum_key == illum_id
        }
        .map { _key, group_meta, meta_list, image_list, _illum_key, _illum_id, _illum_group_meta, illum_file_list ->
            // Extract cycles from meta.cycle for each image
            def cycle_list = [meta_list, image_list].transpose().collect { meta, image ->
                meta.cycle ?: null
            }.findAll { it != null }
            [group_meta.id, group_meta, image_list, illum_file_list, cycle_list]
        }
        .combine(ch_csv_files_with_id)
        .filter { group_id, _group_meta, _image_list, _illum_file_list, _cycle_list, _load_data_csv, csv_group_id ->
            group_id == csv_group_id
        }
        .map { _group_id, group_meta, image_list, illum_file_list, cycle_list, load_data_csv, _csv_group_id ->
            [group_meta, image_list, illum_file_list, load_data_csv]
        }
        .set { ch_images_with_illum_load_data_csv }

    emit:
    images_with_illum_load_data_csv = ch_images_with_illum_load_data_csv    // channel: [ val(meta), [ list_of_images ], [ list_of_illumination_correction_files ], load_data_csv ]

}