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
import json
import os
import re
import sys
from typing import Dict, List, Tuple, Optional


# Pipeline configuration - defines the CSV structure for each pipeline step
PIPELINE_CONFIGS = {
    'illumcalc': {
        'description': 'Illumination calculation - uses original multi-channel images',
        'file_pattern': r'.*\.ome\.tiff?$',
        'metadata_cols': None,  # Dynamic based on has_cycles
        'metadata_cols_base': ['Metadata_Plate', 'Metadata_Well', 'Metadata_Site'],
        'metadata_cols_with_cycles': ['Metadata_Plate', 'Metadata_Well', 'Metadata_Site', 'Metadata_Cycle'],
        'file_cols_template': ['FileName_Orig{channel}', 'Frame_Orig{channel}'],
        'include_illum_files': False,
        'supports_cycles': True,
        'supports_subdirs': False,
        'cycle_aware': False,
        'parse_function': 'parse_original_image'
    },
    'illumapply': {
        'description': 'Illumination correction - uses original images + illumination functions',
        'file_pattern': r'.*\.ome\.tiff?$',
        'metadata_cols': ['Metadata_Plate', 'Metadata_Well', 'Metadata_Site'],
        'file_cols_template': None,  # Dynamic based on cycles
        'include_illum_files': True,
        'supports_cycles': True,
        'supports_subdirs': True,
        'cycle_aware': True,
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
    },
    'combined': {
        'description': 'Combined analysis - uses both cropped cell painting and barcoding images',
        'file_pattern': r'(Plate\d+-[A-Z]\d+_Corr.*_Site_\d+\.tiff?|Plate\d+-[A-Z]\d+_Cycle\d+_[ACGTDAPI]+_Site_\d+\.tiff?)$',
        'metadata_cols': ['Metadata_Plate', 'Metadata_Site', 'Metadata_Well', 'Metadata_Well_Value'],
        'file_cols_template': ['FileName_Cycle{cycle}_{channel}', 'FileName_Corr{channel}'],
        'include_illum_files': False,
        'parse_function': 'parse_combined_image'
    }
}


def parse_original_image(filename: str) -> Optional[Dict]:
    """
    Parse original multi-channel image filename.

    Pattern: WellA1_PointA1_0000_ChannelCHN1,CHN2,CHN3_Seq0000.ome.tiff
    Pattern with cycle: WellA1_PointA1_0000_ChannelCHN1,CHN2,CHN3_Cycle03_Seq0000.ome.tiff

    Returns dict with: plate (if available), well, site, channels (list), frames (dict), cycle (optional)
    """
    # Try pattern with cycle first
    pattern_with_cycle = r'Well([A-Z]\d+)_Point[A-Z]\d+_(\d+)_Channel([^_]+)_Cycle(\d+)_Seq\d+\.ome\.tiff?'
    match = re.search(pattern_with_cycle, filename)

    if match:
        well = match.group(1)
        site = int(match.group(2))
        channels_str = match.group(3)
        cycle = int(match.group(4))

        # Parse channels - could be comma-separated
        channels = [ch.strip() for ch in channels_str.split(',')]

        # Build frame mapping - each channel gets its sequential frame number
        frames = {ch: idx for idx, ch in enumerate(channels)}

        return {
            'well': well,
            'site': site,
            'channels': channels,
            'frames': frames,
            'cycle': cycle
        }

    # Try pattern without cycle
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


def parse_combined_image(filename: str) -> Optional[Dict]:
    """
    Parse combined analysis image filenames from both cell painting and barcoding.

    Patterns:
    - Cell painting corrected: Plate{plate}-{well}_Corr{channel}_Site_{site}.tiff
    - Barcoding cropped: Plate{plate}-{well}_Cycle{cycle}_{channel}_Site_{site}.tiff
      where channel is one of A, C, G, T, DNA

    Returns dict with: plate, well, site, and either (channel) or (cycle, channel)
    """
    # Try barcoding cropped pattern first (Plate{plate}-{well}_Cycle{cycle}_{channel}_Site_{site}.tiff)
    barcode_pattern = r'(Plate\d+)-([A-Z]\d+)_Cycle(\d+)_([ACGT]|DNA|DAPI)_Site_(\d+)\.tiff?'
    barcode_match = re.match(barcode_pattern, filename)

    if barcode_match:
        return {
            'plate': barcode_match.group(1),
            'well': barcode_match.group(2),
            'cycle': barcode_match.group(3),
            'channel': 'DNA' if barcode_match.group(4) == 'DAPI' else barcode_match.group(4),  # Normalize DAPI to DNA
            'site': int(barcode_match.group(5)),
            'type': 'barcoding'
        }

    # Try cell painting corrected pattern (Plate{plate}-{well}_Corr{channel}_Site_{site}.tiff)
    cp_pattern = r'(Plate\d+)-([A-Z]\d+)_Corr(.+?)_Site_(\d+)\.tiff?'
    cp_match = re.match(cp_pattern, filename)

    if cp_match:
        return {
            'plate': cp_match.group(1),
            'well': cp_match.group(2),
            'channel': cp_match.group(3),
            'site': int(cp_match.group(4)),
            'type': 'cellpainting'
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


def infer_plate_well_from_path(file_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Try to infer plate and well from file path for combined analysis.
    Looks for patterns like 'Plate1/Plate1-A1/' or 'Plate1-A1/' in the path.

    Returns: (plate, well) tuple or (None, None) if not found
    """
    # Try pattern with plate directory: Plate1/Plate1-A1/
    match = re.search(r'(Plate\d+)/(Plate\d+)-([A-Z]\d+)', file_path)
    if match:
        return match.group(2), match.group(3)

    # Try pattern without plate directory: Plate1-A1/
    match = re.search(r'(Plate\d+)-([A-Z]\d+)', file_path)
    if match:
        return match.group(1), match.group(2)

    return None, None


def assign_subdirectories(image_list: List[str]) -> Dict[str, str]:
    """
    Assign subdirectory names to unique images for staging.

    Args:
        image_list: List of image filenames

    Returns:
        Dict mapping filename -> subdirectory (e.g., "image.tif" -> "img1")
    """
    unique_images = sorted(set(image_list))
    return {
        img: f"img{idx + 1}"
        for idx, img in enumerate(unique_images)
    }


def load_metadata_json(metadata_json_path: Optional[str]) -> Dict:
    """
    Load metadata JSON file containing additional metadata like original_channels.

    Args:
        metadata_json_path: Path to metadata JSON file

    Returns:
        Dict mapping filename -> metadata dict
    """
    if not metadata_json_path or not os.path.exists(metadata_json_path):
        return {}

    try:
        with open(metadata_json_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Warning: Could not load metadata JSON from {metadata_json_path}: {e}", file=sys.stderr)
        return {}


def match_illumination_files_cycle_aware(
    illum_dir: str,
    plates: List[str],
    channels: List[str],
    has_cycles: bool,
    cycles: Optional[List[str]] = None
) -> Dict:
    """
    Match illumination files with cycle awareness.

    For cycle-based data: Matches pattern Plate1_Cycle01_IllumChannel.npy
    For non-cycle data: Matches pattern Plate1_IllumChannel.npy

    Args:
        illum_dir: Directory containing illumination files
        plates: List of plate names to match
        channels: List of channel names to match
        has_cycles: Whether data has cycles
        cycles: List of cycle numbers (e.g., ['01', '02', '03'])

    Returns:
        Dict structure:
        - For cycles: {plate: {cycle: {channel: filename}}}
        - For non-cycles: {plate: {channel: filename}}
    """
    illum_pattern = os.path.join(illum_dir, "*.npy")
    illum_files = glob.glob(illum_pattern)

    illum_map = {}

    for illum_path in illum_files:
        filename = os.path.basename(illum_path)

        if has_cycles and cycles:
            # Pattern: Plate1_Cycle01_IllumChannel.npy
            match = re.match(r'(.+?)_Cycle(\d+)_Illum(.+?)\.npy', filename)
            if match:
                plate = match.group(1)
                cycle = match.group(2)
                channel = match.group(3)

                if plate in plates and channel in channels:
                    if plate not in illum_map:
                        illum_map[plate] = {}
                    if cycle not in illum_map[plate]:
                        illum_map[plate][cycle] = {}
                    illum_map[plate][cycle][channel] = filename
        else:
            # Pattern: Plate1_IllumChannel.npy
            match = re.match(r'(.+?)_Illum(.+?)\.npy', filename)
            if match:
                plate = match.group(1)
                channel = match.group(2)

                if plate in plates and channel in channels:
                    if plate not in illum_map:
                        illum_map[plate] = {}
                    illum_map[plate][channel] = filename

    return illum_map


def calculate_frame_with_original_channels(
    channel: str,
    current_channels: str,
    original_channels: Optional[str] = None
) -> int:
    """
    Calculate frame number for a channel, considering original_channels metadata.

    Args:
        channel: The channel name to find frame for
        current_channels: Comma-separated string of current channels in image
        original_channels: Optional comma-separated string of original channels before splitting

    Returns:
        Frame number (0-indexed)
    """
    # Multi-channel image: find position in current channels
    if ',' in current_channels:
        channels_list = [ch.strip() for ch in current_channels.split(',')]
        try:
            return channels_list.index(channel)
        except ValueError:
            return 0

    # Single-channel split from multi-channel: use original_channels
    if original_channels and ',' in original_channels:
        orig_channels_list = [ch.strip() for ch in original_channels.split(',')]
        try:
            return orig_channels_list.index(current_channels)
        except ValueError:
            return 0

    # True single-channel image
    return 0


def collect_and_group_files(
    images_dir: str,
    pipeline_type: str,
    illum_dir: Optional[str] = None,
    metadata_plate: Optional[str] = None,
    metadata_cycle: Optional[int] = None,
    metadata_cycles: Optional[List[int]] = None
) -> Dict[Tuple, Dict]:
    """
    Collect and group files based on pipeline configuration.

    Args:
        images_dir: Directory containing images
        pipeline_type: Type of pipeline
        illum_dir: Directory containing illumination files
        metadata_plate: Plate name from metadata (source of truth)
        metadata_cycle: Cycle number from metadata (for single-cycle matching)
        metadata_cycles: List of cycle numbers for multi-cycle processing

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
        # Calculate relative path from images_dir to preserve subdirectory structure
        rel_path = os.path.relpath(img_path, images_dir)

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
            # For combined analysis barcoding files, plate/well are not in filename
            if pipeline_type == 'combined' and parsed.get('type') == 'barcoding':
                inferred_plate, inferred_well = infer_plate_well_from_path(img_path)
                if not inferred_plate or not inferred_well:
                    raise ValueError(f"Could not infer plate/well from path: {img_path}")
                plate = inferred_plate
                well = inferred_well
                site = parsed['site']
            else:
                # Use metadata_plate if provided (source of truth), otherwise parse from filename/path
                plate = metadata_plate if metadata_plate else parsed.get('plate', infer_plate_from_path(img_path))
                well = parsed['well']
                site = parsed['site']
        except KeyError as e:
            missing_metadata.append((filename, str(e)))
            print(f"⚠ Missing required metadata in '{filename}': {e}", file=sys.stderr)
            continue
        except ValueError as e:
            missing_metadata.append((filename, str(e)))
            print(f"⚠ {e}", file=sys.stderr)
            continue

        key = (plate, well, site)

        if key not in grouped:
            grouped[key] = {'images': {}, 'illum': {}, 'cycles': set()}

        # Store files
        try:
            if 'channels' in parsed:
                # Multi-channel image
                if 'cycle' in parsed:
                    # Cycle detected in filename - store per cycle
                    cycle_num = parsed['cycle']
                    grouped[key]['cycles'].add(cycle_num)
                    if '_files_by_cycle' not in grouped[key]['images']:
                        grouped[key]['images']['_files_by_cycle'] = {}
                    grouped[key]['images']['_files_by_cycle'][cycle_num] = {
                        'file': rel_path,
                        'parsed': parsed
                    }
                elif metadata_cycles:
                    # Multi-cycle mode but no cycle in filename - store separately for post-processing
                    grouped[key]['images'][rel_path] = rel_path
                else:
                    # Single-cycle multi-channel image
                    grouped[key]['images']['_file'] = rel_path
                    grouped[key]['images']['_parsed'] = parsed
            elif pipeline_type == 'combined':
                # Combined analysis - store both cell painting and barcoding files
                if parsed.get('type') == 'barcoding':
                    # Barcoding file: Cycle{cycle}_{channel}
                    cycle = parsed['cycle']
                    channel = parsed['channel']
                    cycle_channel_key = f"Cycle{cycle}_{channel}"
                    grouped[key]['images'][cycle_channel_key] = rel_path
                elif parsed.get('type') == 'cellpainting':
                    # Cell painting corrected file: Corr{channel}
                    channel = parsed['channel']
                    corr_key = f"Corr{channel}"
                    grouped[key]['images'][corr_key] = rel_path
            elif 'cycle' in parsed:
                # Cycle-based image (for preprocess pipeline)
                cycle = parsed['cycle']
                channel = parsed['channel']
                cycle_channel_key = f"Cycle{cycle}_{channel}"
                grouped[key]['images'][cycle_channel_key] = rel_path
            else:
                # Single-channel image
                channel = parsed['channel']
                grouped[key]['images'][channel] = rel_path
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

    # Post-process for multi-cycle: assign images to cycles by sorted order
    if metadata_cycles:
        print(f"✓ Processing multi-cycle with cycles: {metadata_cycles}", file=sys.stderr)
        for key in list(grouped.keys()):
            # Skip if already has cycle info
            if '_files_by_cycle' in grouped[key]['images']:
                continue

            # Collect all stored images
            if '_file' in grouped[key]['images']:
                # Single file entry - shouldn't happen in multi-cycle
                continue

            # Get all non-underscore keys (image paths)
            img_paths = [(k, v) for k, v in grouped[key]['images'].items() if not k.startswith('_')]

            if not img_paths:
                continue

            # Sort and assign to cycles by order
            sorted_paths = sorted(img_paths, key=lambda x: x[1])

            if len(sorted_paths) != len(metadata_cycles):
                print(f"⚠ Expected {len(metadata_cycles)} images for {key}, found {len(sorted_paths)}", file=sys.stderr)
                continue

            # Clear and recreate as _files_by_cycle
            for k, _ in img_paths:
                del grouped[key]['images'][k]

            grouped[key]['images']['_files_by_cycle'] = {}
            grouped[key]['cycles'] = set(metadata_cycles)

            for idx, cycle_num in enumerate(sorted(metadata_cycles)):
                img_path = sorted_paths[idx][1]
                filename = os.path.basename(img_path)
                parsed = parse_func(filename)

                if parsed and 'channels' in parsed:
                    grouped[key]['images']['_files_by_cycle'][cycle_num] = {
                        'file': img_path,
                        'parsed': parsed
                    }

        print(f"✓ Assigned images to {len(metadata_cycles)} cycles", file=sys.stderr)

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

            # Try cycle-based pattern first: Plate1_Cycle01_IllumChannelName.npy
            cycle_match = re.match(r'(.+?)_Cycle(\d+)_Illum(.+?)\.npy', filename)
            if cycle_match:
                plate = cycle_match.group(1)
                file_cycle = int(cycle_match.group(2))
                channel = cycle_match.group(3)

                # If metadata_cycle is provided, only match that specific cycle
                # If not provided, match all cycles (store by cycle number)
                if metadata_cycle is not None and file_cycle != metadata_cycle:
                    continue

                # Add to all entries for this plate
                matched_this_file = False
                for (p, w, s) in grouped.keys():
                    if p == plate:
                        # Store illum files by cycle if we have multiple cycles
                        if '_by_cycle' not in grouped[(p, w, s)]['illum']:
                            grouped[(p, w, s)]['illum']['_by_cycle'] = {}
                        if file_cycle not in grouped[(p, w, s)]['illum']['_by_cycle']:
                            grouped[(p, w, s)]['illum']['_by_cycle'][file_cycle] = {}
                        grouped[(p, w, s)]['illum']['_by_cycle'][file_cycle][channel] = filename
                        matched_this_file = True

                if matched_this_file:
                    illum_matched += 1
            else:
                # Try non-cycle pattern: Plate1_IllumChannelName.npy
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
    range_skip: int = 1,
    metadata_channels: Optional[List[str]] = None,
    has_cycles: bool = False,
    metadata_cycle: Optional[int] = None,
    metadata_plate: Optional[str] = None
) -> List[Dict]:
    """
    Generate CSV rows from grouped file data.

    Args:
        grouped: Grouped file data
        pipeline_type: Type of pipeline
        range_skip: Subsampling interval
        metadata_channels: Channel names from metadata (source of truth for headers)
        has_cycles: Whether the data contains cycle information
        metadata_cycle: Cycle number from metadata (source of truth)
        metadata_plate: Plate name from metadata (source of truth)
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
            # Determine which metadata columns to use
            if has_cycles and 'metadata_cols_with_cycles' in config:
                metadata_cols = config['metadata_cols_with_cycles']
            elif 'metadata_cols' in config and config['metadata_cols']:
                metadata_cols = config['metadata_cols']
            elif 'metadata_cols_base' in config:
                metadata_cols = config['metadata_cols_base']
            else:
                metadata_cols = []

            if 'Metadata_Plate' in metadata_cols:
                # Use metadata_plate if provided (source of truth), otherwise use parsed plate
                row['Metadata_Plate'] = metadata_plate if metadata_plate else plate
            if 'Metadata_Well' in metadata_cols:
                row['Metadata_Well'] = well
            if 'Metadata_Site' in metadata_cols:
                row['Metadata_Site'] = site
            if 'Metadata_Well_Value' in metadata_cols:
                row['Metadata_Well_Value'] = well
            if 'Metadata_Cycle' in metadata_cols:
                # Use metadata_cycle if provided (source of truth), otherwise try from file_data
                if metadata_cycle is not None:
                    row['Metadata_Cycle'] = metadata_cycle
                elif 'cycle' in file_data:
                    row['Metadata_Cycle'] = file_data['cycle']

            # Handle multi-channel files
            if '_files_by_cycle' in file_data['images']:
                # Multi-cycle multi-channel images - generate columns for each cycle
                files_by_cycle = file_data['images']['_files_by_cycle']
                illum_by_cycle = file_data['illum'].get('_by_cycle', {})

                # Sort cycles to ensure consistent column order
                for cycle_num in sorted(files_by_cycle.keys()):
                    cycle_info = files_by_cycle[cycle_num]
                    parsed = cycle_info['parsed']
                    filename = cycle_info['file']

                    if 'channels' not in parsed or 'frames' not in parsed:
                        raise ValueError(f"Missing channels or frames data for {filename}")

                    # Use metadata channels if provided, otherwise use parsed channels
                    channels_to_use = metadata_channels if metadata_channels else parsed['channels']

                    cycle_str = f"{cycle_num:02d}"

                    # Add FileName and Frame for each channel in this cycle
                    for frame_idx, channel in enumerate(channels_to_use):
                        # For metadata channels, use frame index; for parsed channels, look up frame
                        if metadata_channels:
                            frame = frame_idx
                        else:
                            if channel not in parsed['frames']:
                                raise KeyError(f"Frame information missing for channel '{channel}'")
                            frame = parsed['frames'][channel]

                        row[f'FileName_Cycle{cycle_str}_Orig{channel}'] = filename
                        row[f'Frame_Cycle{cycle_str}_Orig{channel}'] = frame

                        # Add illumination file if available for this cycle
                        if cycle_num in illum_by_cycle and channel in illum_by_cycle[cycle_num]:
                            row[f'FileName_Cycle{cycle_str}_Illum{channel}'] = illum_by_cycle[cycle_num][channel]

                    # Validate we have all required illumination files for this cycle
                    if config['include_illum_files']:
                        if cycle_num not in illum_by_cycle:
                            print(
                                f"⚠ Missing illumination files for cycle {cycle_num} "
                                f"in {plate}/{well}/Site{site}",
                                file=sys.stderr
                            )
                        else:
                            missing_illum = [ch for ch in channels_to_use if ch not in illum_by_cycle[cycle_num]]
                            if missing_illum:
                                print(
                                    f"⚠ Missing illumination files for channels {missing_illum} in cycle {cycle_num} "
                                    f"in {plate}/{well}/Site{site}",
                                    file=sys.stderr
                                )

            elif '_file' in file_data['images']:
                # Single non-cycle multi-channel image
                parsed = file_data['images']['_parsed']
                filename = file_data['images']['_file']

                if 'channels' not in parsed or 'frames' not in parsed:
                    raise ValueError(f"Missing channels or frames data for {filename}")

                # Use metadata channels if provided, otherwise use parsed channels
                channels_to_use = metadata_channels if metadata_channels else parsed['channels']

                # Determine if we need cycle-specific column names
                use_cycle_columns = config.get('cycle_aware', False) and metadata_cycle is not None

                # Add FileName and Frame for each channel
                for frame_idx, channel in enumerate(channels_to_use):
                    # For metadata channels, use frame index; for parsed channels, look up frame
                    if metadata_channels:
                        frame = frame_idx
                    else:
                        if channel not in parsed['frames']:
                            raise KeyError(f"Frame information missing for channel '{channel}'")
                        frame = parsed['frames'][channel]

                    # Generate column names with or without cycle prefix
                    if use_cycle_columns:
                        cycle_str = f"{metadata_cycle:02d}"
                        row[f'FileName_Cycle{cycle_str}_Orig{channel}'] = filename
                        row[f'Frame_Cycle{cycle_str}_Orig{channel}'] = frame
                    else:
                        row[f'FileName_Orig{channel}'] = filename
                        row[f'Frame_Orig{channel}'] = frame

                    # Add illumination file if available
                    # Match illumination files by channel name (they should use metadata channel names)
                    if channel in file_data['illum']:
                        if use_cycle_columns:
                            row[f'FileName_Cycle{cycle_str}_Illum{channel}'] = file_data['illum'][channel]
                        else:
                            row[f'FileName_Illum{channel}'] = file_data['illum'][channel]

                # Validate we have all required illumination files
                if config['include_illum_files']:
                    missing_illum = [ch for ch in channels_to_use if ch not in file_data['illum']]
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

                # For combined analysis, we need to handle both cycle-based and corrected files
                if pipeline_type == 'combined':
                    # Add all files with their appropriate column names
                    for key, filename in sorted(file_data['images'].items()):
                        # Keys are like "Cycle01_A", "Cycle01_DNA", "CorrDNA", "CorrCHN2"
                        row[f'FileName_{key}'] = filename
                else:
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
    parser.add_argument(
        '--use-subdirs',
        action='store_true',
        help='Use subdirectories (img1/, img2/, etc.) for staging images in CSV'
    )
    parser.add_argument(
        '--metadata-json',
        help='Path to JSON file with additional metadata (e.g., original_channels)'
    )
    parser.add_argument(
        '--output-file-list',
        help='Path to output JSON file listing all required files for staging'
    )
    parser.add_argument(
        '--group-by',
        help='Comma-separated list of metadata keys to group by (e.g., batch,plate,well)'
    )
    parser.add_argument(
        '--has-cycles',
        action='store_true',
        help='Data contains cycle information (for barcoding workflows)'
    )
    parser.add_argument(
        '--channels',
        help='Comma-separated list of channel names from metadata (source of truth for column headers)'
    )
    parser.add_argument(
        '--cycle',
        type=int,
        help='Cycle number from metadata (source of truth for Metadata_Cycle) - for single-cycle processing'
    )
    parser.add_argument(
        '--cycles',
        help='Comma-separated list of cycle numbers for multi-cycle processing (e.g., "1,2,3")'
    )
    parser.add_argument(
        '--plate',
        help='Plate name from metadata (source of truth for Metadata_Plate)'
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
        # Load metadata JSON if provided
        metadata_map = load_metadata_json(args.metadata_json)
        if args.metadata_json and metadata_map:
            print(f"✓ Loaded metadata for {len(metadata_map)} files from {args.metadata_json}", file=sys.stderr)

        # Parse metadata channels if provided
        metadata_channels = None
        if args.channels:
            metadata_channels = [ch.strip() for ch in args.channels.split(',')]
            print(f"✓ Using metadata channels: {metadata_channels}", file=sys.stderr)

        # Use metadata plate if provided
        if args.plate:
            print(f"✓ Using metadata plate: {args.plate}", file=sys.stderr)

        # Parse cycles if provided (for multi-cycle processing)
        metadata_cycles = None
        if args.cycles:
            metadata_cycles = [int(c.strip()) for c in args.cycles.split(',')]
            print(f"✓ Using metadata cycles: {metadata_cycles}", file=sys.stderr)
        elif args.cycle:
            print(f"✓ Using metadata cycle: {args.cycle}", file=sys.stderr)

        # Collect and group files
        print(f"Step 1/4: Collecting and grouping files...", file=sys.stderr)
        grouped = collect_and_group_files(
            args.images_dir,
            args.pipeline_type,
            args.illum_dir,
            args.plate,
            args.cycle,
            metadata_cycles
        )

        # Generate rows
        print(f"\nStep 2/4: Generating CSV rows...", file=sys.stderr)
        rows = generate_csv_rows(grouped, args.pipeline_type, args.range_skip, metadata_channels, args.has_cycles, args.cycle, args.plate)

        # Apply subdirectory staging if requested
        subdir_map = {}
        all_images = set()

        # Collect all image filenames from rows (needed for file list output)
        for row in rows:
            for key, value in row.items():
                if key.startswith('FileName_') and value:
                    # Remove quotes if present
                    filename = value.strip('"')
                    if filename and not filename.endswith('.npy'):
                        all_images.add(filename)

        if args.use_subdirs and config.get('supports_subdirs', False):
            print(f"\nStep 3/4: Applying subdirectory staging...", file=sys.stderr)
            subdir_map = assign_subdirectories(list(all_images))
            print(f"✓ Assigned {len(subdir_map)} images to subdirectories", file=sys.stderr)

            # Update filenames in rows with subdirectory prefix
            for row in rows:
                for key in list(row.keys()):
                    if key.startswith('FileName_') and row[key]:
                        filename = row[key].strip('"')
                        if filename in subdir_map:
                            row[key] = f'"{subdir_map[filename]}/{filename}"'
        else:
            print(f"\nStep 3/4: Skipping subdirectory staging (not enabled or not supported)", file=sys.stderr)

        # Write CSV
        print(f"\nStep 4/4: Writing output files...", file=sys.stderr)
        # Determine correct metadata columns
        if args.has_cycles and 'metadata_cols_with_cycles' in config:
            metadata_cols_to_use = config['metadata_cols_with_cycles']
        elif 'metadata_cols' in config and config['metadata_cols']:
            metadata_cols_to_use = config['metadata_cols']
        elif 'metadata_cols_base' in config:
            metadata_cols_to_use = config['metadata_cols_base']
        else:
            metadata_cols_to_use = []
        write_csv(rows, args.output, metadata_cols_to_use)

        # Write file list if requested
        if args.output_file_list:
            file_list_data = {
                'images': sorted(all_images) if args.use_subdirs else [],
                'subdirs': subdir_map if args.use_subdirs else {},
                'illumination': []
            }

            # Collect illumination files from grouped data
            for file_data in grouped.values():
                if 'illum' in file_data and file_data['illum']:
                    file_list_data['illumination'].extend(file_data['illum'].values())

            file_list_data['illumination'] = sorted(set(file_list_data['illumination']))

            with open(args.output_file_list, 'w') as f:
                json.dump(file_list_data, f, indent=2)

            print(f"✓ Wrote file list to {args.output_file_list}", file=sys.stderr)

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
