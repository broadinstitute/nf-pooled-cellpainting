#!/usr/bin/env python
"""
Align cycle N's images to cycle 1 using phase cross-correlation on a reference
channel (DNA/DAPI), then apply that one shift to every channel in cycle N.

Design philosophy:
- Shared by both arms (barcoding always has multiple cycles; painting only when
  painting_multicycle is enabled) - this script doesn't care which arm it's
  running for, it just groups whatever it's given by the `cycle` field already
  resolved upstream (parsed from filenames for barcoding, looked up from a
  channel->cycle dictionary for painting - see bin/stitch.py).
- If only one cycle is present (painting's normal, non-multicycle case), every
  image is passed through unchanged - no registration needed, no Nextflow-level
  conditional required to skip this module for single-cycle wells.
- Stage drift between imaging rounds is a single rigid translation of the whole
  field of view, so one phase_cross_correlation call per cycle (using each
  cycle's reference/DNA channel) is enough - that one shift is then applied
  uniformly to every channel acquired in that cycle.

Usage:
    align_intraarm.py \\
        --images-dir images/ --metadata-json metadata.json --output-dir . \\
        --channame DNA --shift-threshold 10 --corr-threshold 0.1
"""

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image
from scipy.ndimage import shift as ndi_shift
from skimage.registration import phase_cross_correlation


def load_metadata(path: Path) -> List[dict]:
    with open(path) as f:
        return json.load(f)


def group_by_cycle(image_metas: List[dict]) -> Dict[Optional[int], List[dict]]:
    groups: Dict[Optional[int], List[dict]] = {}
    for entry in image_metas:
        groups.setdefault(entry.get("cycle"), []).append(entry)
    return groups


def find_reference_image(entries: List[dict], channame: str) -> Optional[dict]:
    matches = sorted((e for e in entries if channame in e["channel"]), key=lambda e: e["filename"])
    if not matches:
        return None
    if len(matches) > 1:
        print(f"WARNING: {len(matches)} channels matched '{channame}', using {matches[0]['channel']}")
    return matches[0]


def load_array(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.array(im)


def save_array(arr: np.ndarray, dtype: np.dtype, path: Path) -> None:
    Image.fromarray(arr.astype(dtype)).save(path)


def downsample(arr: np.ndarray, factor: int = 10) -> np.ndarray:
    """Stride-based Nx downsample - same approach as bin/stitch.py's write_downsampled."""
    return arr[::factor, ::factor]


def normalize_to_uint8(arr: np.ndarray) -> np.ndarray:
    """Simple min-max normalization for QC display purposes only (not for analysis)."""
    arr = arr.astype(np.float64)
    lo, hi = arr.min(), arr.max()
    if hi > lo:
        arr = (arr - lo) / (hi - lo)
    else:
        arr = np.zeros_like(arr)
    return (arr * 255).astype(np.uint8)


def save_overlay(reference_arr: np.ndarray, moving_arr: np.ndarray, path: Path, factor: int = 10) -> None:
    """
    QC overlay so a biologist can eyeball alignment quality: the reference image in
    pink/magenta (R+B channels), the post-alignment moving image in green. Correctly
    aligned content reads neutral/white; misalignment shows visible magenta/green
    fringing. Downsampled 10x, same convention as the pipeline's other QC images.
    """
    ref_small = normalize_to_uint8(downsample(reference_arr, factor))
    mov_small = normalize_to_uint8(downsample(moving_arr, factor))
    # Guard against off-by-one shape mismatches between the two downsampled arrays.
    h = min(ref_small.shape[0], mov_small.shape[0])
    w = min(ref_small.shape[1], mov_small.shape[1])
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[..., 0] = ref_small[:h, :w]  # R (pink/magenta = reference)
    rgb[..., 1] = mov_small[:h, :w]  # G (moving, post-alignment)
    rgb[..., 2] = ref_small[:h, :w]  # B (pink/magenta = reference)
    Image.fromarray(rgb, mode="RGB").save(path)


def crop_to_shape(arr: np.ndarray, shape: tuple) -> np.ndarray:
    """Guard against off-by-one canvas-size mismatches across independently-stitched cycles."""
    h, w = shape
    return arr[:h, :w]


def copy_unchanged(entries: List[dict], images_dir: Path, output_dir: Path, common_shape: Optional[tuple] = None) -> None:
    for entry in entries:
        src = images_dir / entry["filename"]
        if common_shape is None:
            shutil.copy(src, output_dir / entry["filename"])
        else:
            arr = load_array(src)
            save_array(crop_to_shape(arr, common_shape), arr.dtype, output_dir / entry["filename"])


def align_cycle(
    entries: List[dict],
    reference_entries: List[dict],
    images_dir: Path,
    output_dir: Path,
    channame: str,
    common_shape: tuple,
) -> dict:
    """Align one non-reference cycle's images to the reference cycle. Returns a stats row."""
    ref_entry = find_reference_image(reference_entries, channame)
    moving_ref_entry = find_reference_image(entries, channame)
    if ref_entry is None or moving_ref_entry is None:
        print(f"Error: could not find a '{channame}' reference channel for cycle alignment")
        sys.exit(1)

    # Cycles are stitched independently (one ashlar call per cycle), so their mosaic
    # canvas sizes can differ by a few pixels - crop to the shape shared by every
    # cycle in this well before comparing/shifting, so all cycles' final outputs
    # end up the same size (required for downstream ALIGN_COMBINED/CROP).
    reference_array = crop_to_shape(load_array(images_dir / ref_entry["filename"]), common_shape)
    moving_array = crop_to_shape(load_array(images_dir / moving_ref_entry["filename"]), common_shape)

    # shift = translation required to register moving_array with reference_array
    # (see skimage.registration.phase_cross_correlation docs) - apply as-is via
    # scipy.ndimage.shift, do not negate.
    shift, error, diffphase = phase_cross_correlation(reference_array, moving_array)

    aligned_reference_channel = None
    for entry in entries:
        arr = crop_to_shape(load_array(images_dir / entry["filename"]), common_shape)
        shifted = ndi_shift(arr, shift, mode="constant", cval=0)
        save_array(shifted, arr.dtype, output_dir / entry["filename"])
        if entry is moving_ref_entry:
            aligned_reference_channel = shifted

    cycle = entries[0].get("cycle")
    overlay_path = output_dir / f"AlignIntraArm_QC_Cycle{cycle:02d}.png"
    save_overlay(reference_array, aligned_reference_channel, overlay_path)
    print(f"  wrote {overlay_path.name}")

    return {
        "cycle": cycle,
        "shift_row": shift[0],
        "shift_col": shift[1],
        "error": error,
        "diffphase": diffphase,
    }


def main(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    image_metas = load_metadata(args.metadata_json)
    groups = group_by_cycle(image_metas)

    distinct_cycles = sorted(c for c in groups if c is not None)

    if len(distinct_cycles) <= 1:
        # Single cycle (or no cycle info at all) - nothing to register, pass through unchanged.
        print("Only one cycle present - no-op, copying images through unchanged")
        for entries in groups.values():
            copy_unchanged(entries, args.images_dir, args.output_dir)
        return

    reference_cycle = distinct_cycles[0]
    reference_entries = groups[reference_cycle]
    print(f"Aligning cycles {distinct_cycles} to reference cycle {reference_cycle}")

    # Each cycle is stitched independently (one ashlar call per cycle), so mosaic
    # canvas sizes can differ by a few pixels across cycles even for the same well.
    # Every channel within one cycle shares the same shape (one ashlar call covers
    # all of a cycle's channels), so one reference-channel image per cycle is
    # enough to determine the common shape every cycle's output must be cropped to.
    cycle_shapes = []
    for cycle in distinct_cycles:
        ref_entry = find_reference_image(groups[cycle], args.channame)
        if ref_entry is None:
            print(f"Error: could not find a '{args.channame}' reference channel in cycle {cycle}")
            sys.exit(1)
        cycle_shapes.append(load_array(args.images_dir / ref_entry["filename"]).shape)
    common_shape = (min(s[0] for s in cycle_shapes), min(s[1] for s in cycle_shapes))

    stats_rows = []
    for cycle in distinct_cycles:
        entries = groups[cycle]
        if cycle == reference_cycle:
            copy_unchanged(entries, args.images_dir, args.output_dir, common_shape)
            continue
        stats_rows.append(align_cycle(entries, reference_entries, args.images_dir, args.output_dir, args.channame, common_shape))
        print(f"  cycle {cycle}: shift={stats_rows[-1]['shift_row']:.3f},{stats_rows[-1]['shift_col']:.3f} error={stats_rows[-1]['error']:.4f}")

    if stats_rows:
        stats_path = args.output_dir / "AlignIntraArm_stats.csv"
        with open(stats_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["cycle", "shift_row", "shift_col", "error", "diffphase", "shift_threshold", "corr_threshold"]
            )
            writer.writeheader()
            for row in stats_rows:
                row = dict(row)
                row["shift_threshold"] = args.shift_threshold
                row["corr_threshold"] = args.corr_threshold
                writer.writerow(row)
        print(f"Wrote {stats_path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--metadata-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--channame", default="DNA", help="Reference channel substring used to identify the registration channel within each cycle")
    parser.add_argument("--shift-threshold", default="0", help="Recorded in the stats CSV for later QC review; not enforced by this script")
    parser.add_argument("--corr-threshold", default="0", help="Recorded in the stats CSV for later QC review; not enforced by this script")

    parsed_args = parser.parse_args()
    main(parsed_args)
