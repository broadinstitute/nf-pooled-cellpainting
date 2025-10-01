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

                // Group by well+site and collect unique images that will actually be used
                def subdirs_by_cycle_site = [:]
                def images_by_cycle_site = [:] // Track which image to stage for each cycle+site

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

                        // Assign subdirectory for this cycle+site if not already assigned
                        def key = "${cycle}_${meta.site}"
                        if (!subdirs_by_cycle_site.containsKey(key)) {
                            // Track the image for this cycle+site (only once per unique cycle+site)
                            images_by_cycle_site[key] = image
                            // Assign subdir based on map size (1-indexed)
                            subdirs_by_cycle_site[key] = "img${images_by_cycle_site.size()}"
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

                    // Helper to get subdir by metadata
                    def getSubdir = { meta ->
                        def key = "${meta.cycle}_${meta.site}"
                        subdirs_by_cycle_site[key]
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
                                def subdir = getSubdir(meta)

                                orig_filename = "\"${subdir}/${image.name}\""

                                // Frame calculation
                                if (meta.channels.contains(',')) {
                                    // Multichannel image - find the channel position
                                    def split_channels = meta.channels.split(',').collect { it.trim() }
                                    orig_frame = split_channels.indexOf(channel)
                                    if (orig_frame < 0) orig_frame = 0
                                } else if (meta.original_channels && meta.original_channels.contains(',')) {
                                    // Single-channel split from multichannel - use original position
                                    def original_channels = meta.original_channels.split(',').collect { it.trim() }
                                    orig_frame = original_channels.indexOf(meta.channels)
                                    if (orig_frame < 0) orig_frame = 0
                                } else {
                                    // True single-channel image
                                    orig_frame = 0
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
                // Collect the unique images from the cycle+site map
                unique_images = images_by_cycle_site.values() as List

            } else {
                // Original non-cycle format
                // Group images by well+site to create one row per well+site combination
                def grouped_by_well_site = [meta_list, image_list].transpose().collect { meta, image ->
                    def group_key = meta.subMap(['batch', 'plate', 'well', 'site'])
                    [group_key, meta, image]
                }.groupBy { it[0] }

                // Header: metadata, for each channel add FileName_Orig{channel}, FileName_Illum{channel}, Frame_Orig{channel}, Frame_Illum{channel}
                def orig_filename_headers = channels.collect { "FileName_Orig${it}" }
                def illum_filename_headers = channels.collect { "FileName_Illum${it}" }
                def orig_frame_headers = channels.collect { "Frame_Orig${it}" }
                def illum_frame_headers = channels.collect { "Frame_Illum${it}" }
                def header = (["Metadata_Batch", "Metadata_Plate", "Metadata_Well","Metadata_Site"] + orig_filename_headers + illum_filename_headers + orig_frame_headers + illum_frame_headers).join(',')

                // Track images to stage and assign subdirectories
                def subdirs_by_filename = [:]
                def images_to_stage = []

                // Content: one row per well+site combination
                def rows = []
                grouped_by_well_site.each { well_site_meta, entries ->

                    // Create a map of images and metadata by channel for this well+site
                    def images_by_channel = [:]
                    def meta_by_channel = [:]
                    entries.each { entry ->
                        def meta = entry[1]
                        def image = entry[2]

                        // Assign subdirectory if not already assigned
                        if (!subdirs_by_filename.containsKey(image.name)) {
                            images_to_stage << image
                            subdirs_by_filename[image.name] = "img${images_to_stage.size()}"
                        }

                        if (meta.channels.contains(',')) {
                            // Multichannel image - same image for all channels
                            def split_channels = meta.channels.split(',').collect { it.trim() }
                            split_channels.each { channel ->
                                if (channels.contains(channel)) {
                                    images_by_channel[channel] = image
                                    meta_by_channel[channel] = meta
                                }
                            }
                        } else {
                            // Single channel image
                            if (channels.contains(meta.channels)) {
                                images_by_channel[meta.channels] = image
                                meta_by_channel[meta.channels] = meta
                            }
                        }
                    }

                    // Helper to get subdir by image filename
                    def getSubdir = { image ->
                        subdirs_by_filename[image.name]
                    }

                    // Create image filename list in channel order with subdirectory prefix
                    def image_filenames = channels.collect { channel ->
                        if (images_by_channel[channel]) {
                            def image = images_by_channel[channel]
                            def subdir = getSubdir(image)
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

                    // Create frame lists for original and illumination images
                    def orig_frames = channels.collect { channel ->
                        if (images_by_channel[channel] && meta_by_channel[channel]) {
                            def meta = meta_by_channel[channel]
                            def frame = 0

                            if (meta.channels.contains(',')) {
                                // Multichannel image - find the channel position
                                def split_channels = meta.channels.split(',').collect { it.trim() }
                                frame = split_channels.indexOf(channel)
                                if (frame < 0) frame = 0
                            } else if (meta.original_channels && meta.original_channels.contains(',')) {
                                // Single-channel split from multichannel - use original position
                                def original_channels = meta.original_channels.split(',').collect { it.trim() }
                                frame = original_channels.indexOf(meta.channels)
                                if (frame < 0) frame = 0
                            } else {
                                // True single-channel image
                                frame = 0
                            }
                            frame
                        } else {
                            0
                        }
                    }

                    def illum_frames = channels.collect { 0 } // Illumination images are always single-channel

                    // Combine: metadata + image files + illum files + orig frames + illum frames
                    def row_data = [
                        "\"${well_site_meta.batch}\"",
                        "\"${well_site_meta.plate}\"",
                        "\"${well_site_meta.well}\"",
                        "\"${well_site_meta.site}\""
                    ] + image_filenames + illum_filenames + orig_frames + illum_frames

                    rows << row_data.join(',')
                }

                csv_content = ([header] + rows).join('\n')
                unique_images = images_to_stage
            }

            [group_meta, unique_images, illum_file_list, csv_content, cycle_list]
        }
        .map { group_meta, unique_images, illum_file_list, csv_content, cycle_list ->
            // Write CSV file and keep all data
            def csv_file = file("${workflow.workDir}/${workflow.sessionId}/cellprofiler/load_data_csvs_with_illum/${step_name}/${group_meta.id}.csv")
            csv_file.parent.mkdirs()
            csv_file.text = csv_content
            [group_meta, unique_images, illum_file_list, csv_file, cycle_list]
        }
        .map { group_meta, unique_images, illum_file_list, csv_file, cycle_list ->
            // Output in expected format: [ val(meta), [ list_of_images ], [ list_of_illumination_correction_files ], load_data_csv ]
            [group_meta, unique_images, illum_file_list, csv_file]
        }
        .set { ch_images_with_illum_load_data_csv }

    emit:
    images_with_illum_load_data_csv = ch_images_with_illum_load_data_csv    // channel: [ val(meta), [ list_of_images ], [ list_of_illumination_correction_files ], load_data_csv ]

}
