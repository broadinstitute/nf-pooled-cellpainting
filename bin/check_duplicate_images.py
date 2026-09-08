#!/usr/bin/env python
"""
Fail loudly if any two output image files in a directory are pixel-identical.

This is a safety net against staging/matching bugs that silently reuse one
physical image where a different one should have been produced (e.g. a
positional-matching bug that maps two different acquisition cycles onto the
same underlying file) - the kind of defect that produces plausible-looking,
successfully-completed output with silently duplicated content.

Each file is loaded as an array (not compared as raw file bytes), and the
array is made contiguous before hashing - this is what makes memory-layout/
serialization differences (e.g. tiff internal tiling, non-contiguous numpy
strides) irrelevant while still catching real duplicated pixel content.

A file that fails to load is treated as a hard failure too, not skipped: an
output image a CellProfiler module claims to have produced that can't be
read is exactly as suspicious as a duplicate would be.

Blank frames (all-black or all-white images) are excluded from comparison:
some channels/sites legitimately produce a uniform blank image, and two
blank images matching each other is not the staging/matching bug this
check is meant to catch.

Usage:
    check_duplicate_images.py <images_dir> [--report report.txt]
"""

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image

EXTENSIONS = ("npy", "tif", "tiff")


def load_array(file_path: Path) -> np.ndarray:
    if file_path.suffix == ".npy":
        return np.load(file_path)
    return np.array(Image.open(file_path))


def is_blank(arr: np.ndarray) -> bool:
    """True if arr is uniformly all-black (0) or all-white (the dtype's max value)."""
    value = arr.flat[0]
    if not np.all(arr == value):
        return False
    if value == 0:
        return True
    if np.issubdtype(arr.dtype, np.integer):
        return value == np.iinfo(arr.dtype).max
    if np.issubdtype(arr.dtype, np.floating):
        return value == 1.0
    return False


def check_duplicates(images_dir: Path) -> Tuple[bool, List[str]]:
    """
    Scan images_dir (recursively, to tolerate Nextflow's numbered input_N/
    staging subdirectories) for .npy/.tif/.tiff files and check that no two
    have identical pixel content.

    Returns (success, report_lines).
    """
    seen: Dict[str, Path] = {}
    duplicates: List[Tuple[Path, Path]] = []
    errors: List[Tuple[Path, Exception]] = []
    blanks: List[Path] = []
    lines: List[str] = []

    files = sorted(
        {f for ext in EXTENSIONS for f in images_dir.rglob(f"*.{ext}")},
        key=lambda p: p.name,
    )

    if not files:
        msg = f"No image files found under {images_dir} - trivial pass."
        print(msg)
        return True, [msg]

    for file_path in files:
        try:
            arr = load_array(file_path)
        except Exception as exc:
            errors.append((file_path, exc))
            continue
        if is_blank(arr):
            blanks.append(file_path)
            continue
        digest = hashlib.md5(np.ascontiguousarray(arr).tobytes()).hexdigest()
        if digest in seen:
            duplicates.append((file_path, seen[digest]))
        else:
            seen[digest] = file_path

    for file_path, exc in errors:
        line = f"ERROR: could not read {file_path.name}: {exc}"
        print(line)
        lines.append(line)
    for dup, original in duplicates:
        line = f"DUPLICATE: {dup.name} is pixel-identical to {original.name}"
        print(line)
        lines.append(line)

    if errors or duplicates:
        return False, lines

    checked = len(files) - len(blanks)
    msg = f"OK: {checked} image file(s) checked, all pixel-content unique."
    if blanks:
        msg += f" ({len(blanks)} blank frame(s) excluded from comparison.)"
    print(msg)
    return True, [msg]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images_dir", type=Path, help="Directory to scan (recursively) for image files")
    parser.add_argument("--report", type=Path, default=None, help="Optional path to also write the summary to a text file")
    args = parser.parse_args()

    success, lines = check_duplicates(args.images_dir)

    if args.report:
        args.report.write_text("\n".join(lines) + "\n")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
