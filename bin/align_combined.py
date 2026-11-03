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
- Both arms are zero-padded (top-left anchored) onto one common canvas before the
  shift is applied, so shifting painting never pushes its right/bottom content off
  the array, and the aligned arms come out the same size.
- Same phase_cross_correlation + scipy.ndimage.shift approach as bin/align_intraarm.py
  (see that script for the shift-direction rationale), but registering across arms is
  done coarse-to-fine (block-mean downsample + windowed PCC, then full-res tile
  refinement) because the arms' mosaics can be offset by ~1000 px and full-resolution
  phase correlation alone fails on that.

Usage:
    align_combined.py \\
        --painting-images-dir images/painting/ --barcoding-images-dir images/barcoding/ \\
        --metadata-json metadata.json --output-dir . \\
        --painting-output-dir aligned_painting/ --barcoding-output-dir aligned_barcoding/ \\
        --painting-scalingstring 1 --barcoding-scalingstring 1.99 \\
        --painting-channame DNA --barcoding-channame DAPI [--align-on-threshold]
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
from skimage.filters import threshold_otsu, window
from skimage.registration import phase_cross_correlation

# Full-well stitched mosaics routinely exceed PIL's default decompression-bomb
# threshold (~89.5 megapixels) - these are legitimate large scientific images,
# not the malicious images that check guards against.
Image.MAX_IMAGE_PIXELS = None

# Registered reference images with a correlation at or below this are flagged as a likely failed alignment.
MIN_NCC = 0.1


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


def downsample(arr: np.ndarray, factor: int = 5) -> np.ndarray:
    """Stride-based Nx downsample - same approach as bin/stitch.py's write_downsampled."""
    return arr[::factor, ::factor]


def normalize_to_uint8(arr: np.ndarray) -> np.ndarray:
    """
    Normalize for QC display purposes only (not for analysis), scaling to the
    image's 99th percentile rather than its max so a handful of hot pixels
    don't wash out the rest of the display.
    """
    arr = arr.astype(np.float64)
    lo = arr.min()
    hi = np.percentile(arr, 99)
    if hi > lo:
        arr = np.clip((arr - lo) / (hi - lo), 0, 1)
    else:
        arr = np.zeros_like(arr)
    return (arr * 255).astype(np.uint8)


def save_overlay(reference_arr: np.ndarray, moving_arr: np.ndarray, path: Path, factor: int = 5) -> None:
    """
    QC overlay so a biologist can eyeball scaling+alignment quality: barcoding
    (reference) in pink/magenta (R+B channels), painting (post-alignment) in green.
    Correctly aligned content reads neutral/white; misalignment shows visible
    magenta/green fringing. Downsampled 5x, same convention as the pipeline's
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


def pad_to_canvas(arr: np.ndarray, height: int, width: int) -> np.ndarray:
    """Zero-pad (top-left anchored) to a common canvas so nothing is lost when the arrays are shifted/compared."""
    pad_rows = max(0, height - arr.shape[0])
    pad_cols = max(0, width - arr.shape[1])
    if pad_rows == 0 and pad_cols == 0:
        return arr
    return np.pad(arr, ((0, pad_rows), (0, pad_cols)), mode="constant", constant_values=0)


def threshold_mask(arr: np.ndarray) -> np.ndarray:
    """Otsu-threshold to a float32 binary mask (1.0 = foreground) for registration."""
    if arr.min() == arr.max():
        return np.zeros(arr.shape, dtype=np.float32)
    return (arr > threshold_otsu(arr)).astype(np.float32)


def block_mean(arr: np.ndarray, factor: int) -> np.ndarray:
    """Block-average downsample. Unlike a stride, this low-passes, which is what makes
    registration between the two arms' differing fine detail/noise robust."""
    if factor == 1:
        return arr.astype(np.float32)
    h, w = (arr.shape[0] // factor) * factor, (arr.shape[1] // factor) * factor
    return arr[:h, :w].reshape(h // factor, factor, w // factor, factor).mean(axis=(1, 3), dtype=np.float32)


def overlap_slices(shape: tuple, shift: np.ndarray) -> tuple:
    """Slices (moving, fixed) over the region where `moving` shifted by `shift` still lands inside `fixed`."""
    sl_mov, sl_fix = [], []
    for n, d in zip(shape, np.round(shift).astype(int)):
        lo, hi = max(0, -d), min(n, n - d)
        sl_mov.append(slice(lo, hi))
        sl_fix.append(slice(lo + d, hi + d))
    return tuple(sl_mov), tuple(sl_fix)


def masked_ncc(fixed: np.ndarray, moving: np.ndarray, shift: np.ndarray, stride: int = 4) -> float:
    """Normalized cross-correlation of the two images over their overlap after applying an integer-rounded shift."""
    sl_mov, sl_fix = overlap_slices(fixed.shape, shift)
    a = fixed[sl_fix][::stride, ::stride].astype(np.float64)
    b = moving[sl_mov][::stride, ::stride].astype(np.float64)
    keep = (a > 0) & (b > 0)
    if keep.sum() < 2:
        return float("nan")
    a, b = a[keep] - a[keep].mean(), b[keep] - b[keep].mean()
    denom = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / denom) if denom > 0 else float("nan")


def register_coarse_to_fine(
    fixed: np.ndarray,
    moving: np.ndarray,
    align_on_threshold: bool = False,
    downsample_factor: int = 8,
    min_coarse_size: int = 64,
    fine_tile_size: int = 1024,
    max_fine_spread: float = 8.0,
) -> tuple:
    """
    Translation (row, col) that registers `moving` onto `fixed`, as (shift, coarse_shift, ncc).

    Full-resolution phase correlation between the two arms is unreliable: their fine
    detail differs, the mosaics can be offset by ~1000 px (so they only partly overlap),
    and the zero-padded mosaic borders dominate the phase spectrum. So:
    1. Coarse: block-mean downsample both, Hann window, phase-correlate, scale back up.
       With --align-on-threshold the downsampled images are Otsu-thresholded to binary
       masks first.
    2. Fine: with the coarse shift applied, phase-correlate a few interior full-resolution
       tiles of the overlap and add the median residual (skipped if the overlap is small or
       the tiles disagree by more than `max_fine_spread` px).
    """
    factor = int(max(1, min(downsample_factor, min(fixed.shape) // min_coarse_size)))
    fixed_small, moving_small = block_mean(fixed, factor), block_mean(moving, factor)
    if align_on_threshold:
        fixed_small, moving_small = threshold_mask(fixed_small), threshold_mask(moving_small)
        print(f"Aligning on thresholded masks: foreground fraction fixed={fixed_small.mean():.3f} moving={moving_small.mean():.3f}")
    win = window("hann", fixed_small.shape)
    coarse, _, _ = phase_cross_correlation(fixed_small * win, moving_small * win, upsample_factor=4)
    coarse = coarse * factor
    print(f"Coarse shift (downsample {factor}x): {coarse[0]:.1f},{coarse[1]:.1f}")

    shift = coarse
    sl_mov, sl_fix = overlap_slices(fixed.shape, coarse)
    fixed_ov, moving_ov = fixed[sl_fix], moving[sl_mov]
    if min(fixed_ov.shape) >= 2 * fine_tile_size:
        residuals = []
        for fy in ((0.15, 0.45), (0.55, 0.85)):
            for fx in ((0.15, 0.45), (0.55, 0.85)):
                y0, y1 = int(fy[0] * fixed_ov.shape[0]), int(fy[1] * fixed_ov.shape[0])
                x0, x1 = int(fx[0] * fixed_ov.shape[1]), int(fx[1] * fixed_ov.shape[1])
                f_tile = fixed_ov[y0:y1, x0:x1].astype(np.float32)
                m_tile = moving_ov[y0:y1, x0:x1].astype(np.float32)
                if f_tile.std() == 0 or m_tile.std() == 0:
                    continue
                tile_win = window("hann", f_tile.shape)
                resid, _, _ = phase_cross_correlation(f_tile * tile_win, m_tile * tile_win, upsample_factor=10)
                residuals.append(resid)
        if residuals:
            residuals = np.array(residuals)
            spread = float(np.abs(residuals - np.median(residuals, axis=0)).max())
            if spread <= max_fine_spread:
                shift = coarse + np.median(residuals, axis=0)
                print(f"Fine residual (median of {len(residuals)} tiles): {np.median(residuals, axis=0)}")
            else:
                print(f"WARNING: fine-alignment tiles disagree by {spread:.1f}px (> {max_fine_spread}), keeping coarse shift")
    else:
        print("Overlap too small for fine alignment, keeping coarse shift")

    return shift, coarse, masked_ncc(fixed, moving, shift)


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
    # (reference) - same convention as skimage.registration.phase_cross_correlation.
    # Apply as-is via scipy.ndimage.shift, do not negate.
    shift, coarse_shift, ncc = register_coarse_to_fine(
        barcoding_ref_cropped,
        painting_ref_cropped,
        align_on_threshold=args.align_on_threshold,
        downsample_factor=args.downsample_factor,
    )
    print(f"Cross-arm shift (painting -> barcoding): {shift[0]:.3f},{shift[1]:.3f} ncc={ncc:.4f}")
    if not ncc > MIN_NCC:
        print(f"WARNING: registered reference images barely correlate (ncc={ncc:.4f} <= {MIN_NCC}); the cross-arm alignment probably failed")

    # The two arms' stitched mosaics differ in size, and the painting shift can be
    # large (hundreds+ px). Shifting within painting's own canvas would push its
    # right/bottom content off the array (lost for good), so both arms are padded
    # (top-left anchored) onto one common canvas first: at least the larger arm, and
    # big enough that a positive shift doesn't push painting content off the edge.
    canvas_h = max(barcoding_ref_array.shape[0], painting_ref_array.shape[0] + max(0, int(np.ceil(shift[0]))))
    canvas_w = max(barcoding_ref_array.shape[1], painting_ref_array.shape[1] + max(0, int(np.ceil(shift[1]))))
    print(f"Common canvas (rows x cols): {canvas_h} x {canvas_w}")

    aligned_painting_ref_array = None
    for entry in painting_entries:
        if entry is painting_ref_entry:
            arr = painting_ref_array
        else:
            arr = scale_array(load_array(args.painting_images_dir / entry["filename"]), args.painting_scalingstring)
        shifted = ndi_shift(pad_to_canvas(arr, canvas_h, canvas_w), shift, mode="constant", cval=0)
        save_array(shifted, arr.dtype, args.painting_output_dir / entry["filename"])
        if entry is painting_ref_entry:
            aligned_painting_ref_array = shifted
        del arr, shifted

    for entry in barcoding_entries:
        if entry is barcoding_ref_entry:
            arr = barcoding_ref_array
        else:
            arr = scale_array(load_array(args.barcoding_images_dir / entry["filename"]), args.barcoding_scalingstring)
        arr = pad_to_canvas(arr, canvas_h, canvas_w)
        save_array(arr, arr.dtype, args.barcoding_output_dir / entry["filename"])
        if entry is barcoding_ref_entry:
            barcoding_ref_array = arr
        del arr

    overlay_path = args.output_dir / "AlignCombined_QC.png"
    save_overlay(barcoding_ref_array, aligned_painting_ref_array, overlay_path)
    print(f"Wrote {overlay_path.name}")

    stats_path = args.output_dir / "AlignCombined_stats.csv"
    with open(stats_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["shift_row", "shift_col", "coarse_shift_row", "coarse_shift_col", "ncc", "painting_scalingstring", "barcoding_scalingstring"]
        )
        writer.writeheader()
        writer.writerow({
            "shift_row": shift[0],
            "shift_col": shift[1],
            "coarse_shift_row": coarse_shift[0],
            "coarse_shift_col": coarse_shift[1],
            "ncc": ncc,
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
    parser.add_argument("--downsample-factor", type=int, default=8, help="Block-mean downsample factor for the coarse registration step")
    parser.add_argument("--painting-channame", default="DNA")
    parser.add_argument("--barcoding-channame", default="DAPI")

    parser.add_argument(
        "--align-on-threshold",
        action="store_true",
        help="Otsu-threshold the downsampled reference images to binary masks for the coarse registration step",
    )

    parsed_args = parser.parse_args()
    main(parsed_args)
