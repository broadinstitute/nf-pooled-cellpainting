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
        'file_pattern': r'.*\.(?:ome\.tiff?|nd2)$',
        'metadata_cols': None,  # Dynamic based on has_cycles
        'metadata_cols_base': ['Metadata_Plate', 'Metadata_Well', 'Metadata_Site'],
        'metadata_cols_with_cycles': ['Metadata_Plate', 'Metadata_Well', 'Metadata_Site'],  # Cycle column name will be added dynamically
        'include_illum_files': False,
        'supports_subdirs': False,
        'cycle_aware': False,
        'parse_function': 'parse_original_image'
    },
    'illumapply': {
        'description': 'Illumination correction - uses original images + illumination functions',
        'file_pattern': r'.*\.(?:ome\.tiff?|nd2)$',
        'metadata_cols': ['Metadata_Plate', 'Metadata_Well', 'Metadata_Site'],
        'include_illum_files': True,
        'supports_subdirs': True,
        'cycle_aware': True,
        'parse_function': 'parse_original_image'
    },
    'segcheck': {
        'description': 'Segmentation check - uses corrected images',
        'file_pattern': r'Plate_.*_Well_.*_Site_.*_Corr.*\.(?:tiff?|nd2)$',
        'metadata_cols': ['Metadata_Plate', 'Metadata_Site', 'Metadata_Well', 'Metadata_Well_Value'],
        'include_illum_files': False,
        'parse_function': 'parse_corrected_image'
    },
    'analysis': {
        'description': 'Full analysis - uses corrected images',
        'file_pattern': r'Plate_.*_Well_.*_Site_.*_Corr.*\.(?:tiff?|nd2)$',
        'metadata_cols': ['Metadata_Plate', 'Metadata_Well', 'Metadata_Site'],
        'include_illum_files': False,
        'parse_function': 'parse_corrected_image'
    },
    'preprocess': {
        'description': 'Barcoding preprocessing - uses cycle-based corrected images',
        'file_pattern': r'Plate_.*_Well_.*_Site_.*_Cycle\d+_(DNA|DAPI|[ACGT])\.(?:tiff?|nd2)$',
        'metadata_cols': ['Metadata_Plate', 'Metadata_Site', 'Metadata_Well', 'Metadata_Well_Value'],
        'include_illum_files': False,
        'parse_function': 'parse_preprocess_image'
    },
    'combined': {
        'description': 'Combined analysis - uses both cropped cell painting and barcoding images',
        'file_pattern': r'(Plate_.*_Well_.*_Site_.*_Corr.*\.(?:tiff?|nd2)|Plate_.*_Well_.*_Site_.*_Cycle\d{2}_\w+\.(?:tiff?|nd2)|Plate\d+-[A-Z]\d+_Corr.*_Site_\d+\.(?:tiff?|nd2)|Plate\d+-[A-Z]\d+_Cycle\d+_\w+_Site_\d+\.(?:tiff?|nd2))$',
        'metadata_cols': ['Metadata_Plate', 'Metadata_Site', 'Metadata_Well', 'Metadata_Well_Value'],
        'include_illum_files': False,
        'parse_function': 'parse_combined_image'
    }
}


def parse_original_image(filename: str) -> Optional[Dict]:
    """
    Parse original multi-channel image filename to extract ONLY channel information.

    IMPORTANT: This function ONLY parses channel info from filenames.
    Metadata (plate, well, site, cycle) MUST come from JSON - NOT from filenames.

    Expected filename patterns:
    - Non-cycle: WellA1_PointA1_0000_ChannelCHN1,CHN2,CHN3_Seq0000.ome.tiff
    - With cycle: WellA1_PointA1_0000_ChannelCHN1,CHN2,CHN3_Cycle03_Seq0000.ome.tiff

    Args:
        filename: Image filename to parse

    Returns:
        Dict with:
        - 'channels': List of channel names (e.g., ['DNA', 'Phalloidin', 'CHN2'])
        - 'frames': Dict mapping channel name to frame index (0-indexed)
        Returns None if filename doesn't match expected pattern

    Note: The channel list can be comma-separated in the filename (multi-channel OME-TIFF)
    """
    # Try pattern with cycle first (to detect cycle presence, but don't extract it)
    # Regex breakdown: Well[A-Z]\d+_Point[A-Z]\d+_\d+_Channel([^_]+)_Cycle\d+_Seq\d+\.(?:ome\.tiff?|nd2)
    #   - Well[A-Z]\d+: WellA1, WellB2, etc. (not captured - metadata from JSON)
    #   - Point[A-Z]\d+: PointA1, PointB2, etc. (not captured - site comes from JSON)
    #   - \d+: Numeric sequence (not captured)
    #   - Channel([^_]+): Captures channel names (e.g., "DNA,Phalloidin,CHN2")
    #   - Cycle\d+: Cycle number (not captured - cycle from JSON)
    #   - Seq\d+: Sequence number (not captured)
    pattern_with_cycle = r'Well[A-Z]\d+_Point[A-Z]\d+_\d+_Channel([^_]+)_Cycle\d+_Seq\d+\.(?:ome\.tiff?|nd2)'
    match = re.search(pattern_with_cycle, filename)

    if match:
        channels_str = match.group(1)
        # Parse channels - could be comma-separated (e.g., "DNA,Phalloidin,CHN2")
        channels = [ch.strip() for ch in channels_str.split(',')]
        # Build frame mapping - each channel gets its sequential frame number
        # Frame 0 = first channel, Frame 1 = second channel, etc.
        frames = {ch: idx for idx, ch in enumerate(channels)}
        return {
            'channels': channels,
            'frames': frames
        }

    # Try pattern without cycle (same structure but no Cycle\d+ component)
    pattern = r'Well[A-Z]\d+_Point[A-Z]\d+_\d+_Channel([^_]+)_Seq\d+\.(?:ome\.tiff?|nd2)'
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
    Parse corrected (illumination-corrected) image filename to extract ONLY channel information.

    IMPORTANT: This function ONLY parses channel info from filenames.
    Metadata (plate, well, site) MUST come from JSON - NOT from filenames.

    Expected filename pattern:
    - Plate_{plate}_Well_{well}_Site_{site}_Corr{channel}.tiff
    - Example: Plate_Plate1_Well_A1_Site_1_CorrDNA.tiff

    Args:
        filename: Corrected image filename to parse

    Returns:
        Dict with:
        - 'channel': Channel name (e.g., 'DNA', 'Phalloidin')
        Returns None if filename doesn't match expected pattern

    Note: These are single-channel TIFF files produced after illumination correction
    """
    # Regex breakdown: Plate_.+?_Well_.+?_Site_\d+_Corr(.+?)\.(?:tiff?|nd2)
    #   - Plate_.+?: Plate identifier (not captured - comes from JSON)
    #   - Well_.+?: Well identifier (not captured - comes from JSON)
    #   - Site_\d+: Site number (not captured - comes from JSON)
    #   - Corr(.+?): Captures channel name after "Corr" prefix (e.g., "DNA", "Phalloidin")
    #   - \.(?:tiff?|nd2): File extension (.tif, .tiff, or .nd2)
    pattern = r'Plate_.+?_Well_.+?_Site_\d+_Corr(.+?)\.(?:tiff?|nd2)'
    match = re.match(pattern, filename)

    if match:
        return {
            'channel': match.group(1)
        }
    return None


def parse_preprocess_image(filename: str) -> Optional[Dict]:
    """
    Parse barcoding preprocess image filename to extract ONLY cycle and channel information.

    IMPORTANT: This function ONLY parses cycle/channel info from filenames.
    Metadata (plate, well, site) MUST come from JSON - NOT from filenames.

    Expected filename pattern:
    - Plate_{plate}_Well_{well}_Site_{site}_Cycle{cycle}_{channel}.tiff
    - Examples:
      * Plate_Plate1_Well_A1_Site_1_Cycle01_DNA.tiff (reference image)
      * Plate_Plate1_Well_A1_Site_1_Cycle02_A.tiff (barcode base A)
      * Plate_Plate1_Well_A1_Site_1_Cycle03_G.tiff (barcode base G)

    Args:
        filename: Barcoding preprocess image filename to parse

    Returns:
        Dict with:
        - 'cycle': Cycle number as zero-padded string (e.g., "01", "02", "03")
        - 'channel': Channel name - either A, C, G, T for barcode bases, or DNA for reference
        Returns None if filename doesn't match expected pattern

    Note: DAPI is automatically normalized to DNA for consistency
    """
    # Try standard pattern first (for barcode bases: A, C, G, T)
    # Regex breakdown: Plate_.+?_Well_.+?_Site_\d+_Cycle(\d+)_([ACGT])\.(?:tiff?|nd2)
    #   - Plate_.+?: Plate identifier (not captured - comes from JSON)
    #   - Well_.+?: Well identifier (not captured - comes from JSON)
    #   - Site_\d+: Site number (not captured - comes from JSON)
    #   - Cycle(\d+): Captures cycle number (e.g., "01", "02", "03")
    #   - ([ACGT]): Captures barcode base (A, C, G, or T)
    pattern = r'Plate_.+?_Well_.+?_Site_\d+_Cycle(\d+)_([ACGT])\.(?:tiff?|nd2)'
    match = re.match(pattern, filename)

    if match:
        return {
            'cycle': match.group(1),  # Keep as string (e.g., "01", "02", "03")
            'channel': match.group(2)
        }

    # Try DNA/DAPI pattern (typically for Cycle01 reference image)
    # Accepts both DNA and DAPI, normalizes to DNA for consistency
    dna_pattern = r'Plate_.+?_Well_.+?_Site_\d+_Cycle(\d+)_(DNA|DAPI)\.(?:tiff?|nd2)'
    dna_match = re.match(dna_pattern, filename)

    if dna_match:
        return {
            'cycle': dna_match.group(1),
            'channel': 'DNA'  # Normalize DAPI to DNA for consistency
        }

    return None


def parse_combined_image(filename: str) -> Optional[Dict]:
    """
    Parse combined analysis image filenames to extract ONLY cycle and channel information.

    IMPORTANT: This function ONLY parses cycle/channel/type info from filenames.
    Metadata (plate, well, site) MUST come from JSON - NOT from filenames.

    The combined analysis pipeline uses both barcoding and cell painting images together.
    This function detects the image type and extracts relevant channel information.

    Expected filename patterns (new standardized format):
    1. Barcoding images:
       - Pattern: Plate_PlateID_Well_WellID_Site_#_Cycle##_Channel.tiff
       - Cycle: 2-digit zero-padded (01, 02, ..., 10, 11, etc.)
       - Channel: A, C, G, T (barcode bases) or DNA/DAPI (reference)
       - Example: Plate_Plate1_Well_A1_Site_1_Cycle02_A.tiff

    2. Cell painting images:
       - Pattern: Plate_PlateID_Well_WellID_Site_#_CorrChannel.tiff
       - Channel: DNA, Phalloidin, CHN2, etc.
       - Example: Plate_Plate1_Well_A1_Site_1_CorrDNA.tiff

    Legacy patterns (for backward compatibility):
    - Barcoding: Plate{plate}-{well}_Cycle{cycle}_{channel}_Site_{site}.tiff
    - Cell painting: Plate{plate}-{well}_Corr{channel}_Site_{site}.tiff

    Args:
        filename: Combined analysis image filename to parse

    Returns:
        Dict with:
        - 'type': Either 'barcoding' or 'cellpainting'
        - 'channel': Channel name (always present)
        - 'cycle': Cycle number as string (only for barcoding images)
        Returns None if filename doesn't match any expected pattern

    Note: DAPI is automatically normalized to DNA for consistency
    """
    # Try new barcoding pattern first (Plate_PlateID_Well_WellID_Site_#_Cycle##_Channel.tiff)
    # Note: cycle is 2-digit zero-padded (\d{2}) to handle cycles > 9
    barcode_new_pattern = r'Plate_[A-Za-z0-9]+_Well_[A-Z]\d+_Site_\d+_Cycle(\d{2})_([ACGT]|DNA|DAPI)\.(?:tiff?|nd2)'
    barcode_new_match = re.match(barcode_new_pattern, filename)

    if barcode_new_match:
        return {
            'cycle': barcode_new_match.group(1),
            'channel': 'DNA' if barcode_new_match.group(2) == 'DAPI' else barcode_new_match.group(2),
            'type': 'barcoding'
        }

    # Try new cell painting pattern (Plate_PlateID_Well_WellID_Site_#_CorrChannel.tiff)
    cp_new_pattern = r'Plate_[A-Za-z0-9]+_Well_[A-Z]\d+_Site_\d+_Corr(.+?)\.(?:tiff?|nd2)'
    cp_new_match = re.match(cp_new_pattern, filename)

    if cp_new_match:
        return {
            'channel': cp_new_match.group(1),
            'type': 'cellpainting'
        }

    # Legacy pattern support: barcoding (Plate{plate}-{well}_Cycle{cycle}_{channel}_Site_{site}.tiff)
    barcode_legacy_pattern = r'Plate\d+-[A-Z]\d+_Cycle(\d+)_([ACGT]|DNA|DAPI)_Site_\d+\.(?:tiff?|nd2)'
    barcode_legacy_match = re.match(barcode_legacy_pattern, filename)

    if barcode_legacy_match:
        return {
            'cycle': barcode_legacy_match.group(1),
            'channel': 'DNA' if barcode_legacy_match.group(2) == 'DAPI' else barcode_legacy_match.group(2),
            'type': 'barcoding'
        }

    # Legacy pattern support: cell painting (Plate{plate}-{well}_Corr{channel}_Site_{site}.tiff)
    cp_legacy_pattern = r'Plate\d+-[A-Z]\d+_Corr(.+?)_Site_\d+\.(?:tiff?|nd2)'
    cp_legacy_match = re.match(cp_legacy_pattern, filename)

    if cp_legacy_match:
        return {
            'channel': cp_legacy_match.group(1),
            'type': 'cellpainting'
        }

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

    ALL metadata (plate, well, site, cycle, channels) MUST come from JSON.
    Filename parsing for metadata is NOT supported - JSON is the single source of truth.

    Args:
        metadata_json_path: Path to metadata JSON file (REQUIRED)

    Returns:
        Dict with keys:
        - plate (REQUIRED): Plate identifier
        - well, site (REQUIRED): Must provide EITHER:
            * 'image_metadata' array with well/site for each image, OR
            * Both 'well' and 'site' fields for single-location processing
        - cycle (optional): Cycle number for barcoding workflows
        - cycles (optional): List of cycle numbers for multi-cycle processing
        - channels (optional): List of channel names
        - batch, arm (optional): Additional metadata fields

    Raises:
        FileNotFoundError: If metadata file doesn't exist
        ValueError: If required fields are missing

    Example JSON structures:

        1. Simplified array format (NEW - most common):
        [
            {"batch": "batch1", "plate": "Plate1", "well": "A1", "site": 0, "channels": ["DNA", "Phalloidin"], "arm": "painting", "filename": "WellA1_PointA1_0000_Channel..."},
            {"batch": "batch1", "plate": "Plate1", "well": "A1", "site": 1, "channels": ["DNA", "Phalloidin"], "arm": "painting", "filename": "WellA1_PointA2_0000_Channel..."}
        ]
        Common fields (plate, channels, batch, arm, cycle) are extracted from first entry.

        2. Multi-location (image_metadata array):
        {
            "plate": "Plate1",
            "channels": ["DNA", "Phalloidin", "CHN2"],
            "image_metadata": [
                {"well": "A1", "site": 0, "filename": "WellA1_PointA1_0000_Channel..."},
                {"well": "A1", "site": 1, "filename": "WellA1_PointA2_0000_Channel..."},
                {"well": "A2", "site": 0, "filename": "WellA2_PointA1_0000_Channel..."}
            ]
        }

        3. Single-location (direct well/site):
        {
            "plate": "Plate1",
            "well": "A1",
            "site": 1,
            "cycle": 1,
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

    # Handle simplified array format: if JSON is an array, extract common fields from first entry
    if isinstance(metadata, list):
        if not metadata:
            raise ValueError("Metadata JSON array is empty")

        # Extract common fields from first entry
        first_entry = metadata[0]
        normalized_metadata = {
            'image_metadata': metadata  # The full array becomes image_metadata
        }

        # Extract common fields that should be consistent across all entries
        if 'plate' in first_entry:
            normalized_metadata['plate'] = first_entry['plate']
        if 'channels' in first_entry:
            normalized_metadata['channels'] = first_entry['channels']
        if 'batch' in first_entry:
            normalized_metadata['batch'] = first_entry['batch']
        if 'arm' in first_entry:
            normalized_metadata['arm'] = first_entry['arm']

        # Detect cycles: if multiple unique cycles exist, create 'cycles' list
        # Otherwise use single 'cycle' value
        unique_cycles = sorted(set(
            entry.get('cycle')
            for entry in metadata
            if entry.get('cycle') is not None
        ))
        if len(unique_cycles) > 1:
            normalized_metadata['cycles'] = unique_cycles
            print(f"✓ Detected {len(unique_cycles)} cycles: {unique_cycles}", file=sys.stderr)
        elif len(unique_cycles) == 1:
            normalized_metadata['cycle'] = unique_cycles[0]
            print(f"✓ Detected single cycle: {unique_cycles[0]}", file=sys.stderr)

        metadata = normalized_metadata
        print(f"✓ Detected simplified array format with {len(metadata['image_metadata'])} entries", file=sys.stderr)

    # Validate required fields: plate is always required
    if 'plate' not in metadata:
        raise ValueError(
            "Metadata JSON is missing required field: 'plate'."
        )

    # Require either image_metadata array OR both well and site
    has_image_metadata = 'image_metadata' in metadata
    has_well_site = 'well' in metadata and 'site' in metadata

    if not has_image_metadata and not has_well_site:
        raise ValueError(
            "Metadata JSON must provide either:\n"
            "  1. 'image_metadata' array with well/site for each image, OR\n"
            "  2. Both 'well' and 'site' fields for single-location processing\n"
            "All metadata must come from JSON - filename parsing is not supported."
        )

    # Validate and normalize the structure
    result = {}

    # Extract required field
    result['plate'] = str(metadata['plate'])

    # Extract well and site fields (now required via validation above)
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


def collect_and_group_files(
    images_dir: str,
    pipeline_type: str,
    illum_dir: Optional[str] = None,
    metadata_cycle: Optional[int] = None,
    metadata_cycles: Optional[List[int]] = None,
    metadata_json: Dict = None
) -> Dict[Tuple, Dict]:
    """
    Collect image files and group them by (plate, well, site) for CSV generation.

    This function is the core file discovery and grouping logic. It:
    1. Validates that metadata JSON is provided (required - no filename parsing)
    2. Finds all image files matching the pipeline-specific pattern
    3. Groups files by (plate, well, site) tuple using JSON metadata
    4. Matches illumination correction files if needed (for illumapply pipeline)

    IMPORTANT: ALL metadata (plate, well, site, cycle) comes from JSON.
    Filenames are ONLY parsed for channel/cycle information, NOT metadata.

    Two modes of operation:
    A. image_metadata array mode (most common):
       - JSON contains array of {well, site, filename, ...} entries
       - Each entry represents one image or set of images
       - Files matched by filename from JSON (NO parsing needed)

    B. Single-location mode:
       - JSON contains single well/site values
       - All files in images_dir are grouped under that one location

    Args:
        images_dir: Directory containing images (recursively searched)
        pipeline_type: Type of pipeline (illumcalc, illumapply, analysis, etc.)
        illum_dir: Directory containing illumination .npy files (optional)
        metadata_cycle: Single cycle number for cycle-specific processing (optional)
        metadata_cycles: List of cycle numbers for multi-cycle processing (optional)
        metadata_json: Metadata dict from JSON file (REQUIRED - source of ALL metadata)

    Returns:
        Dict mapping (plate, well, site) tuple to:
        {
            'images': {
                # For multi-channel files:
                '_file': 'path/to/image.ome.tiff',  # single multi-channel image
                # OR for single-channel files:
                'CorrDNA': 'path/to/corrected_DNA.tiff',
                'CorrPhalloidin': 'path/to/corrected_Phalloidin.tiff',
                # OR for cycle-based files:
                'Cycle01_A': 'path/to/cycle01_A.tiff',
                'Cycle02_C': 'path/to/cycle02_C.tiff',
            },
            'illum': {
                'DNA': 'Plate1_IllumDNA.npy',
                'Phalloidin': 'Plate1_IllumPhalloidin.npy',
            },
            'cycles': {1, 2, 3}  # Set of cycle numbers (if applicable)
        }

    Raises:
        ValueError: If metadata_json is missing or lacks required fields
        FileNotFoundError: If images_dir or illum_dir don't exist
        IOError: If file search fails
    """
    # Validate metadata JSON is provided
    if not metadata_json:
        raise ValueError(
            "Metadata JSON is required but was not provided. "
            "Use --metadata-json to specify the metadata file."
        )

    # Validate required metadata: plate is always required
    # Well and site must be provided either via image_metadata array or directly in JSON
    if 'plate' not in metadata_json:
        raise ValueError(
            "Metadata JSON is missing required field: 'plate'. "
            "Plate must always come from metadata JSON."
        )

    # Check if we have image_metadata array or direct well/site fields
    use_image_metadata = 'image_metadata' in metadata_json
    has_direct_well_site = 'well' in metadata_json and 'site' in metadata_json

    # Require either image_metadata array OR both well and site fields
    if not use_image_metadata and not has_direct_well_site:
        raise ValueError(
            "Metadata JSON must provide either:\n"
            "  1. 'image_metadata' array with well/site for each image, OR\n"
            "  2. Both 'well' and 'site' fields for single-location processing\n"
            "All metadata must come from JSON - filename parsing is not supported."
        )

    if use_image_metadata:
        print(f"✓ Using image_metadata array with {len(metadata_json['image_metadata'])} entries", file=sys.stderr)
    else:
        print(f"✓ Using well={metadata_json['well']} and site={metadata_json['site']} from JSON metadata", file=sys.stderr)

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

    # ==================================================================================
    # STEP 2: Group files by (plate, well, site)
    # ==================================================================================
    # Strategy depends on whether we're using image_metadata array or single-location mode

    grouped = {}  # Dict mapping (plate, well, site) -> {'images': {...}, 'illum': {...}}
    parse_errors = []  # Track files that failed to parse
    missing_metadata = []  # Track files with missing metadata

    # MODE A: image_metadata array - match files by FILENAME (most common)
    # ==================================================================================
    if use_image_metadata:
        # In this mode, the JSON contains an array like:
        # "image_metadata": [
        #     {"well": "A1", "site": 0, "filename": "WellA1_PointA1_..."},
        #     {"well": "A1", "site": 1, "filename": "WellA1_PointA2_..."}
        # ]
        # We match files by filename - NO parsing of metadata from filenames!

        plate = metadata_json['plate']  # Plate comes from JSON

        # Build a lookup map: filename -> full file path
        # This allows fast matching of JSON filenames to actual files on disk
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

    # MODE B: Single-location mode - all files belong to one (plate, well, site)
    # ==================================================================================
    else:
        # In this mode, the JSON contains single well/site values:
        # {
        #     "plate": "Plate1",
        #     "well": "A1",
        #     "site": 1,
        #     "channels": ["DNA", "Phalloidin", "CHN2"]
        # }
        # All files in images_dir are grouped under this one location.
        # We still need to parse filenames for channel/cycle info.

        for img_path in image_files:
            filename = os.path.basename(img_path)
            # Calculate relative path from images_dir to preserve subdirectory structure
            rel_path = os.path.relpath(img_path, images_dir)

            # Parse filename for channel/cycle information (NOT metadata!)
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

            # Get metadata - ALL from JSON (plate, well, site)
            # Filenames are ONLY parsed for channel/cycle info above
            plate = metadata_json['plate']
            well = metadata_json['well']
            site = metadata_json['site']

            key = (plate, well, site)  # Single key for all files

            if key not in grouped:
                grouped[key] = {'images': {}, 'illum': {}, 'cycles': set()}

            # Store files based on what was parsed from filename
            # Different storage strategies for different file types
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

    # Normalize single-cycle data: if images are in _files_by_cycle format with only one cycle,
    # check if illum files are in non-cycle format and convert them to match
    for key in grouped.keys():
        if '_files_by_cycle' in grouped[key]['images']:
            cycles_list = list(grouped[key]['images']['_files_by_cycle'].keys())
            if len(cycles_list) == 1:
                # Single cycle - check if illum files need conversion
                cycle_num = cycles_list[0]
                # Check if we have non-cycle illum files (direct channel mapping)
                has_non_cycle_illum = any(
                    k for k in grouped[key]['illum'].keys()
                    if not k.startswith('_')
                )
                if has_non_cycle_illum and '_by_cycle' not in grouped[key]['illum']:
                    # Convert non-cycle illum files to _by_cycle format
                    direct_illum = {k: v for k, v in grouped[key]['illum'].items() if not k.startswith('_')}
                    grouped[key]['illum']['_by_cycle'] = {cycle_num: direct_illum}
                    # Remove direct entries
                    for channel in direct_illum.keys():
                        del grouped[key]['illum'][channel]
                    print(f"✓ Normalized single-cycle illum files for {key}", file=sys.stderr)

    return grouped


def generate_csv_rows(
    grouped: Dict,
    pipeline_type: str,
    range_skip: int = 1,
    metadata_channels: Optional[List[str]] = None,
    has_cycles: bool = False,
    metadata_cycle: Optional[int] = None,
    metadata_json: Dict = None,
    cycle_metadata_name: str = "Cycle"
) -> List[Dict]:
    """
    Generate CellProfiler load_data.csv rows from grouped file data.

    This function converts the grouped file structure into CSV rows suitable for CellProfiler.
    Each row represents one imaging site and contains:
    - Metadata columns (Metadata_Plate, Metadata_Well, Metadata_Site, etc.)
    - File columns (FileName_ChannelName and Frame_ChannelName for each channel)
    - Illumination file columns (FileName_IllumChannelName) if applicable

    The exact columns depend on:
    - Pipeline type (illumcalc, illumapply, analysis, preprocess, combined)
    - Whether data has cycles (barcoding workflows)
    - What metadata is provided in JSON

    Row generation logic handles several file organization patterns:
    1. Multi-channel OME-TIFF files (one file, multiple channels as frames)
    2. Single-channel TIFF files (one file per channel)
    3. Cycle-based files (for barcoding: Cycle01_DNA, Cycle02_A, etc.)
    4. Combined analysis (both cell painting and barcoding files)

    Args:
        grouped: Dict from collect_and_group_files() mapping (plate, well, site) to file data
        pipeline_type: Pipeline type (illumcalc, illumapply, segcheck, analysis, preprocess, combined)
        range_skip: Subsampling interval - use every Nth site (default: 1 = all sites)
        metadata_channels: Channel names from metadata (overrides JSON if provided)
        has_cycles: Whether data contains cycle information (for barcoding workflows)
        metadata_cycle: Cycle number for single-cycle processing
        metadata_json: Metadata dict from JSON file (REQUIRED - source of all metadata)

    Returns:
        List of dict, where each dict is one CSV row with column names as keys

        Example row structure:
        {
            'Metadata_Plate': 'Plate1',
            'Metadata_Well': 'A1',
            'Metadata_Site': 1,
            'FileName_OrigDNA': 'WellA1_PointA1_0000_ChannelDNA,Phalloidin,CHN2_Seq0000.ome.tiff',
            'Frame_OrigDNA': 0,
            'FileName_OrigPhalloidin': 'WellA1_PointA1_0000_ChannelDNA,Phalloidin,CHN2_Seq0000.ome.tiff',
            'Frame_OrigPhalloidin': 1,
            'FileName_IllumDNA': 'Plate1_IllumDNA.npy',
            'FileName_IllumPhalloidin': 'Plate1_IllumPhalloidin.npy'
        }

    Raises:
        ValueError: If metadata_json is missing, lacks required fields, or channels not specified
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
        metadata_columns.append(f'Metadata_{cycle_metadata_name}')

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

    rows = []  # List of CSV row dicts
    row_errors = []  # Track rows that failed to generate

    # ==================================================================================
    # Generate one CSV row per (plate, well, site)
    # ==================================================================================
    for (plate, well, site), file_data in sorted(grouped.items()):
        # Skip sites not selected by subsampling
        if site not in selected_sites:
            continue

        try:
            # ------------------------------------------------------------------
            # Build metadata columns (from JSON metadata)
            # ------------------------------------------------------------------
            row = {}

            # Always include Metadata_Plate (required in JSON)
            row['Metadata_Plate'] = plate

            # Conditionally include Metadata_Well if present in JSON
            if has_well:
                row['Metadata_Well'] = well
                # Some pipelines (segcheck, preprocess) use Metadata_Well_Value as well
                config_cols = config.get('metadata_cols', []) or config.get('metadata_cols_base', [])
                if 'Metadata_Well_Value' in config_cols:
                    row['Metadata_Well_Value'] = well

            # Conditionally include Metadata_Site if present in JSON
            if has_site:
                row['Metadata_Site'] = site

            # Conditionally include Metadata_Cycle (or custom cycle column name) for barcoding workflows
            if has_cycles and has_cycle:
                cycle_col_name = f'Metadata_{cycle_metadata_name}'
                if 'cycle' in metadata_json:
                    row[cycle_col_name] = metadata_json['cycle']
                elif metadata_cycle is not None:
                    row[cycle_col_name] = metadata_cycle
                else:
                    raise ValueError(f"{cycle_col_name} required but not found in metadata JSON or arguments")

            # ------------------------------------------------------------------
            # Build file columns (FileName_* and Frame_* columns)
            # Strategy depends on file organization pattern
            # ------------------------------------------------------------------

            # PATTERN 1: Multi-cycle multi-channel files
            # (e.g., illumcalc with multiple cycles)
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

                # Check if we have multiple cycles - if only one, don't use cycle prefix
                num_cycles = len(files_by_cycle)
                use_cycle_prefix = num_cycles > 1

                # Sort cycles to ensure consistent column order
                for cycle_num in sorted(files_by_cycle.keys()):
                    cycle_info = files_by_cycle[cycle_num]
                    filename = cycle_info['file']
                    cycle_str = f"{cycle_num:02d}"

                    # Add FileName and Frame for each channel in this cycle
                    # Frame number is just the index in the channels list
                    for frame_idx, channel in enumerate(channels_to_use):
                        if use_cycle_prefix:
                            row[f'FileName_Cycle{cycle_str}_Orig{channel}'] = filename
                            row[f'Frame_Cycle{cycle_str}_Orig{channel}'] = frame_idx
                        else:
                            row[f'FileName_Orig{channel}'] = filename
                            row[f'Frame_Orig{channel}'] = frame_idx

                        # Add illumination file if available for this cycle
                        if cycle_num in illum_by_cycle and channel in illum_by_cycle[cycle_num]:
                            if use_cycle_prefix:
                                row[f'FileName_Cycle{cycle_str}_Illum{channel}'] = illum_by_cycle[cycle_num][channel]
                            else:
                                row[f'FileName_Illum{channel}'] = illum_by_cycle[cycle_num][channel]

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

            # PATTERN 2: Single multi-channel file (e.g., one OME-TIFF with all channels)
            # (e.g., illumcalc without cycles, illumapply single cycle)
            elif '_file' in file_data['images']:
                # One multi-channel file contains all channels as frames
                # Example: WellA1_PointA1_0000_ChannelDNA,Phalloidin,CHN2_Seq0000.ome.tiff
                filename = file_data['images']['_file']

                # Get channels from JSON metadata (required!)
                if metadata_json and 'channels' in metadata_json:
                    channels_to_use = metadata_json['channels']
                elif metadata_channels:
                    channels_to_use = metadata_channels
                else:
                    raise ValueError("Channels must be specified in JSON metadata or CLI args")

                # Determine if we need cycle-specific column names
                # (for illumapply with cycle-aware flag)
                use_cycle_columns = config.get('cycle_aware', False) and metadata_cycle is not None

                # Add FileName and Frame for each channel
                # All channels point to the same file, differentiated by Frame number
                # Frame 0 = first channel, Frame 1 = second channel, etc.
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
            # PATTERN 3: Single-channel files or cycle-based files
            # (e.g., analysis, segcheck, preprocess, combined pipelines)
            else:
                # Multiple separate files, one per channel or per cycle/channel combination
                # Examples:
                #   - Analysis: Plate_Plate1_Well_A1_Site_1_CorrDNA.tiff, Plate_Plate1_Well_A1_Site_1_CorrPhalloidin.tiff
                #   - Preprocess: Plate_Plate1_Well_A1_Site_1_Cycle01_DNA.tiff, Plate_Plate1_Well_A1_Site_1_Cycle02_A.tiff
                if not file_data['images']:
                    raise ValueError(f"No image files for {plate}/{well}/Site{site}")

                # For combined analysis, handle both cell painting and barcoding files
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
    parser.add_argument(
        '--cycle-metadata-name',
        default='Cycle',
        help='Name for the cycle metadata column (default: "Cycle", e.g., "Metadata_Cycle")'
    )

    args = parser.parse_args()

    # Validate arguments
    config = PIPELINE_CONFIGS[args.pipeline_type]
    if config['include_illum_files'] and not args.illum_dir:
        parser.error(f"--illum-dir required for pipeline type '{args.pipeline_type}'")

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
            metadata_json,
            args.cycle_metadata_name
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
