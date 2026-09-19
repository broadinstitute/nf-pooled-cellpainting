#!/usr/bin/env python3
"""
General-purpose load_data.csv generator for CellProfiler pipelines.

Every caller (5 Nextflow modules: illumcalc, illumapply, segcheck, preprocess,
combinedanalysis) builds the SAME canonical metadata JSON shape - a top-level
object with an explicit `image_metadata` array, one entry per (physical file,
channel) pair:

    {
      "plate": "Plate1", "batch": "Batch1", "cycles": [1, 2, 3],
      "image_metadata": [
        {"well": "A1", "site": 0, "arm": "painting", "cycle": 1,
         "channel": "DNA", "frame_index": 2, "column_prefix": "Orig",
         "filename": "...", "original_path": "...", "original_filename": "..."}
      ]
    }

There is no filename parsing and no shape inference anywhere in this script:
every field the CSV needs is stated explicitly by the Nextflow caller. A
multichannel file (e.g. a 3-frame OME-TIFF) contributes multiple entries
sharing one `filename`, differentiated by `channel`/`frame_index`. A
single-channel file contributes one entry with `frame_index` absent, which is
what makes the `Frame_` column absent/present in the output.

`column_prefix` (""/"Orig"/"Corr") is the caller-stated CellProfiler column
prefix - it is NOT derived from `arm`, since the same arm's channels can need
different prefixes in different pipeline stages (e.g. painting segcheck wants
bare "DNA" while painting combined-analysis wants "CorrDNA"). `arm` is carried
for informational/debugging value only; this script never branches on it.

Every entry's `filename` is trusted directly (joined with --images-dir) - no
directory glob, no regex filtering, no substring search. This is sound because
every real caller already resolves `filename` to the exact staged path before
invoking this script: illumcalc/illumapply's module preamble does a
realpath-based remap (and hard-fails if any entry can't be resolved), and
segcheck/preprocess/combinedanalysis stage flatly with unique basenames.
"""

import argparse
import csv
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple


VALID_ARMS = ('painting', 'barcoding')
VALID_PREFIXES = ('', 'Orig', 'Corr')


def load_metadata_json(metadata_json_path: str) -> Dict:
    """
    Load and validate the metadata JSON emitted by every Nextflow caller.

    The JSON is always a top-level object: {plate, batch?, cycles?, cycle?,
    image_metadata: [entry, ...]}. Each entry is one (file, channel) pair:
    {well, site, arm, channel, column_prefix, filename, cycle?, frame_index?,
    original_path?, original_filename?}.

    Raises:
        FileNotFoundError: If metadata file doesn't exist
        ValueError: If required fields are missing or malformed
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

    if not isinstance(metadata, dict):
        raise ValueError(
            "Metadata JSON must be a top-level object with 'plate' and "
            "'image_metadata' - the Nextflow caller must emit the wrapper object."
        )
    for field in ('plate', 'image_metadata'):
        if field not in metadata:
            raise ValueError(f"Metadata JSON is missing required field: '{field}'")
    if not isinstance(metadata['image_metadata'], list) or not metadata['image_metadata']:
        raise ValueError("'image_metadata' must be a non-empty array")

    result = {'plate': str(metadata['plate']), 'image_metadata': []}
    if 'batch' in metadata and metadata['batch'] is not None:
        result['batch'] = str(metadata['batch'])

    for idx, entry in enumerate(metadata['image_metadata']):
        if not isinstance(entry, dict):
            raise ValueError(f"image_metadata[{idx}] must be an object")
        for field in ('well', 'site', 'arm', 'channel', 'column_prefix', 'filename'):
            if field not in entry:
                raise ValueError(f"image_metadata[{idx}] is missing required field '{field}'")
        if entry['arm'] not in VALID_ARMS:
            raise ValueError(
                f"image_metadata[{idx}] has arm={entry['arm']!r}; expected one of {VALID_ARMS}"
            )
        if entry['column_prefix'] not in VALID_PREFIXES:
            raise ValueError(
                f"image_metadata[{idx}] has column_prefix={entry['column_prefix']!r}; "
                f"expected one of {VALID_PREFIXES}"
            )
        rec = {
            'well': str(entry['well']),
            'site': int(entry['site']),
            'arm': str(entry['arm']),
            'channel': str(entry['channel']),
            'column_prefix': str(entry['column_prefix']),
            'filename': str(entry['filename']),
        }
        if entry.get('cycle') is not None:
            rec['cycle'] = int(entry['cycle'])
        if entry.get('frame_index') is not None:
            rec['frame_index'] = int(entry['frame_index'])
        if entry.get('original_path') is not None:
            rec['original_path'] = str(entry['original_path'])
        if entry.get('original_filename') is not None:
            rec['original_filename'] = str(entry['original_filename'])
        result['image_metadata'].append(rec)

    # Cycles: the caller states them explicitly. Cross-check against the
    # entries so a Groovy-side bug surfaces here rather than as silently wrong
    # column names downstream.
    entry_cycles = sorted({r['cycle'] for r in result['image_metadata'] if 'cycle' in r})
    if 'cycles' in metadata and metadata['cycles'] is not None:
        declared = sorted(int(c) for c in metadata['cycles'])
        if declared != entry_cycles:
            raise ValueError(
                f"Top-level 'cycles' {declared} does not match the distinct cycles "
                f"present in image_metadata {entry_cycles}"
            )
        result['cycles'] = declared
    elif entry_cycles:
        raise ValueError(
            f"image_metadata contains cycles {entry_cycles} but no top-level 'cycles' "
            "was provided - the Nextflow caller must state cycles explicitly"
        )
    if len(entry_cycles) == 1:
        result['cycle'] = entry_cycles[0]

    print(
        f"✓ Loaded {len(result['image_metadata'])} image_metadata entries; "
        f"cycles={result.get('cycles')}",
        file=sys.stderr,
    )
    return result


def collect_and_group_files(
    images_dir: str,
    include_illum_files: bool = False,
    illum_dir: Optional[str] = None,
    metadata_cycle: Optional[int] = None,
    metadata_json: Dict = None,
) -> Dict[Tuple, Dict]:
    """
    Group image_metadata entries by (plate, well, site) for CSV generation.

    Every entry's `filename` is trusted directly (see module docstring) - no
    directory glob, no regex filtering, no substring search. Optionally also
    collects illumination .npy files from `illum_dir`, matched by filename
    convention (illum files aren't part of image_metadata today).

    Returns:
        Dict mapping (plate, well, site) -> {
            'records': [{'path', 'channel', 'cycle', 'frame_index', 'column_prefix'}, ...],
            'illum': {channel: filename, ...} or {'_by_cycle': {cycle: {channel: filename}}},
        }
    """
    if not metadata_json:
        raise ValueError(
            "Metadata JSON is required but was not provided. "
            "Use --metadata-json to specify the metadata file."
        )
    if not os.path.isdir(images_dir):
        raise FileNotFoundError(f"Images directory not found: {images_dir}")

    plate = metadata_json['plate']
    grouped = {}

    for entry in metadata_json['image_metadata']:
        full_path = os.path.join(images_dir, entry['filename'])
        if not os.path.isfile(full_path):
            raise ValueError(
                f"File '{entry['filename']}' from metadata not found in {images_dir}"
            )
        key = (plate, entry['well'], entry['site'])
        grouped.setdefault(key, {'records': [], 'illum': {}})
        grouped[key]['records'].append({
            'path': entry['filename'],
            'channel': entry['channel'],
            'cycle': entry.get('cycle'),
            'frame_index': entry.get('frame_index'),
            'column_prefix': entry['column_prefix'],
        })

    print(f"✓ Grouped {len(grouped)} unique (plate, well, site) combinations", file=sys.stderr)

    # Collect illumination files if needed. These aren't part of image_metadata
    # (there's no per-image illumination-file metadata array today), so they're
    # still matched via directory glob + filename convention.
    if include_illum_files and illum_dir:
        if not os.path.isdir(illum_dir):
            raise FileNotFoundError(f"Illumination directory not found: {illum_dir}")

        illum_files = [
            f for f in os.listdir(illum_dir)
            if f.endswith('.npy') and os.path.isfile(os.path.join(illum_dir, f))
        ]
        if not illum_files:
            raise ValueError(f"No illumination files (*.npy) found in {illum_dir}")

        print(f"✓ Found {len(illum_files)} illumination file(s)", file=sys.stderr)

        illum_matched = 0
        for filename in illum_files:
            # Try cycle-based pattern first: Plate1_Cycle01_IllumChannelName.npy
            cycle_match = re.match(r'(.+?)_Cycle(\d+)_Illum(.+?)\.npy', filename)
            if cycle_match:
                illum_plate = cycle_match.group(1)
                file_cycle = int(cycle_match.group(2))
                channel = cycle_match.group(3)

                # If metadata_cycle is provided, only match that specific cycle
                if metadata_cycle is not None and file_cycle != metadata_cycle:
                    continue

                matched_this_file = False
                for (p, w, s) in grouped.keys():
                    if p == illum_plate:
                        grouped[(p, w, s)]['illum'].setdefault('_by_cycle', {})
                        grouped[(p, w, s)]['illum']['_by_cycle'].setdefault(file_cycle, {})
                        grouped[(p, w, s)]['illum']['_by_cycle'][file_cycle][channel] = filename
                        matched_this_file = True
                if matched_this_file:
                    illum_matched += 1
                continue

            # Non-cycle pattern: Plate1_IllumChannelName.npy
            match = re.match(r'(.+?)_Illum(.+?)\.npy', filename)
            if match:
                illum_plate = match.group(1)
                channel = match.group(2)
                matched_this_file = False
                for (p, w, s) in grouped.keys():
                    if p == illum_plate:
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
    include_illum_files: bool = False,
    range_skip: int = 1,
    has_cycles: bool = False,
    metadata_cycle: Optional[int] = None,
    metadata_json: Dict = None,
    cycle_metadata_name: str = "Cycle",
    staged_to_original: Dict = None,
    npy_original_dir: str = None,
) -> List[Dict]:
    """
    Generate CellProfiler load_data.csv rows from grouped file data.

    One column-naming rule covers every caller:
        name = f"{cycle_prefix}{column_prefix}{channel}"
        cycle_prefix = f"Cycle{cycle:02d}_" if (cycle is not None and >1 distinct
                                                 cycle across the whole plate) else ""
    `Frame_{name}` is emitted iff the record carries a `frame_index` (i.e. the
    source file is a multi-frame/multichannel file).
    """
    if not metadata_json:
        raise ValueError("Metadata JSON is required but was not provided")
    if not grouped:
        raise ValueError("No grouped files to generate CSV rows from")

    all_cycles = metadata_json.get('cycles') or []
    use_cycle_prefix = len(all_cycles) > 1
    has_cycle = 'cycle' in metadata_json or metadata_cycle is not None

    def _orig(filename):
        if not staged_to_original or not filename:
            return filename
        return staged_to_original.get(str(filename), filename)

    def _npy_orig(filename):
        if not npy_original_dir or not filename:
            return filename
        return f"{npy_original_dir}{filename}"

    # Apply subsampling per well: select every Nth site.
    wells_to_sites = {}
    for (plate, well, site) in grouped.keys():
        wells_to_sites.setdefault((plate, well), []).append(site)

    selected_keys = set()
    for (plate, well), sites in wells_to_sites.items():
        sorted_sites = sorted(sites)
        if len(sorted_sites) < range_skip:
            selected_sites = sorted_sites
        else:
            selected_sites = [site for i, site in enumerate(sorted_sites) if i % range_skip == 0]
        for site in selected_sites:
            selected_keys.add((plate, well, site))

    print(
        f"✓ Selected {len(selected_keys)} image(s) from {len(grouped)} total images "
        f"across {len(wells_to_sites)} well(s)",
        file=sys.stderr,
    )

    rows = []
    row_errors = []

    for (plate, well, site), file_data in sorted(grouped.items()):
        if (plate, well, site) not in selected_keys:
            continue

        try:
            row = {
                'Metadata_Plate': plate,
                'Metadata_Well': well,
                'Metadata_Site': site,
            }
            if has_cycles and has_cycle:
                cycle_col = f'Metadata_{cycle_metadata_name}'
                if 'cycle' in metadata_json:
                    row[cycle_col] = metadata_json['cycle']
                elif metadata_cycle is not None:
                    row[cycle_col] = metadata_cycle
                else:
                    raise ValueError(f"{cycle_col} required but not found in metadata JSON")

            records = file_data['records']
            if not records:
                raise ValueError(f"No image files for {plate}/{well}/Site{site}")

            illum_by_cycle = file_data['illum'].get('_by_cycle', {})
            illum_flat = {k: v for k, v in file_data['illum'].items() if not k.startswith('_')}
            missing_illum = []

            for rec in records:
                cycle = rec['cycle']
                cycle_prefix = f"Cycle{cycle:02d}_" if (cycle is not None and use_cycle_prefix) else ""
                name = f"{cycle_prefix}{rec['column_prefix']}{rec['channel']}"

                row[f'FileName_{name}'] = rec['path']
                row[f'FinalFileName_{name}'] = _orig(rec['path'])
                if rec['frame_index'] is not None:
                    row[f'Frame_{name}'] = rec['frame_index']

                if include_illum_files:
                    illum_fn = None
                    if cycle is not None and cycle in illum_by_cycle:
                        illum_fn = illum_by_cycle[cycle].get(rec['channel'])
                    if illum_fn is None:
                        illum_fn = illum_flat.get(rec['channel'])
                    if illum_fn is None:
                        missing_illum.append(f"{cycle_prefix}{rec['channel']}")
                    else:
                        illum_name = f"{cycle_prefix}Illum{rec['channel']}"
                        row[f'FileName_{illum_name}'] = illum_fn
                        row[f'FinalFileName_{illum_name}'] = _npy_orig(illum_fn)

            if missing_illum:
                print(
                    f"⚠ Missing illumination files for {sorted(set(missing_illum))} "
                    f"in {plate}/{well}/Site{site}",
                    file=sys.stderr,
                )

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
    """Write rows to CSV with Metadata_ columns first, then sorted FileName/Frame columns."""
    if not rows:
        raise ValueError("No rows to write - cannot create empty CSV")

    all_cols = set()
    for row in rows:
        all_cols.update(row.keys())

    actual_metadata_cols = sorted([c for c in all_cols if c.startswith('Metadata_')])
    file_cols = sorted([c for c in all_cols if not c.startswith('Metadata_')])
    fieldnames = actual_metadata_cols + file_cols

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
        '--include-illum-files',
        action='store_true',
        help='Collect illumination .npy files and emit FileName_Illum* columns (requires --illum-dir)'
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
        '--metadata-json',
        required=True,
        help='Path to JSON file with metadata. REQUIRED - all metadata must be in JSON.'
    )
    parser.add_argument(
        '--has-cycles',
        action='store_true',
        help='Data contains cycle information (for barcoding workflows) - controls '
             'whether a Metadata_Cycle column is emitted'
    )
    parser.add_argument(
        '--cycle',
        type=int,
        help='Cycle number for single-cycle processing - overrides JSON metadata if provided'
    )
    parser.add_argument(
        '--cycle-metadata-name',
        default='Cycle',
        help='Name for the cycle metadata column (default: "Cycle", e.g., "Metadata_Cycle")'
    )
    parser.add_argument(
        '--outdir',
        default='',
        help='Pipeline output directory (used to construct durable paths for illumination .npy files)'
    )

    args = parser.parse_args()

    if args.include_illum_files and not args.illum_dir:
        parser.error("--illum-dir required when --include-illum-files is set")

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"CellProfiler load_data.csv Generator", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"Images directory: {args.images_dir}", file=sys.stderr)
    if args.illum_dir:
        print(f"Illumination directory: {args.illum_dir}", file=sys.stderr)
    if args.range_skip > 1:
        print(f"Subsampling: every {args.range_skip} sites", file=sys.stderr)
    print(f"Output file: {args.output}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    try:
        metadata_json = load_metadata_json(args.metadata_json)
        print(f"✓ Loaded metadata from {args.metadata_json}", file=sys.stderr)
        print(f"  - Plate: {metadata_json['plate']}", file=sys.stderr)
        print(f"  - Image metadata: {len(metadata_json['image_metadata'])} entries", file=sys.stderr)
        if 'cycle' in metadata_json:
            print(f"  - Cycle: {metadata_json['cycle']}", file=sys.stderr)
        if 'cycles' in metadata_json:
            print(f"  - Cycles: {metadata_json['cycles']}", file=sys.stderr)

        metadata_cycle = args.cycle if args.cycle else metadata_json.get('cycle')

        print(f"\nStep 1/3: Collecting and grouping files...", file=sys.stderr)
        grouped = collect_and_group_files(
            images_dir=args.images_dir,
            include_illum_files=args.include_illum_files,
            illum_dir=args.illum_dir,
            metadata_cycle=metadata_cycle,
            metadata_json=metadata_json,
        )

        # Build staged-path -> original-path mapping from image_metadata entries.
        # Keyed by the full (already-disambiguated) 'filename', not its basename:
        # different physical files can share a basename (e.g. the same channel
        # index reused across different acquisition-cycle subfolders), and a
        # basename-only key would collapse them onto whichever entry happened
        # to be inserted last.
        staged_to_original = {}
        for entry in metadata_json.get('image_metadata', []):
            orig = entry.get('original_path')
            filename = entry.get('filename')
            if orig and filename:
                staged_to_original[str(filename)] = orig

        # Construct npy illumination original directory if outdir is provided
        npy_original_dir = None
        if args.outdir:
            batch = metadata_json.get('batch', '')
            plate = metadata_json.get('plate', '')
            if batch and plate:
                npy_original_dir = f"{args.outdir}/images/{batch}/illum/{plate}/"

        print(f"\nStep 2/3: Generating CSV rows...", file=sys.stderr)
        rows = generate_csv_rows(
            grouped,
            include_illum_files=args.include_illum_files,
            range_skip=args.range_skip,
            has_cycles=args.has_cycles,
            metadata_cycle=metadata_cycle,
            metadata_json=metadata_json,
            cycle_metadata_name=args.cycle_metadata_name,
            staged_to_original=staged_to_original,
            npy_original_dir=npy_original_dir,
        )

        print(f"\nStep 3/3: Writing output files...", file=sys.stderr)
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
