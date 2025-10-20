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
import sys
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
    },
    'preprocess': {
        'description': 'Barcoding preprocessing - uses cycle-based corrected images',
        'file_pattern': r'Plate_.*_Well_.*_Site_.*_Cycle\d+_(DNA|DAPI|[ACGT])\.tiff?$',
        'metadata_cols': ['Metadata_Plate', 'Metadata_Site', 'Metadata_Well', 'Metadata_Well_Value'],
        'file_cols_template': ['FileName_Cycle{cycle}_{channel}'],
        'include_illum_files': False,
        'parse_function': 'parse_preprocess_image'
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


def parse_preprocess_image(filename: str) -> Optional[Dict]:
    """
    Parse barcoding preprocess image filename with cycle information.

    Pattern: Plate_{plate}_Well_{well}_Site_{site}_Cycle{cycle}_{channel}.tiff
    where channel is one of A, C, G, T (or DNA/DAPI for Cycle01)

    Returns dict with: plate, well, site, cycle, channel
    """
    # Try standard pattern first (for A, C, G, T)
    pattern = r'Plate_(.+?)_Well_(.+?)_Site_(\d+)_Cycle(\d+)_([ACGT])\.tiff?'
    match = re.match(pattern, filename)

    if match:
        return {
            'plate': match.group(1),
            'well': match.group(2),
            'site': int(match.group(3)),
            'cycle': match.group(4),  # Keep as string (e.g., "01", "02", "03")
            'channel': match.group(5)
        }

    # Try DNA pattern for Cycle01 (accepts both DNA and DAPI, normalizes to DNA)
    dna_pattern = r'Plate_(.+?)_Well_(.+?)_Site_(\d+)_Cycle(\d+)_(DNA|DAPI)\.tiff?'
    dna_match = re.match(dna_pattern, filename)

    if dna_match:
        return {
            'plate': dna_match.group(1),
            'well': dna_match.group(2),
            'site': int(dna_match.group(3)),
            'cycle': dna_match.group(4),
            'channel': 'DNA'  # Normalize DAPI to DNA for consistency
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

    # Validate input directory exists
    if not os.path.isdir(images_dir):
        raise FileNotFoundError(f"Images directory not found: {images_dir}")

    # Find image files
    pattern = os.path.join(images_dir, "**", "*")
    try:
        all_files = glob.glob(pattern, recursive=True)
    except Exception as e:
        raise IOError(f"Error searching for files in {images_dir}: {e}")

    # Filter to actual files matching pattern
    image_files = [
        f for f in all_files
        if os.path.isfile(f) and re.search(config['file_pattern'], os.path.basename(f))
    ]

    if not image_files:
        raise ValueError(
            f"No image files found matching pattern '{config['file_pattern']}' in {images_dir}\n"
            f"Expected pattern for {pipeline_type}: {config['description']}"
        )

    print(f"✓ Found {len(image_files)} image files to process", file=sys.stderr)

    # Group files
    grouped = {}
    parse_errors = []
    missing_metadata = []

    for img_path in image_files:
        filename = os.path.basename(img_path)

        try:
            parsed = parse_func(filename)
        except Exception as e:
            parse_errors.append((filename, str(e)))
            print(f"⚠ Error parsing filename '{filename}': {e}", file=sys.stderr)
            continue

        if not parsed:
            parse_errors.append((filename, "Failed to match expected pattern"))
            print(f"⚠ Skipping '{filename}': does not match expected pattern", file=sys.stderr)
            continue

        # Validate required metadata fields
        try:
            plate = parsed.get('plate', infer_plate_from_path(img_path))
            well = parsed['well']
            site = parsed['site']
        except KeyError as e:
            missing_metadata.append((filename, str(e)))
            print(f"⚠ Missing required metadata in '{filename}': {e}", file=sys.stderr)
            continue

        key = (plate, well, site)

        if key not in grouped:
            grouped[key] = {'images': {}, 'illum': {}}

        # Store based on whether it's multi-channel, single-channel, or cycle-based
        try:
            if 'channels' in parsed:
                # Multi-channel image - store with frames info
                grouped[key]['images']['_file'] = filename
                grouped[key]['images']['_parsed'] = parsed
            elif 'cycle' in parsed:
                # Cycle-based image (for preprocess pipeline)
                cycle = parsed['cycle']
                channel = parsed['channel']
                cycle_channel_key = f"Cycle{cycle}_{channel}"
                grouped[key]['images'][cycle_channel_key] = filename
            else:
                # Single-channel image
                channel = parsed['channel']
                grouped[key]['images'][channel] = filename
        except KeyError as e:
            missing_metadata.append((filename, f"Missing channel information: {e}"))
            print(f"⚠ Error processing '{filename}': Missing channel information: {e}", file=sys.stderr)
            continue

    # Report parsing summary
    if parse_errors:
        print(f"\n⚠ Warning: Failed to parse {len(parse_errors)} file(s)", file=sys.stderr)
    if missing_metadata:
        print(f"⚠ Warning: {len(missing_metadata)} file(s) had missing metadata", file=sys.stderr)

    print(f"✓ Successfully grouped {len(grouped)} unique (plate, well, site) combinations", file=sys.stderr)

    # Collect illumination files if needed
    if config['include_illum_files'] and illum_dir:
        if not os.path.isdir(illum_dir):
            raise FileNotFoundError(f"Illumination directory not found: {illum_dir}")

        illum_pattern = os.path.join(illum_dir, "*.npy")
        illum_files = glob.glob(illum_pattern)

        if not illum_files:
            raise ValueError(f"No illumination files (*.npy) found in {illum_dir}")

        print(f"✓ Found {len(illum_files)} illumination file(s)", file=sys.stderr)

        illum_matched = 0
        for illum_path in illum_files:
            filename = os.path.basename(illum_path)
            # Pattern: Plate1_IllumChannelName.npy
            match = re.match(r'(.+?)_Illum(.+?)\.npy', filename)
            if match:
                plate = match.group(1)
                channel = match.group(2)

                # Add to all entries for this plate
                matched_this_file = False
                for (p, w, s) in grouped.keys():
                    if p == plate:
                        grouped[(p, w, s)]['illum'][channel] = filename
                        matched_this_file = True

                if matched_this_file:
                    illum_matched += 1
            else:
                print(f"⚠ Illumination file '{filename}' does not match expected pattern", file=sys.stderr)

        print(f"✓ Matched {illum_matched} illumination file(s) to image groups", file=sys.stderr)

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

    if not grouped:
        raise ValueError("No grouped files to generate CSV rows from")

    # Apply subsampling if needed
    all_sites = sorted(set(site for _, _, site in grouped.keys()))
    selected_sites = [site for i, site in enumerate(all_sites) if i % range_skip == 0]

    if not selected_sites:
        raise ValueError(f"No sites selected with range_skip={range_skip}")

    print(f"✓ Selected {len(selected_sites)} site(s) from {len(all_sites)} total sites", file=sys.stderr)

    rows = []
    row_errors = []

    for (plate, well, site), file_data in sorted(grouped.items()):
        if site not in selected_sites:
            continue

        try:
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

                if 'channels' not in parsed or 'frames' not in parsed:
                    raise ValueError(f"Missing channels or frames data for {filename}")

                # Add FileName and Frame for each channel
                for channel in parsed['channels']:
                    if channel not in parsed['frames']:
                        raise KeyError(f"Frame information missing for channel '{channel}'")

                    frame = parsed['frames'][channel]
                    row[f'FileName_Orig{channel}'] = filename
                    row[f'Frame_Orig{channel}'] = frame

                    # Add illumination file if available
                    if channel in file_data['illum']:
                        row[f'FileName_Illum{channel}'] = file_data['illum'][channel]

                # Validate we have all required illumination files
                if config['include_illum_files']:
                    missing_illum = [ch for ch in parsed['channels'] if ch not in file_data['illum']]
                    if missing_illum:
                        print(
                            f"⚠ Missing illumination files for channels {missing_illum} "
                            f"in {plate}/{well}/Site{site}",
                            file=sys.stderr
                        )
            else:
                # Single-channel or cycle-based files
                if not file_data['images']:
                    raise ValueError(f"No image files for {plate}/{well}/Site{site}")

                # Check if this is cycle-based (preprocess pipeline)
                is_cycle_based = any('Cycle' in key for key in file_data['images'].keys())

                if is_cycle_based:
                    # For preprocess: add FileName_Cycle{cycle}_{channel} columns
                    for cycle_channel_key, filename in sorted(file_data['images'].items()):
                        # cycle_channel_key is like "Cycle01_A", "Cycle01_C", etc.
                        row[f'FileName_{cycle_channel_key}'] = filename
                else:
                    # For other pipelines: add FileName_{channel} columns
                    for channel, filename in sorted(file_data['images'].items()):
                        row[f'FileName_{channel}'] = filename

            rows.append(row)

        except (KeyError, ValueError) as e:
            row_errors.append((f"{plate}/{well}/Site{site}", str(e)))
            print(f"⚠ Error generating row for {plate}/{well}/Site{site}: {e}", file=sys.stderr)
            continue

    if row_errors:
        print(f"\n⚠ Warning: Failed to generate {len(row_errors)} row(s)", file=sys.stderr)

    if not rows:
        raise ValueError(
            f"Failed to generate any valid CSV rows. "
            f"Processed {len(grouped)} file groups, encountered {len(row_errors)} errors"
        )

    print(f"✓ Generated {len(rows)} CSV row(s)", file=sys.stderr)

    return rows


def write_csv(rows: List[Dict], output_file: str, metadata_cols: List[str]):
    """Write rows to CSV with proper column ordering."""
    if not rows:
        raise ValueError("No rows to write - cannot create empty CSV")

    # Get all column names
    all_cols = set()
    for row in rows:
        all_cols.update(row.keys())

    # Validate that metadata columns are present
    missing_meta = [col for col in metadata_cols if col not in all_cols]
    if missing_meta:
        print(
            f"⚠ Warning: Expected metadata columns not found in data: {missing_meta}",
            file=sys.stderr
        )

    # Order: metadata columns first, then sorted FileName/Frame columns
    file_cols = sorted([c for c in all_cols if c not in metadata_cols])
    fieldnames = metadata_cols + file_cols

    print(f"✓ Writing CSV with {len(fieldnames)} columns: {', '.join(fieldnames)}", file=sys.stderr)

    try:
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except IOError as e:
        raise IOError(f"Failed to write CSV to {output_file}: {e}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error writing CSV: {e}")

    print(f"✓ Successfully generated {output_file} with {len(rows)} rows")


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

    # Validate arguments
    config = PIPELINE_CONFIGS[args.pipeline_type]
    if config['include_illum_files'] and not args.illum_dir:
        parser.error(f"--illum-dir required for pipeline type '{args.pipeline_type}'")

    if args.range_skip < 1:
        parser.error(f"--range-skip must be >= 1, got {args.range_skip}")

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"CellProfiler load_data.csv Generator", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"Pipeline type: {args.pipeline_type}", file=sys.stderr)
    print(f"Description: {config['description']}", file=sys.stderr)
    print(f"Images directory: {args.images_dir}", file=sys.stderr)
    if args.illum_dir:
        print(f"Illumination directory: {args.illum_dir}", file=sys.stderr)
    if args.range_skip > 1:
        print(f"Subsampling: every {args.range_skip} sites", file=sys.stderr)
    print(f"Output file: {args.output}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    try:
        # Collect and group files
        print(f"Step 1/3: Collecting and grouping files...", file=sys.stderr)
        grouped = collect_and_group_files(
            args.images_dir,
            args.pipeline_type,
            args.illum_dir
        )

        # Generate rows
        print(f"\nStep 2/3: Generating CSV rows...", file=sys.stderr)
        rows = generate_csv_rows(grouped, args.pipeline_type, args.range_skip)

        # Write CSV
        print(f"\nStep 3/3: Writing CSV file...", file=sys.stderr)
        write_csv(rows, args.output, config['metadata_cols'])

        print(f"\n{'='*60}", file=sys.stderr)
        print(f"✓ SUCCESS: CSV generation completed", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)

        return 0

    except FileNotFoundError as e:
        print(f"\n❌ ERROR: File or directory not found", file=sys.stderr)
        print(f"   {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"\n❌ ERROR: Invalid data or configuration", file=sys.stderr)
        print(f"   {e}", file=sys.stderr)
        return 1
    except IOError as e:
        print(f"\n❌ ERROR: File I/O error", file=sys.stderr)
        print(f"   {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"\n❌ ERROR: Missing required metadata field", file=sys.stderr)
        print(f"   {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: Unexpected error occurred", file=sys.stderr)
        print(f"   {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        print(f"\nTraceback:", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
