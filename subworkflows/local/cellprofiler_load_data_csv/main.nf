
// This subworkflow takes images from a samplesheet and creates
// CellProfiler-compatible load_data.csv files grouped by specified metadata keys

workflow CELLPROFILER_LOAD_DATA_CSV {

    take:
    ch_samplesheet // channel: [ val(meta), [ image ] ]
    grouping_keys  // value channel: list of keys to group by (e.g., ['batch','plate','channel'])
    step_name      // value channel: name of the pipeline step (determines working directory for load_data.csv files)

    main:

    // Group images by the specified metadata keys
    ch_samplesheet
        .map { meta, image ->
            def keys = grouping_keys
            def group_key = meta.subMap(keys)
            def group_id = keys.collect { meta[it] }.join('_')

            [group_key + [id: group_id], meta, image]
        }
        .groupTuple()
        .set { ch_images_grouped }

    // Create load_data.csv files for each group
    ch_images_grouped
        .map { group_meta, meta_list, image_list ->
            // Derive channels dynamically from the metadata in this group
            // Determine if we're dealing with single-channel processing (after splitting) or multi-channel
            def has_original_channels = meta_list.any { it.original_channels != null }
            def current_channels = meta_list.collect { it.channels }.unique()
            def all_single_channels = current_channels.every { !it.contains(',') }
            
            def image_channels_header
            if (all_single_channels && has_original_channels) {
                // Scenario 2: Single channels after splitting, use only the current channels
                image_channels_header = current_channels
            } else if (all_single_channels && !has_original_channels) {
                // Scenario 1: Single channels without splitting
                image_channels_header = current_channels
            } else {
                // Scenario 3: Multi-channel images, split them into individual channels
                image_channels_header = meta_list.collect { meta ->
                    meta.channels.contains(',') ? meta.channels.split(',').collect { it.trim() } : [meta.channels]
                }.flatten().unique()
            }


            // def header = "FileName_Orig" + image_channels.join(',FileName_Orig') + ",Metadata_Batch,Metadata_Plate,Metadata_Well,Metadata_Col,Metadata_Row,Metadata_Site"
            def header = "Metadata_Plate,Metadata_Well,Metadata_Site," + "FileName_Orig" + image_channels_header.join(',FileName_Orig')+ "," + "Frame_Orig" + image_channels_header.join(',Frame_Orig')

            // Group by well+site within this group so we can create a single row per well+site
            def grouped_by_well = [meta_list, image_list].transpose().collect { meta, image ->
                def group_key = meta.subMap(['plate','well','batch','site'])
                [group_key, meta.channels, image]
            }.groupBy { it[0] }

            def rows = grouped_by_well.collect { row_meta, entries ->

                // Extract channels and images from the entries
                def row_channels = entries.collect { it[1] }  // Extract channels
                def row_images = entries.collect { it[2] }    // Extract images

                // Create a dictionary with the image_channels as keys and the images as values
                def images_by_channel = [row_channels, row_images].transpose().collectEntries { channels, image ->
                    [channels, image]
                }

                // Create lists of image filenames and frames in the order of the image_channels_header
                def (image_filenames, image_frames) = image_channels_header.collect { channel ->
                    // Find which channels string contains this channel
                    def matching_channels = images_by_channel.keySet().find { channels_string ->
                        channels_string.contains(',') ? 
                            channels_string.split(',').collect { it.trim() }.contains(channel) :
                            channels_string == channel
                    }
                    
                    if (matching_channels) {
                        def filename = "\"${images_by_channel[matching_channels].name}\""
                        def frame
                        
                        // Calculate frame based on the scenario
                        if (all_single_channels && has_original_channels) {
                            // Scenario 2: Single channels after splitting, use original_channels for frame calculation
                            def meta_for_image = [meta_list, image_list].transpose().find { _meta, _image -> 
                                _image == images_by_channel[matching_channels] 
                            }[0]
                            
                            if (meta_for_image.original_channels && meta_for_image.original_channels.contains(',')) {
                                def split_channels = meta_for_image.original_channels.split(',').collect { it.trim() }
                                frame = split_channels.indexOf(channel)
                            } else {
                                frame = 0
                            }
                        } else if (all_single_channels && !has_original_channels) {
                            // Scenario 1: Single channels without splitting, frame is always 0
                            frame = 0
                        } else {
                            // Scenario 3: Multi-channel images, calculate frame from the channel string
                            if (matching_channels.contains(',')) {
                                def split_channels = matching_channels.split(',').collect { it.trim() }
                                frame = split_channels.indexOf(channel)
                            } else {
                                frame = 0
                            }
                        }
                        
                        [filename, frame]
                    } else {
                        ["\"\"", ""]
                    }
                }.transpose()

                // Add metadata columns
                def row = [row_meta.plate, row_meta.well, row_meta.site] + image_filenames + image_frames
                row.join(',')
            }

            def csv_content = ([header] + rows).join('\n')
            [group_meta, csv_content]
        }
        .collectFile(
            newLine: true,
            storeDir: "${workflow.workDir}/${workflow.sessionId}/cellprofiler/load_data_csvs/${step_name}"
        ) { group_meta, csv_content ->
            ["${group_meta.id}.csv", csv_content]
        }
        .set { ch_load_data_csvs }

    // Join grouped images with their corresponding CSV files
    ch_images_grouped
        .map { group_meta, meta_list, image_list ->
            [group_meta.id, group_meta, meta_list, image_list]
        }
        .set { ch_images_with_key }

    ch_load_data_csvs
        .map { load_data_csv ->
            [load_data_csv.baseName, load_data_csv]
        }
        .set { ch_csvs_with_key }

    // Combine grouped images with their load_data.csv files
    ch_images_with_key
        .join(ch_csvs_with_key)
        .map { _key, group_meta, meta_list, image_list, load_data_csv ->
            // Remove duplicate image paths while preserving order
            def unique_image_list = image_list.unique() // Since we can point to the same image multiple times, we need to remove duplicates
            [group_meta, meta_list.channels.unique(), unique_image_list, load_data_csv]
        }
        .set { ch_images_with_load_data_csv }

    emit:
    images_with_load_data_csv      = ch_images_with_load_data_csv    // channel: [ val(meta), [ list_of_images ], load_data_csv ]

}
