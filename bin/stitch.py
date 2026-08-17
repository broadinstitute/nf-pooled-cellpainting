#!/usr/bin/env python
"""
Stitch a well's illumination-corrected per-site images into one full-well image
per channel (painting) or per cycle+channel (barcoding, or multicycle painting),
using ashlar.

Design philosophy:
- Read whatever Nextflow has already staged locally for one well (a flat directory
  of per-site TIFFs - no shared-filesystem path assumptions, portable across executors).
- Microscopes (Phenix/Operetta-style instruments in particular) acquire round-well
  sites in a center-first, non-raster physical order. ashlar's `fileseries` reader
  expects tiles numbered in flat sequential raster order (row-major, given a
  width x height grid) and has no built-in knowledge of that acquisition order. So
  before invoking ashlar, every real site is copied/renamed into a raster-ordered
  temp directory (series = row * columns + col), and any empty grid corners (round
  wells never fill a full rectangle) are filled with synthetic low-level noise -
  this whole remapping step is the reason this script exists.
- The site->grid-position layouts for known round-well geometries (im_per_well_dict,
  phenix_im_per_well_dict) live in assets/stitchcrop/well_site_layouts.json, shared
  with the legacy Fiji-based stitcher (assets/stitchcrop/stitch_crop.env_master.py)
  so both scripts read the same data from one place.
- ashlar registers from an implicit reference channel and applies that registration
  to every channel in the same fileseries, so this script makes ONE ashlar call per
  well (painting) or per well x cycle (barcoding), covering all channels at once via
  ashlar's own `{channel}` wildcard - not one call per channel.

Known limitation, called out explicitly rather than silently: the square-grid
(non-round) position mapping below is NEW code with no legacy precedent - the old
Fiji script delegated square-grid tiling entirely to ImageJ's built-in
"Grid/Collection stitching" plugin, which has no equivalent pure-Python
implementation to port. Only "Grid: snake by rows" is currently supported for
square grids; anything else raises an error rather than guessing.

Usage:
    stitch.py \\
        --input-dir images/ --output-dir stitched_images/ --downsampled-dir downsampled_images/ \\
        --arm painting --round-or-square round --phenix true --imperwell 80 \\
        --quarter-if-round true --overlap-pct 10 --rows 2 --columns 2 \\
        --stitchorder "Grid: snake by rows" \\
        --compress true --channame DNA --first-site-index 1
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_WELL_SITE_LAYOUTS_JSON = SCRIPT_DIR.parent / "assets" / "stitchcrop" / "well_site_layouts.json"

# Painting images carry a literal "Corr" prefix before the bare channel name
# (e.g. "..._Site_1_CorrDNA.tiff"); barcoding images don't (e.g. "..._Cycle01_DNA.tiff").
PAINTING_FILENAME_RE = re.compile(
    r"^Plate_(?P<plate>.+)_Well_(?P<well>.+)_Site_(?P<site>\d+)_Corr(?P<channel>.+)\.tiff?$"
)
BARCODING_FILENAME_RE = re.compile(
    r"^Plate_(?P<plate>.+)_Well_(?P<well>.+)_Site_(?P<site>\d+)_(?P<cycle>Cycle\d+)_(?P<channel>.+)\.tiff?$"
)

# 3-digit zero-padded series numbering for ashlar's fileseries pattern - large
# non-round grids (see im_per_well_dict, e.g. "1396") can need more than 2 digits.
SERIES_DIGITS = 3
MAX_SERIES = 10**SERIES_DIGITS - 1

SHORT_CODES = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def load_well_site_layouts(path: Path) -> Tuple[Dict[str, List[int]], Dict[str, List[List]]]:
    """Load the shared site-position layouts (see module docstring)."""
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading well site layouts from {path}: {e}")
        sys.exit(1)
    return data["im_per_well_dict"], data["phenix_im_per_well_dict"]


def parse_filenames(input_dir: Path, arm: str) -> List[dict]:
    """Parse every staged tiff filename into plate/well/site/[cycle/]channel/path."""
    pattern = BARCODING_FILENAME_RE if arm == "barcoding" else PAINTING_FILENAME_RE
    parsed = []
    for f in sorted(input_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() not in (".tif", ".tiff"):
            continue
        m = pattern.match(f.name)
        if not m:
            print(f"WARNING: filename doesn't match expected {arm} pattern, skipping: {f.name}")
            continue
        entry = m.groupdict()
        entry["site"] = int(entry["site"])
        entry["path"] = f
        parsed.append(entry)
    if not parsed:
        print(f"Error: no images matched the expected {arm} filename pattern in {input_dir}")
        sys.exit(1)
    return parsed


def normalize_site(raw_site: int, first_site_index: int) -> int:
    """Map the observed site numbering onto the layout dicts' 1-indexed convention."""
    return raw_site - first_site_index + 1


def build_position_dict(
    round_or_square: str,
    phenix: bool,
    imperwell: str,
    rows: str,
    columns: str,
    stitchorder: str,
    im_per_well_dict: Dict[str, List[int]],
    phenix_im_per_well_dict: Dict[str, List[List]],
) -> Tuple[Dict[Tuple[int, int], int], int, int]:
    """
    Returns (position_dict, grid_columns, grid_rows), where position_dict maps
    (col, row) grid position -> true 1-indexed site number for every filled position.
    """
    if round_or_square == "round":
        if phenix:
            row_pattern = phenix_im_per_well_dict.get(str(imperwell))
            if row_pattern is None:
                print(f"Error: {imperwell} images/well for a round Phenix well is not currently supported")
                sys.exit(1)
            grid_rows = len(row_pattern)
            grid_columns = len(row_pattern[0])
            position_dict = {}
            for row_idx, row in enumerate(row_pattern):
                for col_idx, site in enumerate(row):
                    if site != "":
                        position_dict[(col_idx, row_idx)] = int(site)
            return position_dict, grid_columns, grid_rows

        # Round, non-Phenix: snake back and forth, each row centered under the widest row.
        row_widths = im_per_well_dict.get(str(imperwell))
        if row_widths is None:
            print(f"Error: {imperwell} images/well for a round well is not currently supported")
            sys.exit(1)
        grid_rows = len(row_widths)
        grid_columns = max(row_widths)
        position_dict = {}
        count = 1  # legacy layout dicts are 1-indexed
        for row_idx, row_width in enumerate(row_widths):
            left_pos = (grid_columns - row_width) // 2
            if row_idx % 2 == 0:
                for col_offset in range(row_width):
                    position_dict[(left_pos + col_offset, row_idx)] = count
                    count += 1
            else:
                right_pos = left_pos + row_width - 1
                for col_offset in range(row_width):
                    position_dict[(right_pos - col_offset, row_idx)] = count
                    count += 1
        return position_dict, grid_columns, grid_rows

    # Square grid: NEW logic, no legacy precedent (see module docstring). Only the
    # pipeline's default stitchorder is supported so far.
    if stitchorder != "Grid: snake by rows":
        print(
            f"Error: square-grid stitchorder '{stitchorder}' is not supported by bin/stitch.py yet "
            "(only 'Grid: snake by rows' is implemented - this path has no legacy precedent to port, "
            "unlike the round-well cases; extend build_position_dict() to add it)"
        )
        sys.exit(1)
    grid_rows = int(rows)
    grid_columns = int(columns)
    position_dict = {}
    count = 1
    for row_idx in range(grid_rows):
        col_range = range(grid_columns) if row_idx % 2 == 0 else reversed(range(grid_columns))
        for col_idx in col_range:
            position_dict[(col_idx, row_idx)] = count
            count += 1
    return position_dict, grid_columns, grid_rows


def build_chandict(channels: List[str]) -> Dict[str, str]:
    """Assign each distinct channel a short single-character code, sorted deterministically."""
    unique_channels = sorted(set(channels))
    if len(unique_channels) > len(SHORT_CODES):
        print(f"Error: {len(unique_channels)} distinct channels found, more than the {len(SHORT_CODES)} available codes")
        sys.exit(1)
    return {ch: SHORT_CODES[i] for i, ch in enumerate(unique_channels)}


def synthesize_noise(shape: Tuple[int, ...], dtype: np.dtype, high: int = 25) -> np.ndarray:
    """Low-amplitude noise, kept below the real camera noise floor, for empty round-well corners."""
    return np.random.randint(0, high, size=shape).astype(dtype)


def stage_channel_set(
    images: List[dict],
    position_dict: Dict[Tuple[int, int], int],
    grid_columns: int,
    grid_rows: int,
    first_site_index: int,
    chandict: Dict[str, str],
    channame: str,
    arm: str,
    work_dir: Path,
) -> None:
    """
    Populate work_dir with raster-ordered, ashlar-ready files for every channel in
    chandict: {series:03d}_Corr{code}.tiff (painting) or {series:03d}_{code}.tiff
    (barcoding). Real files are copied in for occupied grid positions; synthetic
    noise is written for empty ones (round wells only).
    """
    total_positions = grid_rows * grid_columns
    if total_positions - 1 > MAX_SERIES:
        print(
            f"Error: grid has {total_positions} positions, which needs more than {SERIES_DIGITS} "
            f"digits of series numbering ({MAX_SERIES + 1} max) - increase SERIES_DIGITS in bin/stitch.py"
        )
        sys.exit(1)

    by_site_channel = {}
    for entry in images:
        norm_site = normalize_site(entry["site"], first_site_index)
        by_site_channel[(norm_site, entry["channel"])] = entry["path"]

    # Prefer the channame-matching image for shape/dtype detection (matches the legacy
    # script's use of channame as a reference channel); fall back to any real image.
    reference_path = next((e["path"] for e in images if channame in e["channel"]), None)
    if reference_path is None:
        reference_path = images[0]["path"]
    with Image.open(reference_path) as im:
        sample_array = np.array(im)
    shape, dtype = sample_array.shape, sample_array.dtype

    corr_infix = "Corr" if arm == "painting" else ""
    for channel, code in chandict.items():
        for row in range(grid_rows):
            for col in range(grid_columns):
                series = row * grid_columns + col
                dest = work_dir / f"{series:0{SERIES_DIGITS}d}_{corr_infix}{code}.tiff"
                true_site = position_dict.get((col, row))
                src = by_site_channel.get((true_site, channel)) if true_site is not None else None
                if src is not None:
                    shutil.copy(src, dest)
                else:
                    noise = synthesize_noise(shape, dtype)
                    Image.fromarray(noise).save(dest)


def run_ashlar(
    work_dir: Path,
    grid_columns: int,
    grid_rows: int,
    overlap_pct: float,
    arm: str,
    out_dir: Path,
    out_prefix: str,
) -> None:
    """One ashlar call over every channel staged in work_dir - see module docstring."""
    overlap_frac = float(overlap_pct) / 100.0
    corr_infix = "Corr" if arm == "painting" else ""
    pattern = f"{{series:{SERIES_DIGITS}}}_{corr_infix}{{channel:1}}.tiff"
    fileseries_url = f"fileseries|{work_dir}|pattern={pattern}|overlap={overlap_frac}|width={grid_columns}|height={grid_rows}"
    out_template = str(out_dir / f"{out_prefix}{corr_infix}{{channel}}.tif")
    cmd = ["ashlar", fileseries_url, "-o", out_template]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def write_downsampled(src: Path, dest: Path, factor: int = 10) -> None:
    """Write a 1/factor-scaled copy for QC montage purposes."""
    with Image.open(src) as im:
        arr = np.array(im)
    small = arr[::factor, ::factor]
    Image.fromarray(small).save(dest)


def stitch_one_channel_set(
    images: List[dict],
    plate: str,
    well: str,
    cycle: Optional[str],
    args: argparse.Namespace,
    im_per_well_dict: Dict[str, List[int]],
    phenix_im_per_well_dict: Dict[str, List[List]],
) -> None:
    """Stitch one well x cycle - Nextflow always stages exactly one cycle's images per invocation."""
    position_dict, grid_columns, grid_rows = build_position_dict(
        args.round_or_square,
        args.phenix.lower() == "true",
        args.imperwell,
        args.rows,
        args.columns,
        args.stitchorder,
        im_per_well_dict,
        phenix_im_per_well_dict,
    )
    chandict = build_chandict([e["channel"] for e in images])
    print(f"{well}{' ' + cycle if cycle else ''}: grid {grid_columns}x{grid_rows}, channels {chandict}")

    with tempfile.TemporaryDirectory(prefix="stitch_") as tmp:
        work_dir = Path(tmp) / "renamed"
        work_dir.mkdir()
        ashlar_out_dir = Path(tmp) / "ashlar_out"
        ashlar_out_dir.mkdir()

        stage_channel_set(
            images, position_dict, grid_columns, grid_rows,
            int(args.first_site_index), chandict, args.channame, args.arm, work_dir,
        )

        out_prefix = "stitched_"
        run_ashlar(work_dir, grid_columns, grid_rows, float(args.overlap_pct), args.arm, ashlar_out_dir, out_prefix)

        corr_infix = "Corr" if args.arm == "painting" else ""
        inv_chandict = {code: ch for ch, code in chandict.items()}
        # ashlar's fileseries reader assigns each channel an internal 0-based index
        # by sorting the parsed {channel} field values it found on disk (see
        # FileSeriesMetadata._enumerate_tiles: `channel_map = dict(enumerate(sorted(channels)))`)
        # and substitutes THAT index - not the literal parsed value - into the `-o`
        # template's {channel} placeholder. So output files are named by rank-in-sorted-order
        # of our chandict codes, not by the codes themselves.
        sorted_codes = sorted(chandict.values())
        for ashlar_channel_index, code in enumerate(sorted_codes):
            channel = inv_chandict[code]
            ashlar_output = ashlar_out_dir / f"{out_prefix}{corr_infix}{ashlar_channel_index}.tif"
            if not ashlar_output.exists():
                print(f"WARNING: expected ashlar output not found: {ashlar_output}")
                continue

            # painting:  Stitched_{cycle}_Corr{channel}.tiff
            # barcoding: Stitched_{cycle}_{channel}.tiff
            cycle_infix = f"{cycle}_" if cycle else ""
            corr_infix = "Corr" if args.arm == "painting" else ""
            final_name = f"Plate_{plate}_Well_{well}_Site_1_Stitched_{cycle_infix}{corr_infix}{channel}.tiff"
            final_path = args.output_dir / final_name

            save_kwargs = {"compression": "tiff_deflate"} if args.compress.lower() == "true" else {}
            with Image.open(ashlar_output) as im:
                im.save(final_path, **save_kwargs)

            write_downsampled(final_path, args.downsampled_dir / final_name)
            print(f"  wrote {final_path.name}")


def main(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.downsampled_dir.mkdir(parents=True, exist_ok=True)

    im_per_well_dict, phenix_im_per_well_dict = load_well_site_layouts(args.well_site_layouts_json)
    parsed = parse_filenames(args.input_dir, args.arm)

    plate = parsed[0]["plate"]
    well = parsed[0]["well"]

    # Nextflow now pre-splits every STITCH invocation to exactly one (well, cycle) -
    # for both arms - so there's never more than one cycle's worth of images staged
    # here, and this just needs to determine the cycle tag used in output filenames.
    if args.arm == "barcoding":
        cycles_found = sorted(set(e["cycle"] for e in parsed))
        if len(cycles_found) > 1:
            print(f"Error: expected exactly one cycle per STITCH invocation (Nextflow pre-splits by well+cycle), found {cycles_found}")
            sys.exit(1)
        cycle_tag = cycles_found[0]
    else:
        if not args.cycle:
            print("Error: --cycle is required for --arm painting (Nextflow must supply the well's resolved cycle)")
            sys.exit(1)
        cycle_tag = f"Cycle{int(args.cycle):02d}"

    stitch_one_channel_set(parsed, plate, well, cycle_tag, args, im_per_well_dict, phenix_im_per_well_dict)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory of staged per-site illumination-corrected TIFFs for one well")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory to write stitched full-well TIFFs to")
    parser.add_argument("--downsampled-dir", type=Path, required=True, help="Directory to write 10x-downsampled copies to")
    parser.add_argument("--arm", required=True, choices=["painting", "barcoding"])
    parser.add_argument("--round-or-square", required=True, choices=["round", "square"])
    parser.add_argument("--quarter-if-round", default="false", help="Accepted for interface parity with the legacy Fiji script; unused here - imperwell already distinguishes a full round well from a single quarter of one")
    parser.add_argument("--overlap-pct", required=True)
    parser.add_argument("--imperwell", default="")
    parser.add_argument("--rows", default="")
    parser.add_argument("--columns", default="")
    parser.add_argument("--stitchorder", default="Grid: snake by rows")
    parser.add_argument("--compress", default="true")
    parser.add_argument("--phenix", default="false")
    parser.add_argument("--channame", default="DNA", help="Reference channel substring used to pick a representative image for shape/dtype detection")
    parser.add_argument("--first-site-index", default="0")
    parser.add_argument("--well-site-layouts-json", type=Path, default=DEFAULT_WELL_SITE_LAYOUTS_JSON)
    parser.add_argument("--cycle", default=None, help="Cycle number for this invocation (painting only - "
        "barcoding parses cycle directly from filenames). Required when --arm painting, since painting "
        "filenames never carry a cycle token.")

    parsed_args = parser.parse_args()
    main(parsed_args)
