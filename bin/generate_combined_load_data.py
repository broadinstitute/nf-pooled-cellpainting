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
import os
import re
import sys
from typing import Dict, List, Tuple, Optional


def parse_combined_image(filename: str) -> Optional[Dict]:
    """
    Parse combined analysis image filenames from both cell painting and barcoding.

    Patterns:
    - Cell painting corrected: Plate_{plate}_Well_{well}_Site_{site}_Corr{channel}.tiff
    - Barcoding cropped with cycles: Plate_{plate}_Well_{well}_Site_{site}_Cycle{cycle}_{channel}.tiff
      where cycle is 2-digit zero-padded (01, 02, ..., 10, 11, etc.)
      and channel is one of A, C, G, T, DNA, DAPI

    Returns dict with: plate, well, site, type, and either (channel) or (cycle, channel)
    """
    # Try barcoding cropped pattern with cycles first
    # Note: cycle is 2-digit zero-padded (\d{2}) to handle cycles > 9
    barcode_cycle_pattern = r'Plate_([A-Za-z0-9]+)_Well_([A-Z]\d+)_Site_(\d+)_Cycle(\d{2})_([ACGT]|DNA|DAPI)\.tiff?'
    barcode_cycle_match = re.match(barcode_cycle_pattern, filename)

    if barcode_cycle_match:
        return {
            'plate': barcode_cycle_match.group(1),
            'well': barcode_cycle_match.group(2),
            'site': int(barcode_cycle_match.group(3)),
            'cycle': barcode_cycle_match.group(4),
            'channel': 'DNA' if barcode_cycle_match.group(5) == 'DAPI' else barcode_cycle_match.group(5),
            'type': 'barcoding'
        }

    # Try cell painting corrected pattern
    cp_pattern = r'Plate_([A-Za-z0-9]+)_Well_([A-Z]\d+)_Site_(\d+)_Corr(.+?)\.tiff?'
    cp_match = re.match(cp_pattern, filename)

    if cp_match:
        return {
            'plate': cp_match.group(1),
            'well': cp_match.group(2),
            'site': int(cp_match.group(3)),
            'channel': cp_match.group(4),
            'type': 'cellpainting'
        }

    return None


def infer_plate_well_from_path(file_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Infer plate and well from file path for barcoding files.

    Looks for patterns like 'Plate1/Plate1-A1/' or 'Plate1-A1/' in the path,
    or from the new filename format 'Plate_PlateID_Well_WellID_...'
    Returns: (plate, well) tuple or (None, None) if not found
    """
    # First try to extract from filename using new naming pattern
    filename = os.path.basename(file_path)
    filename_match = re.match(r'Plate_([A-Za-z0-9]+)_Well_([A-Z]\d+)_', filename)
    if filename_match:
        return filename_match.group(1), filename_match.group(2)

    # Try pattern with plate directory: Plate1/Plate1-A1/
    match = re.search(r'(Plate\d+)/(Plate\d+)-([A-Z]\d+)', file_path)
    if match:
        return match.group(2), match.group(3)

    # Try pattern without plate directory: Plate1-A1/
    match = re.search(r'(Plate\d+)-([A-Z]\d+)', file_path)
    if match:
        return match.group(1), match.group(2)

    return None, None


def collect_and_group_files(images_dir: str) -> Dict[Tuple, Dict]:
    """
    Collect and group combined analysis image files.

    Returns:
        Dict mapping (plate, well, site) -> {'barcoding': {...}, 'cellpainting': {...}}
    """
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

    for img_path in image_files:
        filename = os.path.basename(img_path)

        # Parse the filename
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

        # Get plate, well, site from parsed filename
        # With the new naming pattern, all files have plate/well/site in the filename
        try:
            plate = parsed['plate']
            well = parsed['well']
            site = parsed['site']

        except (KeyError, ValueError) as e:
            missing_metadata.append((filename, str(e)))
            print(f"⚠ {e}", file=sys.stderr)
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

    print(f"✓ Successfully grouped {len(grouped)} unique (plate, well, site) combinations", file=sys.stderr)

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
    print(f"Output file: {args.output}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    try:
        # Collect and group files
        print(f"Step 1/3: Collecting and grouping files...", file=sys.stderr)
        grouped = collect_and_group_files(args.images_dir)

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
