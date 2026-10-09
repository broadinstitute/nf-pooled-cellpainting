#!/usr/bin/env python
"""
Crop a full-well stitched image into a tileperside x tileperside grid of
final_tile_size x final_tile_size pixel tiles, one channel file at a time.

Design philosophy:
- Ported from the tiling/naming logic in assets/stitchcrop/stitch_crop.env_master.py's
  apply_stitching_per_well_section_and_channel() (the simple, non-quartered case -
  quartering a round well before cropping is Fiji-Grid/Stitch-specific legacy
  behavior with no equivalent here, matching this pipeline's existing precedent of
  not chasing full FIJI parity in the new stitch/crop scripts).
- Each channel's stitched TIFF is loaded, tiled, and its tiles saved, one channel
  at a time - this script never holds more than one full-well image in memory,
  the same reasoning as bin/align_combined.py's memory fix.
- Tile numbering matches the legacy script's convention exactly: column-major
  (all rows of column 0, then all rows of column 1, ...), starting from
  --first-site-index instead of a hardcoded 1, so cropped site numbers line up
  with whatever indexing convention (0- or 1-based) this well's original
  per-site acquisition used.
- If the stitched image is smaller than tileperside * final_tile_size in either
  dimension, it's zero-padded (top-left anchored) first, matching the legacy
  script's "Canvas Size... position=Top-Left zero" step - this guarantees every
  tile is exactly final_tile_size x final_tile_size, which downstream per-tile
  CellProfiler analysis assumes.

Usage:
    crop.py \\
        --input-dir images/ --output-dir cropped_images/ \\
        --tileperside 10 --final-tile-size 800 \\
        --compress true --phenix false --channame DNA --first-site-index 1
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Full-well stitched mosaics routinely exceed PIL's default decompression-bomb
# threshold (~89.5 megapixels) - these are legitimate large scientific images,
# not the malicious images that check guards against.
Image.MAX_IMAGE_PIXELS = None

# Matches STITCH's output naming (bin/stitch.py's stitch_one_channel_set): the
# real site number here is always 1 (a stitched full-well image has none of its
# own), everything after "_Stitched_" (channel, and cycle infix if present) is
# carried through verbatim into each cropped tile's filename.
STITCHED_FILENAME_RE = re.compile(
    r"^Plate_(?P<plate>.+)_Well_(?P<well>.+)_Site_(?P<site>\d+)_Stitched_(?P<suffix>.+)\.tiff?$"
)


def load_array(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.array(im)


def save_array(arr: np.ndarray, dtype: np.dtype, path: Path, compress: str) -> None:
    save_kwargs = {"compression": "tiff_deflate"} if compress.lower() == "true" else {}
    Image.fromarray(arr.astype(dtype)).save(path, **save_kwargs)


def pad_to_grid(arr: np.ndarray, grid_rows: int, grid_cols: int) -> np.ndarray:
    """Zero-pad (top-left anchored) so every tile in the grid is a full tile."""
    pad_rows = max(0, grid_rows - arr.shape[0])
    pad_cols = max(0, grid_cols - arr.shape[1])
    if pad_rows == 0 and pad_cols == 0:
        return arr
    return np.pad(arr, ((0, pad_rows), (0, pad_cols)), mode="constant", constant_values=0)


def crop_one_file(
    path: Path,
    output_dir: Path,
    tileperside: int,
    final_tile_size: int,
    first_site_index: int,
    compress: str,
) -> None:
    m = STITCHED_FILENAME_RE.match(path.name)
    if not m:
        print(f"WARNING: filename doesn't match expected stitched-image pattern, skipping: {path.name}")
        return
    plate, well, suffix = m["plate"], m["well"], m["suffix"]

    arr = load_array(path)
    arr = pad_to_grid(arr, tileperside * final_tile_size, tileperside * final_tile_size)

    for eachxtile in range(tileperside):
        for eachytile in range(tileperside):
            tile_num = first_site_index + eachxtile * tileperside + eachytile
            y0, y1 = eachytile * final_tile_size, (eachytile + 1) * final_tile_size
            x0, x1 = eachxtile * final_tile_size, (eachxtile + 1) * final_tile_size
            tile = arr[y0:y1, x0:x1]
            out_name = f"Plate_{plate}_Well_{well}_Site_{tile_num}_{suffix}.tiff"
            save_array(tile, arr.dtype, output_dir / out_name, compress)

    print(f"  cropped {path.name} into {tileperside * tileperside} tiles")


def main(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)

    tileperside = int(args.tileperside)
    final_tile_size = int(args.final_tile_size)
    first_site_index = int(args.first_site_index)

    paths = sorted(p for p in args.input_dir.iterdir() if p.is_file() and p.suffix.lower() in (".tif", ".tiff"))
    if not paths:
        print(f"Error: no images found in {args.input_dir}")
        sys.exit(1)

    for path in paths:
        crop_one_file(path, args.output_dir, tileperside, final_tile_size, first_site_index, args.compress)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory of staged full-well stitched TIFFs for one well (one file per channel/cycle)")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory to write cropped per-tile TIFFs to")
    parser.add_argument("--tileperside", required=True, help="Number of tiles per side of the square crop grid")
    parser.add_argument("--final-tile-size", required=True, help="Pixel size (both dimensions) of each cropped tile")
    parser.add_argument("--compress", default="true")
    parser.add_argument("--phenix", default="false", help="Accepted for interface parity with the legacy Fiji script; unused here - tile numbering is a plain column-major grid regardless of acquisition geometry, since cropping happens after stitching")
    parser.add_argument("--channame", default="DNA", help="Accepted for interface parity with the legacy Fiji script; unused here - every channel file is cropped independently with the same grid")
    parser.add_argument("--first-site-index", default="0", help="Starting tile number (matches whatever 0- or 1-based site indexing convention this well's original acquisition used)")

    parsed_args = parser.parse_args()
    main(parsed_args)
