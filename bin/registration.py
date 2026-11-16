"""
Shared image-registration helpers for bin/align_intraarm.py (cycle -> cycle within an
arm) and bin/align_combined.py (painting -> barcoding).

register_coarse_to_fine() finds the single rigid translation that registers `moving`
onto `fixed`:

1. Coarse: background-subtract + block-mean downsample both images, Hann window,
   phase-correlate, scale back up. Robust to large offsets (~1000 px).
2. Fine: with the coarse shift applied, split the overlap into a grid of full-resolution
   tiles, phase-correlate each, and take a vote among tiles. Tiles with little signal
   (borders, empty regions) or hot-pixel/fixed-pattern peaks return junk shifts, so a
   single global correlation is not reliable; the consensus of the well-correlated tiles is.

Shift convention is that of skimage.registration.phase_cross_correlation: apply the
returned shift as-is with scipy.ndimage.shift, do not negate.
"""

from typing import Optional

import numpy as np
from scipy.ndimage import gaussian_filter
from skimage.filters import window
from skimage.registration import phase_cross_correlation


def prep_for_registration(arr: np.ndarray, sigma: float = 20.0, clip_percentile: float = 99.5) -> np.ndarray:
    """Clip hot pixels and subtract a Gaussian background so PCC sees structure, not intensity pedestals."""
    arr = arr.astype(np.float32)
    arr = np.clip(arr, 0, np.percentile(arr, clip_percentile))
    return arr - gaussian_filter(arr, sigma)


def block_mean(arr: np.ndarray, factor: int) -> np.ndarray:
    """Block-average downsample. Unlike a stride, this low-passes, which is what makes
    registration robust to differing fine detail/noise."""
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


def vote_tile_shifts(
    fixed: np.ndarray,
    moving: np.ndarray,
    grid: int = 5,
    max_residual: float = 20.0,
    agree_tol: float = 1.5,
    min_tile_ncc: float = 0.5,
) -> tuple:
    """
    Per-tile phase correlation on a grid x grid tiling, then a consensus shift.

    Each tile votes with its shift, weighted by that tile's post-shift NCC. The winner is
    the candidate with the greatest summed weight among tiles within `agree_tol` px of it
    (only tiles with NCC > `min_tile_ncc` count); the result is the median of that cluster.
    Returns (shift or None, n_agreeing_tiles, n_candidate_tiles).
    """
    h, w = fixed.shape
    th, tw = h // grid, w // grid
    shifts, scores = [], []
    for i in range(grid):
        for j in range(grid):
            sl = (slice(i * th, (i + 1) * th), slice(j * tw, (j + 1) * tw))
            f_raw, m_raw = fixed[sl].astype(np.float32), moving[sl].astype(np.float32)
            if f_raw.std() == 0 or m_raw.std() == 0:
                continue
            s, _, _ = phase_cross_correlation(prep_for_registration(f_raw), prep_for_registration(m_raw))
            if np.abs(s).max() > max_residual:
                continue
            shifts.append(s)
            scores.append(masked_ncc(f_raw, m_raw, s, stride=2))
    if not shifts:
        return None, 0, 0
    shifts, scores = np.array(shifts), np.nan_to_num(np.array(scores), nan=0.0)
    usable = scores > min_tile_ncc
    best_score, best_members = 0.0, None
    for s in shifts[usable]:
        members = usable & (np.abs(shifts - s).max(axis=1) <= agree_tol)
        score = scores[members].sum()
        if score > best_score:
            best_score, best_members = score, members
    if best_members is None:
        return None, 0, len(shifts)
    return np.median(shifts[best_members], axis=0), int(best_members.sum()), len(shifts)


def register_coarse_to_fine(
    fixed: np.ndarray,
    moving: np.ndarray,
    downsample_factor: int = 8,
    min_coarse_size: int = 64,
    min_fine_tile_size: int = 256,
    grid: int = 5,
    log=print,
) -> tuple:
    """
    Translation (row, col) registering `moving` onto `fixed`, as
    (shift, coarse_shift, ncc, n_tiles_agree). `fixed` and `moving` must have the same shape.
    """
    factor = int(max(1, min(downsample_factor, min(fixed.shape) // min_coarse_size)))
    fixed_small = prep_for_registration(block_mean(fixed, factor))
    moving_small = prep_for_registration(block_mean(moving, factor))
    win = window("hann", fixed_small.shape)
    coarse, _, _ = phase_cross_correlation(fixed_small * win, moving_small * win, upsample_factor=4)
    coarse = coarse * factor
    log(f"Coarse shift (downsample {factor}x): {coarse[0]:.1f},{coarse[1]:.1f}")

    shift, n_agree = coarse, 0
    sl_mov, sl_fix = overlap_slices(fixed.shape, coarse)
    fixed_ov, moving_ov = fixed[sl_fix], moving[sl_mov]
    if min(fixed_ov.shape) >= grid * min_fine_tile_size:
        residual, n_agree, n_tiles = vote_tile_shifts(fixed_ov, moving_ov, grid=grid)
        if residual is not None:
            shift = coarse + residual
            log(f"Fine residual: {residual[0]:.1f},{residual[1]:.1f} ({n_agree}/{n_tiles} tiles agree)")
        else:
            log(f"WARNING: no consensus among {n_tiles} fine-alignment tiles, keeping coarse shift")
    else:
        log("Overlap too small for fine alignment, keeping coarse shift")

    return shift, coarse, masked_ncc(fixed, moving, shift), n_agree
