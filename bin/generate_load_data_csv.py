#!/usr/bin/env python3
"""
General-purpose load_data.csv generator for CellProfiler pipelines.

This script generates load_data.csv files for different CellProfiler pipeline steps.
It automatically detects the pipeline type based on input files and generates the
appropriate CSV structure.

Uses only Python standard library - no external dependencies.
"""

import argparse
import csv
import glob
import os
import re
from typing import Dict, List, Tuple, Optional


# Pipeline configuration - defines the CSV structure for each pipeline step
PIPELINE_CONFIGS = {
    'illumcalc': {
        'description': 'Illumination calculation - uses original multi-channel images',
        'file_pattern': r'.*\.ome\.tiff?$',
        'metadata_cols': ['Metadata_Plate', 'Metadata_Well', 'Metadata_Site'],
        'file_cols_template': ['FileName_Orig{channel}', 'Frame_Orig{channel}'],
        'include_illum_files': False,
        'parse_function': 'parse_original_image'
    },
    'illumapply': {
        'description': 'Illumination correction - uses original images + illumination functions',
        'file_pattern': r'.*\.ome\.tiff?$',
        'metadata_cols': ['Metadata_Plate', 'Metadata_Well', 'Metadata_Site'],
        'file_cols_template': ['FileName_Orig{channel}', 'Frame_Orig{channel}', 'FileName_Illum{channel}'],
        'include_illum_files': True,
        'parse_function': 'parse_original_image'
    },
    'segcheck': {
        'description': 'Segmentation check - uses corrected images',
        'file_pattern': r'Plate_.*_Well_.*_Site_.*_Corr.*\.tiff?$',
        'metadata_cols': ['Metadata_Plate', 'Metadata_Site', 'Metadata_Well', 'Metadata_Well_Value'],
        'file_cols_template': ['FileName_{channel}'],
        'include_illum_files': False,
        'parse_function': 'parse_corrected_image'
    },
    'analysis': {
        'description': 'Full analysis - uses corrected images',
        'file_pattern': r'Plate_.*_Well_.*_Site_.*_Corr.*\.tiff?$',
        'metadata_cols': ['Metadata_Plate', 'Metadata_Well', 'Metadata_Site'],
        'file_cols_template': ['FileName_{channel}'],
        'include_illum_files': False,
        'parse_function': 'parse_corrected_image'
    }
}


def parse_original_image(filename: str) -> Optional[Dict]:
    """
    Parse original multi-channel image filename.

    Pattern: WellA1_PointA1_0000_ChannelCHN1,CHN2,CHN3_Seq0000.ome.tiff

    Returns dict with: plate (if available), well, site, channels (list), frames (dict)
    """
    # Extract well, site, and channel info
    pattern = r'Well([A-Z]\d+)_Point[A-Z]\d+_(\d+)_Channel([^_]+)_Seq\d+\.ome\.tiff?'
    match = re.search(pattern, filename)

    if not match:
        return None

    well = match.group(1)
    site = int(match.group(2))
    channels_str = match.group(3)

    # Parse channels - could be comma-separated
    channels = [ch.strip() for ch in channels_str.split(',')]

    # Build frame mapping - each channel gets its sequential frame number
    frames = {ch: idx for idx, ch in enumerate(channels)}

    return {
        'well': well,
        'site': site,
        'channels': channels,
        'frames': frames
    }


def parse_corrected_image(filename: str) -> Optional[Dict]:
    """
    Parse corrected image filename.

    Pattern: Plate_{plate}_Well_{well}_Site_{site}_Corr{channel}.tiff

    Returns dict with: plate, well, site, channel
    """
    pattern = r'Plate_(.+?)_Well_(.+?)_Site_(\d+)_Corr(.+?)\.tiff?'
    match = re.match(pattern, filename)

    if match:
        return {
            'plate': match.group(1),
            'well': match.group(2),
            'site': int(match.group(3)),
            'channel': match.group(4)
        }
    return None


def infer_plate_from_path(file_path: str) -> str:
    """
    Try to infer plate name from file path.
    Looks for 'Plate{number}' pattern in the path.
    """
    match = re.search(r'Plate(\d+)', file_path)
    if match:
        return f'Plate{match.group(1)}'
    return 'Unknown'


def collect_and_group_files(
    images_dir: str,
    pipeline_type: str,
    illum_dir: Optional[str] = None
) -> Dict[Tuple, Dict]:
    """
    Collect and group files based on pipeline configuration.

    Returns:
        Dict mapping (plate, well, site) -> {'images': {...}, 'illum': {...}}
    """
    config = PIPELINE_CONFIGS[pipeline_type]
    parse_func = globals()[config['parse_function']]

    # Find image files
    pattern = os.path.join(images_dir, "**", "*")
    all_files = glob.glob(pattern, recursive=True)

    # Filter to actual files matching pattern
    image_files = [
        f for f in all_files
        if os.path.isfile(f) and re.search(config['file_pattern'], os.path.basename(f))
    ]

    if not image_files:
        raise ValueError(f"No image files found matching pattern in {images_dir}")

    # Group files
    grouped = {}

    for img_path in image_files:
        filename = os.path.basename(img_path)
        parsed = parse_func(filename)

        if not parsed:
            continue

        # Build key
        plate = parsed.get('plate', infer_plate_from_path(img_path))
        well = parsed['well']
        site = parsed['site']
        key = (plate, well, site)

        if key not in grouped:
            grouped[key] = {'images': {}, 'illum': {}}

        # Store based on whether it's multi-channel or single-channel
        if 'channels' in parsed:
            # Multi-channel image - store with frames info
            grouped[key]['images']['_file'] = filename
            grouped[key]['images']['_parsed'] = parsed
        else:
            # Single-channel image
            channel = parsed['channel']
            grouped[key]['images'][channel] = filename

    # Collect illumination files if needed
    if config['include_illum_files'] and illum_dir:
        illum_pattern = os.path.join(illum_dir, "*.npy")
        illum_files = glob.glob(illum_pattern)

        for illum_path in illum_files:
            filename = os.path.basename(illum_path)
            # Pattern: Plate1_IllumChannelName.npy
            match = re.match(r'(.+?)_Illum(.+?)\.npy', filename)
            if match:
                plate = match.group(1)
                channel = match.group(2)

                # Add to all entries for this plate
                for (p, w, s) in grouped.keys():
                    if p == plate:
                        grouped[(p, w, s)]['illum'][channel] = filename

    return grouped


def generate_csv_rows(
    grouped: Dict,
    pipeline_type: str,
    range_skip: int = 1
) -> List[Dict]:
    """
    Generate CSV rows from grouped file data.
    """
    config = PIPELINE_CONFIGS[pipeline_type]

    # Apply subsampling if needed
    all_sites = sorted(set(site for _, _, site in grouped.keys()))
    selected_sites = [site for i, site in enumerate(all_sites) if i % range_skip == 0]

    rows = []

    for (plate, well, site), file_data in sorted(grouped.items()):
        if site not in selected_sites:
            continue

        # Build metadata columns
        row = {}
        if 'Metadata_Plate' in config['metadata_cols']:
            row['Metadata_Plate'] = plate
        if 'Metadata_Well' in config['metadata_cols']:
            row['Metadata_Well'] = well
        if 'Metadata_Site' in config['metadata_cols']:
            row['Metadata_Site'] = site
        if 'Metadata_Well_Value' in config['metadata_cols']:
            row['Metadata_Well_Value'] = well

        # Handle multi-channel files
        if '_file' in file_data['images']:
            parsed = file_data['images']['_parsed']
            filename = file_data['images']['_file']

            # Add FileName and Frame for each channel
            for channel in parsed['channels']:
                frame = parsed['frames'][channel]
                row[f'FileName_Orig{channel}'] = filename
                row[f'Frame_Orig{channel}'] = frame

                # Add illumination file if available
                if channel in file_data['illum']:
                    row[f'FileName_Illum{channel}'] = file_data['illum'][channel]
        else:
            # Single-channel files
            for channel, filename in sorted(file_data['images'].items()):
                row[f'FileName_{channel}'] = filename

        rows.append(row)

    return rows


def write_csv(rows: List[Dict], output_file: str, metadata_cols: List[str]):
    """Write rows to CSV with proper column ordering."""
    if not rows:
        raise ValueError("No rows to write")

    # Get all column names
    all_cols = set()
    for row in rows:
        all_cols.update(row.keys())

    # Order: metadata columns first, then sorted FileName/Frame columns
    file_cols = sorted([c for c in all_cols if c not in metadata_cols])
    fieldnames = metadata_cols + file_cols

    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✓ Generated {output_file} with {len(rows)} rows")


def main():
    parser = argparse.ArgumentParser(
        description='Generate load_data.csv for CellProfiler pipelines'
    )
    parser.add_argument(
        '--pipeline-type',
        required=True,
        choices=list(PIPELINE_CONFIGS.keys()),
        help='Pipeline step type'
    )
    parser.add_argument(
        '--images-dir',
        default='./images',
        help='Directory containing input images (default: ./images)'
    )
    parser.add_argument(
        '--illum-dir',
        help='Directory containing illumination .npy files (for illumapply)'
    )
    parser.add_argument(
        '--output',
        default='load_data.csv',
        help='Output CSV file path (default: load_data.csv)'
    )
    parser.add_argument(
        '--range-skip',
        type=int,
        default=1,
        help='Subsampling interval - use every Nth site (default: 1 = all sites)'
    )

    args = parser.parse_args()

    # Validate
    config = PIPELINE_CONFIGS[args.pipeline_type]
    if config['include_illum_files'] and not args.illum_dir:
        parser.error(f"--illum-dir required for pipeline type '{args.pipeline_type}'")

    print(f"Pipeline type: {args.pipeline_type}")
    print(f"Description: {config['description']}")
    print(f"Images directory: {args.images_dir}")
    if args.illum_dir:
        print(f"Illumination directory: {args.illum_dir}")

    # Collect and group files
    grouped = collect_and_group_files(
        args.images_dir,
        args.pipeline_type,
        args.illum_dir
    )

    # Generate rows
    rows = generate_csv_rows(grouped, args.pipeline_type, args.range_skip)

    # Write CSV
    write_csv(rows, args.output, config['metadata_cols'])

    if args.range_skip > 1:
        print(f"Subsampling: every {args.range_skip} sites")


if __name__ == '__main__':
    main()
