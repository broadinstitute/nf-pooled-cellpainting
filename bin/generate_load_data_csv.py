#!/usr/bin/env python3
"""
Generate load_data.csv for CELLPROFILER_SEGCHECK.

This script scans the staged images directory and generates a load_data.csv
file based on the corrected image filenames.

Expected filename pattern: Plate_{plate}_Well_{well}_Site_{site}_Corr{channel}.tiff
Example: Plate_Plate1_Well_A1_Site_0_CorrDNA.tiff

For Nextflow: All images are staged in ./images/, so we only need FileName columns.
Uses only Python standard library - no external dependencies.
"""

import argparse
import csv
import glob
import os
import re


def parse_corrected_image_filename(filename):
    """
    Parse a corrected image filename to extract metadata.

    Pattern: Plate_{plate}_Well_{well}_Site_{site}_Corr{channel}.tiff

    Returns:
        dict with keys: plate, well, site, channel
        None if filename doesn't match pattern
    """
    pattern = r'Plate_(.+?)_Well_(.+?)_Site_(\d+)_Corr(.+?)\.tiff'
    match = re.match(pattern, filename)

    if match:
        return {
            'plate': match.group(1),
            'well': match.group(2),
            'site': int(match.group(3)),
            'channel': match.group(4)
        }
    return None


def generate_segcheck_load_data(images_dir, output_file, range_skip=2):
    """
    Generate load_data.csv for segmentation check.

    Args:
        images_dir: Directory containing corrected images
        output_file: Output CSV file path
        range_skip: Subsampling interval (use every Nth site)
    """
    # Find all corrected image files
    pattern = os.path.join(images_dir, "Plate_*_Well_*_Site_*_Corr*.tiff")
    image_files = glob.glob(pattern)

    if not image_files:
        raise ValueError(f"No corrected images found in {images_dir}")

    # Parse filenames and group by (plate, well, site)
    grouped = {}

    for img_path in image_files:
        filename = os.path.basename(img_path)
        parsed = parse_corrected_image_filename(filename)
        if parsed:
            key = (parsed['plate'], parsed['well'], parsed['site'])
            if key not in grouped:
                grouped[key] = {}
            grouped[key][parsed['channel']] = filename

    # Get all unique sites and apply range_skip subsampling
    all_sites = sorted(set(site for _, _, site in grouped.keys()))
    selected_sites = [site for i, site in enumerate(all_sites) if i % range_skip == 0]

    # Build rows for CSV
    rows = []
    for (plate, well, site), channels_dict in sorted(grouped.items()):
        # Only include sites that match our subsampling
        if site not in selected_sites:
            continue

        row = {
            'Metadata_Plate': plate,
            'Metadata_Site': site,
            'Metadata_Well': well,
            'Metadata_Well_Value': well,
        }

        # Add FileName columns for each channel
        for channel, filename in sorted(channels_dict.items()):
            row[f'FileName_{channel}'] = filename

        rows.append(row)

    if not rows:
        raise ValueError(f"No images found after subsampling with range_skip={range_skip}")

    # Write CSV
    # Determine column order: metadata columns first, then FileName columns
    fieldnames = ['Metadata_Plate', 'Metadata_Site', 'Metadata_Well', 'Metadata_Well_Value']

    # Get all unique channel names from the data
    all_channels = set()
    for row in rows:
        for key in row.keys():
            if key.startswith('FileName_'):
                all_channels.add(key)

    # Add sorted FileName columns
    fieldnames.extend(sorted(all_channels))

    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {output_file} with {len(rows)} rows")
    print(f"Channels found: {sorted([ch.replace('FileName_', '') for ch in all_channels])}")
    print(f"Sites selected (every {range_skip}): {selected_sites}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate load_data.csv for CELLPROFILER_SEGCHECK'
    )
    parser.add_argument(
        '--images-dir',
        default='./images',
        help='Directory containing corrected images (default: ./images)'
    )
    parser.add_argument(
        '--output',
        default='load_data.csv',
        help='Output CSV file path (default: load_data.csv)'
    )
    parser.add_argument(
        '--range-skip',
        type=int,
        default=2,
        help='Subsampling interval - use every Nth site (default: 2)'
    )

    args = parser.parse_args()

    generate_segcheck_load_data(args.images_dir, args.output, args.range_skip)


if __name__ == '__main__':
    main()
