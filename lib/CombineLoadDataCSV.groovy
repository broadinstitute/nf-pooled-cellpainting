/**
 * Utility class for combining load_data.csv files from process outputs
 */
class CombineLoadDataCSV {

    /**
     * Combines multiple load_data.csv files into a single file per group
     *
     * This function takes a channel of [meta, csv] tuples, groups them by specified
     * meta keys, and combines the CSV files while preserving the header from the first file.
     *
     * @param input_channel Channel containing [meta, csv] tuples
     * @param grouping_keys List of meta keys to group by (e.g., ['batch', 'plate', 'arm'])
     * @param output_dir Directory to store combined CSV files
     * @param output_prefix Prefix for output filename (e.g., 'barcoding-preprocess', 'cellpainting-segcheck')
     * @return Channel with combined CSV files
     *
     * Example usage:
     *   def combined = CombineLoadDataCSV.combine(
     *       CELLPROFILER_PREPROCESS.out.load_data_csv,
     *       ['batch', 'plate', 'arm'],
     *       "${params.outdir}/workspace/load_data_csv",
     *       'barcoding-preprocess'
     *   )
     *
     * Output filename format: {output_prefix}.{batch}-{plate}-{arm}_combined_load_data.csv
     */
    static def combine(input_channel, List<String> grouping_keys, String output_dir, String output_prefix) {
        return input_channel
            .map { meta, csv ->
                [meta.subMap(grouping_keys), csv]
            }
            .groupTuple()
            .flatMap { meta, csv_files ->
                csv_files.collect { csv ->
                    [meta, csv]
                }
            }
            .collectFile(keepHeader: true, skip: 1, storeDir: output_dir) { meta, csv ->
                def meta_values = grouping_keys.collect { meta[it] }.join('-')
                def combined_name = "${output_prefix}.${meta_values}_combined_load_data.csv"
                [combined_name, csv]
            }
    }
}
