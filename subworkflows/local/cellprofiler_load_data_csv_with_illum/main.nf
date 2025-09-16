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
            
            def channels
            if (all_single_channels && has_original_channels) {
                // Single channels after splitting, use only the current channels
                channels = current_channels.sort()
            } else {
                // Multi-channel or original data, derive channels from comma-separated channels
                def all_channels = current_channels.collectMany { it.split(',') as List }.unique().sort()
                channels = all_channels
            }

            // Group images by well and site within this group
            def wells_data = [:] // Map: well_site -> [meta, images_by_channel]
            [meta_list, image_list].transpose().each { meta, image ->
                def well_key = "${meta.well}_${meta.site ?: 1}"
                if (!wells_data[well_key]) {
                    wells_data[well_key] = [meta: meta, images_by_channel: [:]]
                }
                wells_data[well_key].images_by_channel[meta.channels] = image
            }

            // Create a map of illumination files by channel
            def illum_files_by_channel = [:]
            illum_file_list.each { illum_file ->
                // Extract channel from illumination filename (format: "Plate_IllumChannelName.npy")
                def filename = illum_file.name
                def channel_match = filename =~ /.*_Illum(.+)\.npy$/
                if (channel_match) {
                    def channel = channel_match[0][1]
                    illum_files_by_channel[channel] = illum_file
                }
            }

            // Header: metadata, for each channel add FileName_Orig{channel}, FileName_Illum{channel}
            def orig_headers = channels.collect { "FileName_Orig${it}" }
            def illum_headers = channels.collect { "FileName_Illum${it}" }
            def header = (["Metadata_Batch", "Metadata_Plate", "Metadata_Well","Metadata_Site"] + orig_headers + illum_headers).join(',')

            // Content: one row per well+site
            def rows = wells_data.values().collect { well_data ->
                def meta = well_data.meta
                def images_by_channel = well_data.images_by_channel

                // Create image filename list in channel order
                // For multichannel images, the same image file is used for all channels
                def image_filenames = channels.collect { channel ->
                    if (all_single_channels && has_original_channels) {
                        // Single channel processing - each channel has its own image
                        images_by_channel[channel] ? images_by_channel[channel].name : ""
                    } else {
                        // Multichannel processing - find the image that contains all channels
                        def matching_image = images_by_channel.find { img_channels, _img -> 
                            img_channels.contains(channel)
                        }
                        matching_image ? matching_image.value.name : ""
                    }
                }

                // Create illumination filename list using actual files
                def illum_filenames = channels.collect { channel ->
                    illum_files_by_channel[channel] ? illum_files_by_channel[channel].name : ""
                }

                // Combine: image files + metadata + illum files
                def row = [meta.batch, meta.plate, meta.well, meta.site] + image_filenames + illum_filenames
                // Quote all values to handle filenames with commas
                def quoted_row = row.collect { value -> "\"${value}\"" }
                quoted_row.join(',')
            }

            def csv_content = ([header] + rows).join('\n')
            
            // Deduplicate image files to prevent staging collisions for multichannel TIFFs
            // Multiple channels may reference the same physical file
            def unique_images = image_list.unique { it.name }
            
            [group_meta, unique_images, illum_file_list, csv_content]
        }
        .collectFile(
            newLine: true,
            storeDir: "${workflow.workDir}/${workflow.sessionId}/cellprofiler/load_data_csvs_with_illum/${step_name}"
        ) { group_meta, _image_list, _illum_file_list, csv_content ->
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
        .map { _key, group_meta, _meta_list, image_list, _illum_key, _illum_id, _illum_group_meta, illum_file_list ->
            [group_meta.id, group_meta, image_list, illum_file_list]
        }
        .combine(ch_csv_files_with_id)
        .filter { group_id, _group_meta, _image_list, _illum_file_list, _load_data_csv, csv_group_id ->
            group_id == csv_group_id
        }
        .map { _group_id, group_meta, image_list, illum_file_list, load_data_csv, _csv_group_id ->
            [group_meta, image_list, illum_file_list, load_data_csv]
        }
        .set { ch_images_with_illum_load_data_csv }

    emit:
    images_with_illum_load_data_csv = ch_images_with_illum_load_data_csv    // channel: [ val(meta), [ list_of_images ], [ list_of_illumination_correction_files ], load_data_csv ]

}