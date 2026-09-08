#!/usr/bin/env python
"""
Scale painting and barcoding images to matching physical pixel size, then register
painting to barcoding using phase cross-correlation on their DNA/DAPI reference
channels, applying one shift to every painting image.

Design philosophy:
- Barcoding cycle 1's reference channel is the fixed anchor for the whole well -
  barcoding images (all cycles - they were already mutually aligned to barcoding
  cycle 1 by ALIGN_INTRAARM_BARCODING) are scaled here but never shifted.
- Painting (all cycles - already mutually aligned to each other by
  ALIGN_INTRAARM_PAINTING if painting_multicycle) gets ONE shift computed from a
  single representative cycle's reference channel against barcoding cycle 1, then
  that same shift is applied uniformly to every painting image regardless of cycle.
- Scaling happens here (not in bin/stitch.py) specifically because this is the one
  place both arms need to be compared - scaling per arm at stitch time would only
  be useful for this same comparison, so it's centralized here instead.
- Same phase_cross_correlation + scipy.ndimage.shift approach as bin/align_intraarm.py
  (see that script for the shift-direction rationale), just registering across arms
  instead of across cycles within one arm.

Usage:
    align_combined.py \\
        --painting-images-dir images/painting/ --barcoding-images-dir images/barcoding/ \\
        --metadata-json metadata.json --output-dir . \\
        --painting-output-dir aligned_painting/ --barcoding-output-dir aligned_barcoding/ \\
        --painting-scalingstring 1 --barcoding-scalingstring 1.99 \\
        --painting-channame DNA --barcoding-channame DAPI
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image
from scipy.ndimage import shift as ndi_shift
from skimage.registration import phase_cross_correlation

# Full-well stitched mosaics routinely exceed PIL's default decompression-bomb
# threshold (~89.5 megapixels) - these are legitimate large scientific images,
# not the malicious images that check guards against.
Image.MAX_IMAGE_PIXELS = None


def load_metadata(path: Path) -> List[dict]:
    with open(path) as f:
        return json.load(f)


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


def scale_array(arr: np.ndarray, scalingstring: str) -> np.ndarray:
    try:
        scale = float(scalingstring)
    except ValueError:
        print(f"WARNING: could not parse scalingstring '{scalingstring}' as a number, skipping scaling")
        return arr
    if scale == 1:
        return arr
    im = Image.fromarray(arr)
    new_size = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
    return np.array(im.resize(new_size, Image.LANCZOS))


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
    QC overlay so a biologist can eyeball scaling+alignment quality: barcoding
    (reference) in pink/magenta (R+B channels), painting (post-alignment) in green.
    Correctly aligned content reads neutral/white; misalignment shows visible
    magenta/green fringing. Downsampled 10x, same convention as the pipeline's
    other QC images.
    """
    ref_small = normalize_to_uint8(downsample(reference_arr, factor))
    mov_small = normalize_to_uint8(downsample(moving_arr, factor))
    h = min(ref_small.shape[0], mov_small.shape[0])
    w = min(ref_small.shape[1], mov_small.shape[1])
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[..., 0] = ref_small[:h, :w]  # R (pink/magenta = barcoding reference)
    rgb[..., 1] = mov_small[:h, :w]  # G (painting, post-alignment)
    rgb[..., 2] = ref_small[:h, :w]  # B (pink/magenta = barcoding reference)
    Image.fromarray(rgb, mode="RGB").save(path)


def crop_to_common_shape(a: np.ndarray, b: np.ndarray) -> tuple:
    """Guard against off-by-one size mismatches after independent per-arm scaling."""
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    return a[:h, :w], b[:h, :w]


def main(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.painting_output_dir.mkdir(parents=True, exist_ok=True)
    args.barcoding_output_dir.mkdir(parents=True, exist_ok=True)

    image_metas = load_metadata(args.metadata_json)
    painting_entries = [e for e in image_metas if e.get("arm_source") == "cellpainting"]
    barcoding_entries = [e for e in image_metas if e.get("arm_source") == "barcoding"]
    if not painting_entries or not barcoding_entries:
        print("Error: expected both cellpainting and barcoding entries in metadata-json")
        sys.exit(1)

    # Barcoding cycle 1's reference channel is the fixed anchor for the whole well.
    barcoding_cycles = [e.get("cycle") for e in barcoding_entries if e.get("cycle") is not None]
    barcoding_cycle1 = min(barcoding_cycles) if barcoding_cycles else None
    barcoding_ref_pool = [e for e in barcoding_entries if e.get("cycle") == barcoding_cycle1] if barcoding_cycle1 is not None else barcoding_entries
    barcoding_ref_entry = find_reference_image(barcoding_ref_pool, args.barcoding_channame)

    # Painting reference: one representative cycle (its own cycle 1 if multicycle,
    # otherwise the only "cycle" there is) - ALIGN_INTRAARM_PAINTING already made
    # painting's cycles mutually consistent, so one cross-arm shift covers all of them.
    painting_cycles = [e.get("cycle") for e in painting_entries if e.get("cycle") is not None]
    painting_cycle1 = min(painting_cycles) if painting_cycles else None
    painting_ref_pool = [e for e in painting_entries if e.get("cycle") == painting_cycle1] if painting_cycle1 is not None else painting_entries
    painting_ref_entry = find_reference_image(painting_ref_pool, args.painting_channame)

    if barcoding_ref_entry is None or painting_ref_entry is None:
        print(
            f"Error: could not find reference channels ('{args.barcoding_channame}' in barcoding, "
            f"'{args.painting_channame}' in painting) for cross-arm alignment"
        )
        sys.exit(1)

    # Only the two reference images need to be scaled and held in memory at once,
    # to compute the single shift applied to every painting image below. Every
    # other image is streamed through one at a time (loaded, scaled, saved,
    # discarded) instead of pre-loading the whole well (all cycles x channels,
    # both arms) into memory simultaneously - for a full-resolution multi-cycle
    # well, especially with barcoding's ~4x pixel-count upscale, that previously
    # ballooned to tens of GB and got OOM-killed.
    barcoding_ref_array = scale_array(load_array(args.barcoding_images_dir / barcoding_ref_entry["filename"]), args.barcoding_scalingstring)
    painting_ref_array = scale_array(load_array(args.painting_images_dir / painting_ref_entry["filename"]), args.painting_scalingstring)
    barcoding_ref_cropped, painting_ref_cropped = crop_to_common_shape(barcoding_ref_array, painting_ref_array)

    # shift = translation required to register painting (moving) with barcoding
    # (reference) - see skimage.registration.phase_cross_correlation docs. Apply
    # as-is via scipy.ndimage.shift, do not negate.
    shift, error, diffphase = phase_cross_correlation(barcoding_ref_cropped, painting_ref_cropped)
    print(f"Cross-arm shift (painting -> barcoding): {shift[0]:.3f},{shift[1]:.3f} error={error:.4f}")

    aligned_painting_ref_array = None
    for entry in painting_entries:
        if entry is painting_ref_entry:
            arr = painting_ref_array
        else:
            arr = scale_array(load_array(args.painting_images_dir / entry["filename"]), args.painting_scalingstring)
        shifted = ndi_shift(arr, shift, mode="constant", cval=0)
        save_array(shifted, arr.dtype, args.painting_output_dir / entry["filename"])
        if entry is painting_ref_entry:
            aligned_painting_ref_array = shifted
        del arr, shifted

    for entry in barcoding_entries:
        if entry is barcoding_ref_entry:
            arr = barcoding_ref_array
        else:
            arr = scale_array(load_array(args.barcoding_images_dir / entry["filename"]), args.barcoding_scalingstring)
        save_array(arr, arr.dtype, args.barcoding_output_dir / entry["filename"])
        del arr

    overlay_path = args.output_dir / "AlignCombined_QC.png"
    save_overlay(barcoding_ref_array, aligned_painting_ref_array, overlay_path)
    print(f"Wrote {overlay_path.name}")

    stats_path = args.output_dir / "AlignCombined_stats.csv"
    with open(stats_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["shift_row", "shift_col", "error", "diffphase", "painting_scalingstring", "barcoding_scalingstring"]
        )
        writer.writeheader()
        writer.writerow({
            "shift_row": shift[0],
            "shift_col": shift[1],
            "error": error,
            "diffphase": diffphase,
            "painting_scalingstring": args.painting_scalingstring,
            "barcoding_scalingstring": args.barcoding_scalingstring,
        })
    print(f"Wrote {stats_path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--painting-images-dir", type=Path, required=True)
    parser.add_argument("--barcoding-images-dir", type=Path, required=True)
    parser.add_argument("--metadata-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="Top-level output dir for the stats CSV and QC overlay PNG")
    parser.add_argument("--painting-output-dir", type=Path, required=True)
    parser.add_argument("--barcoding-output-dir", type=Path, required=True)
    parser.add_argument("--painting-scalingstring", default="1")
    parser.add_argument("--barcoding-scalingstring", default="1")
    parser.add_argument("--painting-channame", default="DNA")
    parser.add_argument("--barcoding-channame", default="DAPI")

    parsed_args = parser.parse_args()
    main(parsed_args)
