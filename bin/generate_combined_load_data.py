#!/usr/bin/env python3
"""
Simplified load_data.csv generator for CellProfiler Combined Analysis.

This script generates load_data.csv files specifically for combined analysis,
which uses both cropped cell painting and barcoding images.

Uses only Python standard library - no external dependencies.
"""

import argparse
import csv
import glob
import json
import os
import re
import sys
from typing import Dict, List, Tuple, Optional


def read_metadata_json(json_path: str) -> Dict:
    """
    Read and parse metadata from JSON file.

    Expected JSON structure:
    {
        "plate": "Plate1",       # required
        "well": "A1",            # optional - can parse from filename
        "site": 1,               # optional - can parse from filename
        "cycle": 1,              # optional
        "channels": "DNA,Phalloidin",  # optional
        "batch": "Batch1",       # optional
        "arm": "painting"        # optional
    }

    Returns dict with metadata. Only 'plate' is required.
    'well' and 'site' can be parsed from filenames if not provided.
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Metadata JSON file not found: {json_path}")

    try:
        with open(json_path, 'r') as f:
            metadata = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in metadata file {json_path}: {e}")
    except IOError as e:
        raise IOError(f"Error reading metadata file {json_path}: {e}")

    # Validate required fields - only plate is mandatory
    if not isinstance(metadata, dict):
        raise ValueError(f"Metadata JSON must be a dictionary, got {type(metadata)}")

    if 'plate' not in metadata:
        raise ValueError(
            "Metadata JSON is missing required field: 'plate'. "
            "Only 'plate' is mandatory; 'well' and 'site' are optional and can be parsed from filenames."
        )

    # Extract fields with defaults
    result = {
        'plate': metadata.get('plate'),
        'well': metadata.get('well'),
        'site': metadata.get('site'),
        'cycle': metadata.get('cycle'),
        'channels': metadata.get('channels'),
        'batch': metadata.get('batch'),
        'arm': metadata.get('arm')
    }

    # Convert site to int if present
    if result['site'] is not None:
        try:
            result['site'] = int(result['site'])
        except (ValueError, TypeError):
            raise ValueError(f"Invalid site value in metadata: {result['site']}, must be an integer")

    # Log warnings for missing optional fields
    if result['well'] is None:
        print("⚠ Warning: 'well' field not found in metadata JSON - will parse from filename", file=sys.stderr)
    if result['site'] is None:
        print("⚠ Warning: 'site' field not found in metadata JSON - will parse from filename", file=sys.stderr)

    print(f"✓ Loaded metadata from JSON: {json_path}", file=sys.stderr)
    print(f"  Plate: {result['plate']}, Well: {result['well']}, Site: {result['site']}", file=sys.stderr)

    return result


def parse_well_from_filename(filename: str) -> Optional[str]:
    """
    Parse well identifier from filename as fallback when not in JSON metadata.

    Pattern: Well_{well} in combined analysis filenames
    Example: Plate_Plate1_Well_A1_Site_1_Corr... -> "A1"

    Returns:
        Well identifier (e.g., "A1") or None if not found
    """
    match = re.search(r'Well_([A-Z]\d+)_', filename)
    if match:
        return match.group(1)
    return None


def parse_site_from_filename(filename: str) -> Optional[int]:
    """
    Parse site number from filename as fallback when not in JSON metadata.

    Pattern: Site_{site} in combined analysis filenames
    Example: Plate_Plate1_Well_A1_Site_1_Corr... -> 1

    Returns:
        Site number (int) or None if not found
    """
    match = re.search(r'Site_(\d+)_', filename)
    if match:
        return int(match.group(1))
    return None


def parse_combined_image(filename: str) -> Optional[Dict]:
    """
    Parse channel information from combined analysis image filenames.

    Patterns:
    - Cell painting corrected: Plate_*_Well_*_Site_*_Corr{channel}.tiff
    - Barcoding cropped with cycles: Plate_*_Well_*_Site_*_Cycle{cycle}_{channel}.tiff
      where cycle is 2-digit zero-padded (01, 02, ..., 10, 11, etc.)
      and channel is one of A, C, G, T, DNA, DAPI

    Returns dict with: type (barcoding/cellpainting), channel, and cycle (for barcoding only)
    Note: plate always comes from JSON metadata
    Note: well and site can come from JSON or be parsed from filename
    """
    # Try barcoding cropped pattern with cycles first
    # Note: cycle is 2-digit zero-padded (\d{2}) to handle cycles > 9
    barcode_cycle_pattern = r'Plate_[A-Za-z0-9]+_Well_[A-Z]\d+_Site_\d+_Cycle(\d{2})_([ACGT]|DNA|DAPI)\.tiff?'
    barcode_cycle_match = re.match(barcode_cycle_pattern, filename)

    if barcode_cycle_match:
        return {
            'cycle': barcode_cycle_match.group(1),
            'channel': 'DNA' if barcode_cycle_match.group(2) == 'DAPI' else barcode_cycle_match.group(2),
            'type': 'barcoding'
        }

    # Try cell painting corrected pattern
    cp_pattern = r'Plate_[A-Za-z0-9]+_Well_[A-Z]\d+_Site_\d+_Corr(.+?)\.tiff?'
    cp_match = re.match(cp_pattern, filename)

    if cp_match:
        return {
            'channel': cp_match.group(1),
            'type': 'cellpainting'
        }

    return None


def collect_and_group_files(images_dir: str, metadata: Dict) -> Dict[Tuple, Dict]:
    """
    Collect and group combined analysis image files.

    Args:
        images_dir: Directory containing image files
        metadata: Required metadata dict from JSON (must contain plate; well/site optional)

    Returns:
        Dict mapping (plate, well, site) -> {'barcoding': {...}, 'cellpainting': {...}}
    """
    # Validate metadata is provided and contains required fields
    if not metadata:
        raise ValueError("Metadata is required. JSON metadata file must be provided via --metadata-json")

    # Only plate is required - well and site can be parsed from filenames
    if 'plate' not in metadata:
        raise ValueError(
            "Metadata JSON is missing required field: 'plate'. "
            "Plate must always come from metadata JSON."
        )

    # Check if we need to parse well/site from filenames
    use_json_well = metadata.get('well') is not None
    use_json_site = metadata.get('site') is not None

    if use_json_well and use_json_site:
        print("✓ Using well and site from JSON metadata", file=sys.stderr)
    elif use_json_well:
        print("✓ Using well from JSON metadata, will parse site from filenames", file=sys.stderr)
    elif use_json_site:
        print("✓ Using site from JSON metadata, will parse well from filenames", file=sys.stderr)
    else:
        print("✓ Will parse both well and site from filenames (not in JSON metadata)", file=sys.stderr)

    # Validate input directory
    if not os.path.isdir(images_dir):
        raise FileNotFoundError(f"Images directory not found: {images_dir}")

    # Find all image files recursively
    pattern = os.path.join(images_dir, "**", "*")
    try:
        all_files = glob.glob(pattern, recursive=True)
    except Exception as e:
        raise IOError(f"Error searching for files in {images_dir}: {e}")

    # Combined analysis file pattern - matches new naming scheme
    file_pattern = r'(Plate_[A-Za-z0-9]+_Well_[A-Z]\d+_Site_\d+_Corr.*\.tiff?|Plate_[A-Za-z0-9]+_Well_[A-Z]\d+_Site_\d+_Cycle\d{2}_([ACGT]|DNA|DAPI)\.tiff?)$'

    # Filter to matching files
    image_files = [
        f for f in all_files
        if os.path.isfile(f) and re.search(file_pattern, os.path.basename(f))
    ]

    if not image_files:
        raise ValueError(
            f"No combined analysis image files found in {images_dir}\n"
            f"Expected patterns:\n"
            f"  - Cell painting: Plate_PlateID_Well_WellID_Site_#_CorrChannel.tiff\n"
            f"  - Barcoding with cycles: Plate_PlateID_Well_WellID_Site_#_Cycle##_Channel.tiff"
        )

    print(f"✓ Found {len(image_files)} image files to process", file=sys.stderr)

    # Group files by (plate, well, site)
    grouped = {}
    parse_errors = []
    missing_metadata = []

    # Extract plate from metadata (always required)
    plate = metadata['plate']

    for img_path in image_files:
        filename = os.path.basename(img_path)

        # Parse the filename for channel information
        try:
            parsed = parse_combined_image(filename)
        except Exception as e:
            parse_errors.append((filename, str(e)))
            print(f"⚠ Error parsing filename '{filename}': {e}", file=sys.stderr)
            continue

        if not parsed:
            parse_errors.append((filename, "Failed to match expected pattern"))
            print(f"⚠ Skipping '{filename}': does not match expected pattern", file=sys.stderr)
            continue

        # Get well: from JSON or parse from filename
        if use_json_well:
            well = metadata['well']
        else:
            well = parse_well_from_filename(filename)
            if not well:
                missing_metadata.append((filename, "Could not parse well from filename (not in JSON)"))
                print(f"⚠ Skipping '{filename}': Could not parse well from filename", file=sys.stderr)
                continue

        # Get site: from JSON or parse from filename
        if use_json_site:
            site = metadata['site']
        else:
            site = parse_site_from_filename(filename)
            if site is None:
                missing_metadata.append((filename, "Could not parse site from filename (not in JSON)"))
                print(f"⚠ Skipping '{filename}': Could not parse site from filename", file=sys.stderr)
                continue

        # Create grouping key
        key = (plate, well, site)
        if key not in grouped:
            grouped[key] = {'barcoding': {}, 'cellpainting': {}}

        # Store file by type
        if parsed['type'] == 'barcoding':
            # Barcoding file: Cycle{cycle}_{channel}
            cycle = parsed['cycle']
            channel = parsed['channel']
            cycle_channel_key = f"Cycle{cycle}_{channel}"
            grouped[key]['barcoding'][cycle_channel_key] = filename
        else:
            # Cell painting corrected file: Corr{channel}
            channel = parsed['channel']
            corr_key = f"Corr{channel}"
            grouped[key]['cellpainting'][corr_key] = filename

    # Report summary
    if parse_errors:
        print(f"\n⚠ Warning: Failed to parse {len(parse_errors)} file(s)", file=sys.stderr)
    if missing_metadata:
        print(f"⚠ Warning: {len(missing_metadata)} file(s) had missing metadata", file=sys.stderr)

    # Log metadata source
    if use_json_well and use_json_site:
        print(f"✓ Using JSON metadata for plate/well/site: {plate}/{metadata['well']}/Site{metadata['site']}", file=sys.stderr)
    elif use_json_well:
        print(f"✓ Using JSON metadata for plate/well, parsed sites from filenames: {plate}/{metadata['well']}", file=sys.stderr)
    elif use_json_site:
        print(f"✓ Using JSON metadata for plate/site, parsed wells from filenames: {plate}/Site{metadata['site']}", file=sys.stderr)
    else:
        print(f"✓ Using JSON metadata for plate, parsed well/site from filenames: {plate}", file=sys.stderr)

    print(f"✓ Successfully grouped {len(grouped)} unique (plate, well, site) combination(s)", file=sys.stderr)

    return grouped


def generate_csv_rows(grouped: Dict, range_skip: int = 1) -> List[Dict]:
    """
    Generate CSV rows from grouped combined analysis files.

    Each row contains:
    - Metadata_Plate, Metadata_Well, Metadata_Site, Metadata_Well_Value
    - FileName_Cycle##_Channel (for barcoding images)
    - FileName_CorrChannel (for cell painting images)
    """
    if not grouped:
        raise ValueError("No grouped files to generate CSV rows from")

    # Apply site subsampling if needed
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
            row = {
                'Metadata_Plate': plate,
                'Metadata_Well': well,
                'Metadata_Site': site,
                'Metadata_Well_Value': well
            }

            # Add barcoding files (FileName_Cycle##_Channel)
            for cycle_channel_key, filename in sorted(file_data['barcoding'].items()):
                row[f'FileName_{cycle_channel_key}'] = filename

            # Add cell painting files (FileName_CorrChannel)
            for corr_key, filename in sorted(file_data['cellpainting'].items()):
                row[f'FileName_{corr_key}'] = filename

            # Validate we have at least some files
            if not file_data['barcoding'] and not file_data['cellpainting']:
                raise ValueError(f"No image files found for {plate}/{well}/Site{site}")

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


def write_csv(rows: List[Dict], output_file: str):
    """Write rows to CSV with proper column ordering."""
    if not rows:
        raise ValueError("No rows to write - cannot create empty CSV")

    # Metadata columns always come first
    metadata_cols = ['Metadata_Plate', 'Metadata_Site', 'Metadata_Well', 'Metadata_Well_Value']

    # Get all column names
    all_cols = set()
    for row in rows:
        all_cols.update(row.keys())

    # Order: metadata columns first, then sorted FileName columns
    file_cols = sorted([c for c in all_cols if c not in metadata_cols])
    fieldnames = metadata_cols + file_cols

    print(f"✓ Writing CSV with {len(fieldnames)} columns", file=sys.stderr)

    try:
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except IOError as e:
        raise IOError(f"Failed to write CSV to {output_file}: {e}")

    print(f"✓ Successfully generated {output_file} with {len(rows)} rows")


def main():
    parser = argparse.ArgumentParser(
        description='Generate load_data.csv for CellProfiler Combined Analysis',
        epilog='This script processes both cell painting corrected images and barcoding cropped images.'
    )
    parser.add_argument(
        '--images-dir',
        default='./images',
        help='Directory containing input images (default: ./images)'
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
    parser.add_argument(
        '--metadata-json',
        type=str,
        required=True,
        help='JSON file containing metadata (plate, well, site, etc.). '
             'This file is required and provides the plate/well/site values for all images.'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.range_skip < 1:
        parser.error(f"--range-skip must be >= 1, got {args.range_skip}")

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"CellProfiler Combined Analysis CSV Generator", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"Images directory: {args.images_dir}", file=sys.stderr)
    if args.range_skip > 1:
        print(f"Subsampling: every {args.range_skip} sites", file=sys.stderr)
    print(f"Metadata JSON: {args.metadata_json}", file=sys.stderr)
    print(f"Output file: {args.output}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    try:
        # Read metadata from JSON (required)
        print(f"Step 0: Loading metadata from JSON...", file=sys.stderr)
        metadata = read_metadata_json(args.metadata_json)
        print()

        # Collect and group files
        print(f"Step 1/3: Collecting and grouping files...", file=sys.stderr)
        grouped = collect_and_group_files(args.images_dir, metadata)

        # Generate rows
        print(f"\nStep 2/3: Generating CSV rows...", file=sys.stderr)
        rows = generate_csv_rows(grouped, args.range_skip)

        # Write CSV
        print(f"\nStep 3/3: Writing CSV file...", file=sys.stderr)
        write_csv(rows, args.output)

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
    except Exception as e:
        print(f"\n❌ ERROR: Unexpected error occurred", file=sys.stderr)
        print(f"   {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        print(f"\nTraceback:", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
