#!/usr/bin/env python3
"""
General-purpose load_data.csv generator for CellProfiler pipelines.

This script generates load_data.csv files for different CellProfiler pipeline steps.
It automatically detects the pipeline type based on input files and generates the
appropriate CSV structure.

Metadata columns are created based on fields present in the JSON metadata file:

Mode 1: image_metadata array (one CSV row per array entry)
- JSON has 'image_metadata' array → CSV has Metadata_Plate, Metadata_Well, Metadata_Site
- Well/site values come from array entries, not parsed from filenames
- Files are matched to array entries by parsing well/site from filenames
- Example: {"plate": "P1", "image_metadata": [{"well": "A1", "site": 0}, ...]}

Mode 2: Single well/site (one CSV row)
- JSON has 'plate', 'well', 'site' → CSV has all three columns
- Example: {"plate": "P1", "well": "A1", "site": 0}

Mode 3: Plate-level only (well/site parsed from filenames)
- JSON has 'plate' only → CSV has Metadata_Plate only
- Well/site parsed from filenames for grouping but not in CSV columns
- Example: {"plate": "P1"}

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
        'file_pattern': r'(Plate_.*_Well_.*_Site_.*_Corr.*\.tiff?|Plate_.*_Well_.*_Site_.*_Cycle\d{2}_\w+\.tiff?|Plate\d+-[A-Z]\d+_Corr.*_Site_\d+\.tiff?|Plate\d+-[A-Z]\d+_Cycle\d+_\w+_Site_\d+\.tiff?)$',
        'metadata_cols': ['Metadata_Plate', 'Metadata_Site', 'Metadata_Well', 'Metadata_Well_Value'],
        'file_cols_template': ['FileName_Cycle{cycle}_{channel}', 'FileName_Corr{channel}'],
        'include_illum_files': False,
        'parse_function': 'parse_combined_image'
    }
}


def parse_original_image(filename: str) -> Optional[Dict]:
    """
    Parse original multi-channel image filename to extract channel information.

    Pattern: WellA1_PointA1_0000_ChannelCHN1,CHN2,CHN3_Seq0000.ome.tiff
    Pattern with cycle: WellA1_PointA1_0000_ChannelCHN1,CHN2,CHN3_Cycle03_Seq0000.ome.tiff

    Returns dict with: channels (list), frames (dict)
    Note: plate, well, site, cycle must come from JSON metadata
    """
    # Try pattern with cycle first (to detect cycle presence, but don't extract it)
    pattern_with_cycle = r'Well[A-Z]\d+_Point[A-Z]\d+_\d+_Channel([^_]+)_Cycle\d+_Seq\d+\.ome\.tiff?'
    match = re.search(pattern_with_cycle, filename)

    if match:
        channels_str = match.group(1)
        # Parse channels - could be comma-separated
        channels = [ch.strip() for ch in channels_str.split(',')]
        # Build frame mapping - each channel gets its sequential frame number
        frames = {ch: idx for idx, ch in enumerate(channels)}
        return {
            'channels': channels,
            'frames': frames
        }

    # Try pattern without cycle
    pattern = r'Well[A-Z]\d+_Point[A-Z]\d+_\d+_Channel([^_]+)_Seq\d+\.ome\.tiff?'
    match = re.search(pattern, filename)

    if not match:
        return None

    channels_str = match.group(1)
    # Parse channels - could be comma-separated
    channels = [ch.strip() for ch in channels_str.split(',')]
    # Build frame mapping - each channel gets its sequential frame number
    frames = {ch: idx for idx, ch in enumerate(channels)}

    return {
        'channels': channels,
        'frames': frames
    }


def parse_corrected_image(filename: str) -> Optional[Dict]:
    """
    Parse corrected image filename to extract channel information.

    Pattern: Plate_{plate}_Well_{well}_Site_{site}_Corr{channel}.tiff

    Returns dict with: channel
    Note: plate, well, site must come from JSON metadata
    """
    pattern = r'Plate_.+?_Well_.+?_Site_\d+_Corr(.+?)\.tiff?'
    match = re.match(pattern, filename)

    if match:
        return {
            'channel': match.group(1)
        }
    return None


def parse_preprocess_image(filename: str) -> Optional[Dict]:
    """
    Parse barcoding preprocess image filename to extract cycle and channel information.

    Pattern: Plate_{plate}_Well_{well}_Site_{site}_Cycle{cycle}_{channel}.tiff
    where channel is one of A, C, G, T (or DNA/DAPI for Cycle01)

    Returns dict with: cycle, channel
    Note: plate, well, site must come from JSON metadata
    """
    # Try standard pattern first (for A, C, G, T)
    pattern = r'Plate_.+?_Well_.+?_Site_\d+_Cycle(\d+)_([ACGT])\.tiff?'
    match = re.match(pattern, filename)

    if match:
        return {
            'cycle': match.group(1),  # Keep as string (e.g., "01", "02", "03")
            'channel': match.group(2)
        }

    # Try DNA pattern for Cycle01 (accepts both DNA and DAPI, normalizes to DNA)
    dna_pattern = r'Plate_.+?_Well_.+?_Site_\d+_Cycle(\d+)_(DNA|DAPI)\.tiff?'
    dna_match = re.match(dna_pattern, filename)

    if dna_match:
        return {
            'cycle': dna_match.group(1),
            'channel': 'DNA'  # Normalize DAPI to DNA for consistency
        }

    return None


def parse_combined_image(filename: str) -> Optional[Dict]:
    """
    Parse combined analysis image filenames to extract cycle and channel information.

    Patterns (new format from standardized pipeline):
    - Barcoding cropped with cycles: Plate_PlateID_Well_WellID_Site_#_Cycle##_Channel.tiff
      where cycle is 2-digit zero-padded (01, 02, ..., 10, 11, etc.)
      and channel is one of A, C, G, T, DNA, DAPI
    - Cell painting corrected: Plate_PlateID_Well_WellID_Site_#_CorrChannel.tiff

    Also supports legacy patterns for backward compatibility:
    - Barcoding: Plate{plate}-{well}_Cycle{cycle}_{channel}_Site_{site}.tiff
    - Cell painting: Plate{plate}-{well}_Corr{channel}_Site_{site}.tiff

    Returns dict with: either (channel) or (cycle, channel), plus type
    Note: plate, well, site can come from JSON metadata or be parsed from filename
    """
    # Try new barcoding pattern first (Plate_PlateID_Well_WellID_Site_#_Cycle##_Channel.tiff)
    # Note: cycle is 2-digit zero-padded (\d{2}) to handle cycles > 9
    barcode_new_pattern = r'Plate_[A-Za-z0-9]+_Well_[A-Z]\d+_Site_\d+_Cycle(\d{2})_([ACGT]|DNA|DAPI)\.tiff?'
    barcode_new_match = re.match(barcode_new_pattern, filename)

    if barcode_new_match:
        return {
            'cycle': barcode_new_match.group(1),
            'channel': 'DNA' if barcode_new_match.group(2) == 'DAPI' else barcode_new_match.group(2),
            'type': 'barcoding'
        }

    # Try new cell painting pattern (Plate_PlateID_Well_WellID_Site_#_CorrChannel.tiff)
    cp_new_pattern = r'Plate_[A-Za-z0-9]+_Well_[A-Z]\d+_Site_\d+_Corr(.+?)\.tiff?'
    cp_new_match = re.match(cp_new_pattern, filename)

    if cp_new_match:
        return {
            'channel': cp_new_match.group(1),
            'type': 'cellpainting'
        }

    # Legacy pattern support: barcoding (Plate{plate}-{well}_Cycle{cycle}_{channel}_Site_{site}.tiff)
    barcode_legacy_pattern = r'Plate\d+-[A-Z]\d+_Cycle(\d+)_([ACGT]|DNA|DAPI)_Site_\d+\.tiff?'
    barcode_legacy_match = re.match(barcode_legacy_pattern, filename)

    if barcode_legacy_match:
        return {
            'cycle': barcode_legacy_match.group(1),
            'channel': 'DNA' if barcode_legacy_match.group(2) == 'DAPI' else barcode_legacy_match.group(2),
            'type': 'barcoding'
        }

    # Legacy pattern support: cell painting (Plate{plate}-{well}_Corr{channel}_Site_{site}.tiff)
    cp_legacy_pattern = r'Plate\d+-[A-Z]\d+_Corr(.+?)_Site_\d+\.tiff?'
    cp_legacy_match = re.match(cp_legacy_pattern, filename)

    if cp_legacy_match:
        return {
            'channel': cp_legacy_match.group(1),
            'type': 'cellpainting'
        }

    return None


def parse_well_from_filename(filename: str) -> Optional[str]:
    """
    Parse well identifier from filename as fallback when not in JSON metadata.

    Patterns:
    - WellA1_Point... (original images)
    - Well_A1_... (corrected/preprocess images)
    - Plate-A1_... (combined images)

    Returns:
        Well identifier (e.g., "A1") or None if not found
    """
    # Try original image pattern: WellA1_Point...
    match = re.search(r'Well([A-Z]\d+)_Point', filename)
    if match:
        return match.group(1)

    # Try corrected/preprocess pattern: Well_A1_...
    match = re.search(r'Well_([A-Z]\d+)_', filename)
    if match:
        return match.group(1)

    # Try combined pattern: Plate-A1_...
    match = re.search(r'Plate\d+-([A-Z]\d+)_', filename)
    if match:
        return match.group(1)

    return None


def parse_site_from_filename(filename: str) -> Optional[int]:
    """
    Parse site number from filename as fallback when not in JSON metadata.

    Patterns:
    - PointA1_... (original images - Point is equivalent to Site)
    - Site_1_... (corrected/preprocess images)
    - _Site_1.tif (combined images)

    Returns:
        Site number (int) or None if not found
    """
    # Try original image pattern: PointA1_... (Point is equivalent to Site)
    # Extract numeric part after Point letter prefix
    match = re.search(r'Point[A-Z](\d+)_', filename)
    if match:
        return int(match.group(1))

    # Try corrected/preprocess pattern: Site_1_...
    match = re.search(r'Site_(\d+)_', filename)
    if match:
        return int(match.group(1))

    # Try combined pattern: _Site_1.tif
    match = re.search(r'_Site_(\d+)\.', filename)
    if match:
        return int(match.group(1))

    return None


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


def load_metadata_json(metadata_json_path: str) -> Dict:
    """
    Load and validate metadata JSON file containing required metadata.

    Args:
        metadata_json_path: Path to metadata JSON file (REQUIRED)

    Returns:
        Dict with keys: plate (required), well, site (optional), cycle, channels, batch, arm (optional)
                       image_metadata (optional) - array of {well, site} dicts for each image

        The presence of 'well' and 'site' keys determines which metadata columns are created:
        - If 'image_metadata' array exists: Always create Metadata_Well and Metadata_Site columns
        - If 'well' is present: Metadata_Well column is created in CSV
        - If 'site' is present: Metadata_Site column is created in CSV
        - If absent: values are parsed from filenames but no metadata column is created

    Raises:
        FileNotFoundError: If metadata file doesn't exist
        ValueError: If required fields are missing

    Example JSON structures:
        With image_metadata array (one row per entry):
        {
            "plate": "Plate1",
            "channels": ["DNA", "Phalloidin", "CHN2"],
            "image_metadata": [
                {"well": "A1", "site": 0},
                {"well": "A1", "site": 1},
                {"well": "A2", "site": 0}
            ]
        }

        Full metadata (single well/site):
        {
            "plate": "Plate1",
            "well": "A1",
            "site": 1,
            "cycle": 1,
            "channels": ["DNA", "Phalloidin", "CHN2"]
        }

        Plate-level only (no well/site columns in CSV):
        {
            "plate": "Plate1",
            "channels": ["DNA", "Phalloidin", "CHN2"]
        }
    """
    if not os.path.exists(metadata_json_path):
        raise FileNotFoundError(f"Metadata JSON file not found: {metadata_json_path}")

    try:
        with open(metadata_json_path, 'r') as f:
            metadata = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in metadata file {metadata_json_path}: {e}")
    except Exception as e:
        raise IOError(f"Error reading metadata file {metadata_json_path}: {e}")

    # Validate required fields - only plate is mandatory
    if 'plate' not in metadata:
        raise ValueError(
            "Metadata JSON is missing required field: 'plate'. "
            "Only 'plate' is mandatory; 'well' and 'site' are optional."
        )

    # Validate and normalize the structure
    result = {}

    # Extract required field
    result['plate'] = str(metadata['plate'])

    # Extract optional well and site fields
    if 'well' in metadata:
        result['well'] = str(metadata['well'])

    if 'site' in metadata:
        result['site'] = int(metadata['site'])

    # Extract optional image_metadata array
    if 'image_metadata' in metadata:
        if not isinstance(metadata['image_metadata'], list):
            raise ValueError("'image_metadata' must be an array")
        result['image_metadata'] = []
        for idx, entry in enumerate(metadata['image_metadata']):
            if not isinstance(entry, dict):
                raise ValueError(f"image_metadata[{idx}] must be an object with 'well' and 'site' fields")
            if 'well' not in entry or 'site' not in entry:
                raise ValueError(f"image_metadata[{idx}] must have 'well' and 'site' fields")
            metadata_entry = {
                'well': str(entry['well']),
                'site': int(entry['site'])
            }
            # Preserve filename if present
            if 'filename' in entry:
                metadata_entry['filename'] = str(entry['filename'])
            # Preserve type if present (for combined analysis: cellpainting, barcoding, etc.)
            if 'type' in entry:
                metadata_entry['type'] = str(entry['type'])
            # Preserve cycle if present (for multi-cycle images)
            if 'cycle' in entry:
                metadata_entry['cycle'] = int(entry['cycle'])
            # Preserve channel if present (for single-channel images like segcheck)
            if 'channel' in entry:
                metadata_entry['channel'] = str(entry['channel'])
            result['image_metadata'].append(metadata_entry)

    # Extract optional fields
    if 'cycle' in metadata and metadata['cycle'] is not None:
        result['cycle'] = int(metadata['cycle'])
    if 'cycles' in metadata and metadata['cycles'] is not None:
        # Handle list of cycles for multi-cycle processing
        if isinstance(metadata['cycles'], list):
            result['cycles'] = [int(c) for c in metadata['cycles']]
        else:
            result['cycles'] = [int(metadata['cycles'])]
    if 'channels' in metadata:
        # Handle both comma-separated string and list
        if isinstance(metadata['channels'], str):
            result['channels'] = [ch.strip() for ch in metadata['channels'].split(',')]
        elif isinstance(metadata['channels'], list):
            result['channels'] = [str(ch) for ch in metadata['channels']]
    if 'batch' in metadata:
        result['batch'] = str(metadata['batch'])
    if 'arm' in metadata:
        result['arm'] = str(metadata['arm'])

    return result


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
    metadata_cycle: Optional[int] = None,
    metadata_cycles: Optional[List[int]] = None,
    metadata_json: Dict = None
) -> Dict[Tuple, Dict]:
    """
    Collect and group files based on pipeline configuration.

    Args:
        images_dir: Directory containing images
        pipeline_type: Type of pipeline
        illum_dir: Directory containing illumination files
        metadata_cycle: Cycle number from metadata (for single-cycle matching)
        metadata_cycles: List of cycle numbers for multi-cycle processing
        metadata_json: Dict from JSON file (REQUIRED - source of plate, well, site, cycle)

    Returns:
        Dict mapping (plate, well, site) -> {'images': {...}, 'illum': {...}}

    Raises:
        ValueError: If metadata_json is missing or lacks required fields
    """
    # Validate metadata JSON is provided
    if not metadata_json:
        raise ValueError(
            "Metadata JSON is required but was not provided. "
            "Use --metadata-json to specify the metadata file."
        )

    # Only plate is required in metadata JSON - well and site can be parsed from filenames
    if 'plate' not in metadata_json:
        raise ValueError(
            "Metadata JSON is missing required field: 'plate'. "
            "Plate must always come from metadata JSON."
        )

    # Check if we have image_metadata array or need to parse well/site from filenames
    use_image_metadata = 'image_metadata' in metadata_json
    use_json_well = 'well' in metadata_json
    use_json_site = 'site' in metadata_json

    if use_image_metadata:
        print(f"✓ Using image_metadata array with {len(metadata_json['image_metadata'])} entries", file=sys.stderr)
    elif use_json_well and use_json_site:
        print("✓ Using well and site from JSON metadata", file=sys.stderr)
    elif use_json_well:
        print("✓ Using well from JSON metadata, will parse site from filenames", file=sys.stderr)
    elif use_json_site:
        print("✓ Using site from JSON metadata, will parse well from filenames", file=sys.stderr)
    else:
        print("✓ Will parse both well and site from filenames (not in JSON metadata)", file=sys.stderr)

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

    # If using image_metadata array, match files by FILENAME
    if use_image_metadata:
        # Match files to metadata entries by filename - NO parsing needed!
        # All metadata comes from JSON
        plate = metadata_json['plate']

        # Build a map of filename -> file path
        file_map = {}
        for img_path in image_files:
            filename = os.path.basename(img_path)
            file_map[filename] = img_path

        # Iterate through metadata entries and find matching files
        for entry in metadata_json['image_metadata']:
            well = entry['well']
            site = entry['site']
            expected_filename = entry.get('filename')
            entry_cycle = entry.get('cycle')  # Get cycle from entry if present
            entry_channel = entry.get('channel')  # Get channel from entry if present (for single-channel files)
            entry_type = entry.get('type', '')  # Get type from entry if present (cellpainting, barcoding, etc.)

            if not expected_filename:
                print(f"⚠ Warning: No filename in metadata entry for well={well}, site={site}", file=sys.stderr)
                continue

            if expected_filename not in file_map:
                print(f"⚠ Warning: File '{expected_filename}' from metadata not found in images directory", file=sys.stderr)
                continue

            img_path = file_map[expected_filename]
            rel_path = os.path.relpath(img_path, images_dir)
            key = (plate, well, site)

            # Initialize grouped entry if not exists
            if key not in grouped:
                grouped[key] = {'images': {}, 'illum': {}, 'cycles': set()}

            # Store file based on whether it has cycle/channel information
            # NO PARSING - just use metadata from JSON
            if entry_cycle is not None and entry_channel:
                # Cycle + channel (like preprocess: Cycle01_DNA)
                cycle_channel_key = f"Cycle{entry_cycle:02d}_{entry_channel}"
                grouped[key]['images'][cycle_channel_key] = rel_path
            elif entry_cycle is not None:
                # Multi-cycle only: store per cycle
                cycle_num = entry_cycle
                grouped[key]['cycles'].add(cycle_num)
                if '_files_by_cycle' not in grouped[key]['images']:
                    grouped[key]['images']['_files_by_cycle'] = {}
                # Only store if not already present (same file may be referenced multiple times)
                if cycle_num not in grouped[key]['images']['_files_by_cycle']:
                    grouped[key]['images']['_files_by_cycle'][cycle_num] = {
                        'file': rel_path
                    }
            elif entry_channel:
                # Single-channel file - use appropriate prefix based on type
                if entry_type == 'cellpainting':
                    # Cell painting corrected images: prefix with "Corr"
                    channel_key = f"Corr{entry_channel}"
                else:
                    # Other types (like segcheck): use channel as-is
                    channel_key = entry_channel
                grouped[key]['images'][channel_key] = rel_path
            elif metadata_cycles:
                # Multi-cycle mode from JSON but no cycle in entry - store for post-processing
                grouped[key]['images'][rel_path] = rel_path
            else:
                # Multi-channel single file
                grouped[key]['images']['_file'] = rel_path

        print(f"✓ Created {len(grouped)} entries from image_metadata array", file=sys.stderr)

    else:
        # Original logic: group files based on parsed or JSON metadata
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

            # Extract metadata - plate always from JSON, well/site from JSON or filename
            plate = metadata_json['plate']

            # Get well: from JSON or parse from filename
            if use_json_well:
                well = metadata_json['well']
            else:
                well = parse_well_from_filename(filename)
                if not well:
                    missing_metadata.append((filename, "Could not parse well from filename (not in JSON)"))
                    print(f"⚠ Skipping '{filename}': Could not parse well from filename", file=sys.stderr)
                    continue

            # Get site: from JSON or parse from filename
            if use_json_site:
                site = metadata_json['site']
            else:
                site = parse_site_from_filename(filename)
                if site is None:
                    missing_metadata.append((filename, "Could not parse site from filename (not in JSON)"))
                    print(f"⚠ Skipping '{filename}': Could not parse site from filename", file=sys.stderr)
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
                # No parsing needed - just store the file path
                grouped[key]['images']['_files_by_cycle'][cycle_num] = {
                    'file': img_path
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
    metadata_json: Dict = None
) -> List[Dict]:
    """
    Generate CSV rows from grouped file data.

    Args:
        grouped: Grouped file data
        pipeline_type: Type of pipeline
        range_skip: Subsampling interval
        metadata_channels: Channel names from metadata (for column headers)
        has_cycles: Whether the data contains cycle information
        metadata_cycle: Cycle number from metadata
        metadata_json: Dict from JSON file (REQUIRED - source of all metadata)

    Raises:
        ValueError: If metadata_json is missing or lacks required fields
    """
    # Validate metadata JSON
    if not metadata_json:
        raise ValueError("Metadata JSON is required but was not provided")
    config = PIPELINE_CONFIGS[pipeline_type]

    if not grouped:
        raise ValueError("No grouped files to generate CSV rows from")

    # Determine which metadata fields are present in JSON
    # If image_metadata array exists, always create Metadata_Well and Metadata_Site columns
    use_image_metadata = 'image_metadata' in metadata_json
    has_well = use_image_metadata or 'well' in metadata_json
    has_site = use_image_metadata or 'site' in metadata_json
    has_cycle = 'cycle' in metadata_json or metadata_cycle is not None

    # Report which metadata columns will be created
    metadata_columns = ['Metadata_Plate']
    if has_well:
        metadata_columns.append('Metadata_Well')
    if has_site:
        metadata_columns.append('Metadata_Site')
    if has_cycles and has_cycle:
        metadata_columns.append('Metadata_Cycle')

    if use_image_metadata:
        print(f"✓ Metadata columns from image_metadata array: {', '.join(metadata_columns)}", file=sys.stderr)
    else:
        print(f"✓ Metadata columns from JSON fields: {', '.join(metadata_columns)}", file=sys.stderr)

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
            # Build metadata columns based on what's in JSON
            row = {}

            # Always include Metadata_Plate (required in JSON)
            row['Metadata_Plate'] = plate

            # Conditionally include Metadata_Well if 'well' is in JSON
            if has_well:
                row['Metadata_Well'] = well
                # Some pipelines use Metadata_Well_Value as well
                config_cols = config.get('metadata_cols', []) or config.get('metadata_cols_base', [])
                if 'Metadata_Well_Value' in config_cols:
                    row['Metadata_Well_Value'] = well

            # Conditionally include Metadata_Site if 'site' is in JSON
            if has_site:
                row['Metadata_Site'] = site

            # Conditionally include Metadata_Cycle if 'cycle' is in JSON or provided
            if has_cycles and has_cycle:
                if 'cycle' in metadata_json:
                    row['Metadata_Cycle'] = metadata_json['cycle']
                elif metadata_cycle is not None:
                    row['Metadata_Cycle'] = metadata_cycle
                else:
                    raise ValueError(f"Metadata_Cycle required but not found in metadata JSON or arguments")

            # Handle multi-channel files
            if '_files_by_cycle' in file_data['images']:
                # Multi-cycle multi-channel images - generate columns for each cycle
                files_by_cycle = file_data['images']['_files_by_cycle']
                illum_by_cycle = file_data['illum'].get('_by_cycle', {})

                # Get channels from JSON metadata (required!)
                if metadata_json and 'channels' in metadata_json:
                    channels_to_use = metadata_json['channels']
                elif metadata_channels:
                    channels_to_use = metadata_channels
                else:
                    raise ValueError("Channels must be specified in JSON metadata or CLI args")

                # Sort cycles to ensure consistent column order
                for cycle_num in sorted(files_by_cycle.keys()):
                    cycle_info = files_by_cycle[cycle_num]
                    filename = cycle_info['file']
                    cycle_str = f"{cycle_num:02d}"

                    # Add FileName and Frame for each channel in this cycle
                    # Frame number is just the index in the channels list
                    for frame_idx, channel in enumerate(channels_to_use):
                        row[f'FileName_Cycle{cycle_str}_Orig{channel}'] = filename
                        row[f'Frame_Cycle{cycle_str}_Orig{channel}'] = frame_idx

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
                filename = file_data['images']['_file']

                # Get channels from JSON metadata (required!)
                if metadata_json and 'channels' in metadata_json:
                    channels_to_use = metadata_json['channels']
                elif metadata_channels:
                    channels_to_use = metadata_channels
                else:
                    raise ValueError("Channels must be specified in JSON metadata or CLI args")

                # Determine if we need cycle-specific column names
                use_cycle_columns = config.get('cycle_aware', False) and metadata_cycle is not None

                # Add FileName and Frame for each channel
                # Frame number is just the index in the channels list
                for frame_idx, channel in enumerate(channels_to_use):
                    # Generate column names with or without cycle prefix
                    if use_cycle_columns:
                        cycle_str = f"{metadata_cycle:02d}"
                        row[f'FileName_Cycle{cycle_str}_Orig{channel}'] = filename
                        row[f'Frame_Cycle{cycle_str}_Orig{channel}'] = frame_idx
                    else:
                        row[f'FileName_Orig{channel}'] = filename
                        row[f'Frame_Orig{channel}'] = frame_idx

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


def write_csv(rows: List[Dict], output_file: str, metadata_cols: Optional[List[str]] = None):
    """
    Write rows to CSV with proper column ordering.

    Args:
        rows: List of row dictionaries
        output_file: Path to output CSV file
        metadata_cols: Optional list of expected metadata columns (for validation only)
    """
    if not rows:
        raise ValueError("No rows to write - cannot create empty CSV")

    # Get all column names from actual data
    all_cols = set()
    for row in rows:
        all_cols.update(row.keys())

    # Separate metadata columns (start with Metadata_) from file columns
    actual_metadata_cols = sorted([c for c in all_cols if c.startswith('Metadata_')])
    file_cols = sorted([c for c in all_cols if not c.startswith('Metadata_')])

    # Order: metadata columns first, then sorted FileName/Frame columns
    fieldnames = actual_metadata_cols + file_cols

    # Validation: warn if expected metadata columns are missing
    if metadata_cols:
        missing_meta = [col for col in metadata_cols if col not in all_cols]
        if missing_meta:
            print(
                f"⚠ Warning: Expected metadata columns not found in data: {missing_meta}",
                file=sys.stderr
            )

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
        required=True,
        help='Path to JSON file with metadata (plate, well, site, cycle, channels). REQUIRED - all metadata must be in JSON.'
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
        help='Comma-separated list of channel names (for column headers) - overrides JSON metadata if provided'
    )
    parser.add_argument(
        '--cycle',
        type=int,
        help='Cycle number for single-cycle processing - overrides JSON metadata if provided'
    )
    parser.add_argument(
        '--cycles',
        help='Comma-separated list of cycle numbers for multi-cycle processing (e.g., "1,2,3")'
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
        # Load and validate metadata JSON (REQUIRED)
        metadata_json = load_metadata_json(args.metadata_json)
        print(f"✓ Loaded metadata from {args.metadata_json}", file=sys.stderr)
        print(f"  - Plate: {metadata_json['plate']}", file=sys.stderr)
        if 'image_metadata' in metadata_json:
            print(f"  - Image metadata: {len(metadata_json['image_metadata'])} entries", file=sys.stderr)
        if 'well' in metadata_json:
            print(f"  - Well: {metadata_json['well']}", file=sys.stderr)
        if 'site' in metadata_json:
            print(f"  - Site: {metadata_json['site']}", file=sys.stderr)
        if 'cycle' in metadata_json:
            print(f"  - Cycle: {metadata_json['cycle']}", file=sys.stderr)
        if 'channels' in metadata_json:
            print(f"  - Channels: {', '.join(metadata_json['channels'])}", file=sys.stderr)

        # Extract metadata with CLI arg overrides where applicable
        # Channels: CLI arg > JSON metadata
        metadata_channels = None
        if args.channels:
            metadata_channels = [ch.strip() for ch in args.channels.split(',')]
            print(f"✓ Using CLI arg channels (overriding JSON): {metadata_channels}", file=sys.stderr)
        elif 'channels' in metadata_json:
            metadata_channels = metadata_json['channels']

        # Cycle: CLI arg > JSON metadata
        metadata_cycle = None
        if args.cycle:
            metadata_cycle = args.cycle
            print(f"✓ Using CLI arg cycle (overriding JSON): {metadata_cycle}", file=sys.stderr)
        elif 'cycle' in metadata_json:
            metadata_cycle = metadata_json['cycle']

        # Parse cycles if provided (for multi-cycle processing)
        metadata_cycles = None
        if args.cycles:
            metadata_cycles = [int(c.strip()) for c in args.cycles.split(',')]
            print(f"✓ Using CLI arg cycles (overriding JSON): {metadata_cycles}", file=sys.stderr)
        elif 'cycles' in metadata_json:
            metadata_cycles = metadata_json['cycles']
            print(f"✓ Using cycles from JSON metadata: {metadata_cycles}", file=sys.stderr)

        # Collect and group files
        print(f"\nStep 1/4: Collecting and grouping files...", file=sys.stderr)
        grouped = collect_and_group_files(
            args.images_dir,
            args.pipeline_type,
            args.illum_dir,
            metadata_cycle,
            metadata_cycles,
            metadata_json
        )

        # Generate rows
        print(f"\nStep 2/4: Generating CSV rows...", file=sys.stderr)
        rows = generate_csv_rows(
            grouped,
            args.pipeline_type,
            args.range_skip,
            metadata_channels,
            args.has_cycles,
            metadata_cycle,
            metadata_json
        )

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
        # Metadata columns are now determined dynamically from the data
        # We still determine expected columns for validation purposes
        if args.has_cycles and 'metadata_cols_with_cycles' in config:
            expected_metadata_cols = config['metadata_cols_with_cycles']
        elif 'metadata_cols' in config and config['metadata_cols']:
            expected_metadata_cols = config['metadata_cols']
        elif 'metadata_cols_base' in config:
            expected_metadata_cols = config['metadata_cols_base']
        else:
            expected_metadata_cols = []
        write_csv(rows, args.output, expected_metadata_cols)

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
