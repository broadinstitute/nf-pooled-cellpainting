process CELLPROFILER_ILLUMCALC {
    tag "${meta.id}"
    label 'cellprofiler_basic'

    container "${workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container
        ? 'oras://community.wave.seqera.io/library/cellprofiler:4.2.8--7c1bd3a82764de92'
        : 'community.wave.seqera.io/library/cellprofiler:4.2.8--aff0a99749304a7f'}"

    input:
    tuple val(meta), val(channels), val(cycle), path(images, stageAs: "images/img?/*"), val(image_metas)
    path illumination_cppipe
    val has_cycles

    output:
    tuple val(meta), path("*.npy"), emit: illumination_corrections
    tuple val(meta), path("load_data.csv"), emit: load_data_csv
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    // Serialize image metadata for load_data.csv generation
    // Base64 encode to reduce log verbosity
    def metadata_json_content = groovy.json.JsonOutput.toJson(image_metas)
    def metadata_base64 = metadata_json_content.bytes.encodeBase64().toString()
    def staged_list_base64 = images.toString().bytes.encodeBase64().toString()

    """
    # Create metadata JSON file from base64 (reduces log verbosity)
    echo '${metadata_base64}' | base64 -d > metadata.json
    echo '${staged_list_base64}' | base64 -d > staged_list.txt
    # Replace the metadata with staged paths instead - matched by real source
    # path, not position (Groovy array order and Nextflow's actual staged-file
    # order are not guaranteed to match for large plate-wide batches).

    python3 -c "
import json
import os
import sys

with open('metadata.json') as f:
    metadata = json.load(f)
with open('staged_list.txt') as f:
    staged_list = f.read()

staged_list = staged_list.split(' ')

# Two different physical files can share a basename (e.g. Phenix filenames
# reuse the same ch{N} index across different acquisition 'round'
# subfolders), so basename alone - or position - can't disambiguate them.
# Nextflow stages each file as a symlink back to its real source path, and
# every metadata entry already records that same absolute path as
# original_path - resolve each staged symlink's target and match on that
# instead, falling back to basename matching only if the staged copy isn't a
# symlink (e.g. a stageInMode: copy environment), preserving today's behavior
# there.
staged_by_realpath = {}
staged_by_basename = {}
for s in staged_list:
    rel = os.path.sep.join(s.split(os.path.sep)[1:])
    staged_by_basename.setdefault(s.split(os.path.sep)[-1], rel)
    real = os.path.realpath(s)
    if real != os.path.abspath(s):
        staged_by_realpath[real] = rel

missing = []
for entry in metadata:
    staged_path = None
    original_path = entry.get('original_path')
    if original_path:
        staged_path = staged_by_realpath.get(os.path.realpath(original_path))
    if staged_path is None:
        staged_path = staged_by_basename.get(entry['filename'])
    if staged_path is None:
        missing.append(entry['filename'])
    else:
        entry['filename'] = staged_path

if missing:
    print(f'Error: {len(missing)} metadata entries have no matching staged file, e.g. {missing[:10]}', file=sys.stderr)
    sys.exit(1)

with open('metadata.json','w') as f:
    json.dump(metadata,f)
"

    # Generate load_data.csv
    generate_load_data_csv.py \\
        --pipeline-type illumcalc \\
        --images-dir ./images \\
        --output load_data.csv \\
        --metadata-json metadata.json \\
        --channels "${channels}" \\
        --cycle-metadata-name "${params.cycle_metadata_name}" \\
        --outdir "${params.outdir}" \\
        --orig-channel-columns \\
        ${has_cycles ? '--has-cycles' : ''}

    # Check if illumination_cppipe ends with .template
    if [[ "${illumination_cppipe}" == *.template ]]; then
        # Handle single vs multiple channels for template files
        IFS=',' read -ra CHANNELS <<< "${channels}"
        if [ \${#CHANNELS[@]} -eq 1 ]; then
            # Single channel - simple replacement
            sed 's/{channel}/'\${CHANNELS[0]}'/g; s/{module_num}/2/g; s/{final_module_num}/6/g' ${illumination_cppipe} > illumination.cppipe
            total_modules=6  # LoadData + 4 channel modules + CreateBatchFiles
        else
            # Multiple channels - extract template blocks and repeat
            # Extract header (before CHANNEL_BLOCK_START)
            sed -n '1,/# CHANNEL_BLOCK_START/p' ${illumination_cppipe} | sed '\$d' > illumination.cppipe

            # Extract channel block template
            sed -n '/# CHANNEL_BLOCK_START/,/# CHANNEL_BLOCK_END/p' ${illumination_cppipe} | sed '1d;\$d' > channel_block.tmp

            # Generate blocks for each channel
            module_num=2
            for channel in \${CHANNELS[@]}; do
                # Process channel block in memory without temporary files
                current_module=\$module_num
                sed 's/{channel}/'\$channel'/g' channel_block.tmp | while IFS= read -r line; do
                    if [[ \$line == *"{module_num}"* ]]; then
                        echo "\$line" | sed 's/{module_num}/'\$current_module'/g'
                        current_module=\$((current_module + 1))
                    else
                        echo "\$line"
                    fi
                done >> illumination.cppipe

                echo "" >> illumination.cppipe
                module_num=\$((module_num + 4))
            done

            # Add footer (after CHANNEL_BLOCK_END)
            total_modules=\$((1 + \${#CHANNELS[@]} * 4 + 1))
            sed -n '/# CHANNEL_BLOCK_END/,\$p' ${illumination_cppipe} | sed '1d; s/{final_module_num}/'\$module_num'/g' >> illumination.cppipe
            rm channel_block.tmp
        fi

        # Update ModuleCount in header and remove any remaining markers
        sed -i 's/ModuleCount:X/ModuleCount:'\$total_modules'/; /^# CHANNEL_BLOCK_/d' illumination.cppipe
    else
        # Not a template file - use as-is
        cp ${illumination_cppipe} illumination.cppipe
    fi

    # Patch Base image location to use Default Input Folder (staged images)
    sed -i 's/Base image location:None|/Base image location:Default Input Folder|/g' illumination.cppipe

    cellprofiler -c -r \\
        -p illumination.cppipe \\
        -o . \\
        --data-file=load_data.csv \\
        --image-directory ./images/

    cat <<-END_VERSIONS > versions.yml
	"${task.process}":
	    cellprofiler: \$(cellprofiler --version)
	END_VERSIONS
    """

    stub:
    def cycle_prefix = meta.cycle ? "${meta.cycle}_" : ""
    """
    touch ${meta.plate}_${cycle_prefix}Illum${channels}.npy
    touch load_data.csv

    cat <<-END_VERSIONS > versions.yml
	"${task.process}":
	    cellprofiler: \$(cellprofiler --version)
	END_VERSIONS
    """
}
