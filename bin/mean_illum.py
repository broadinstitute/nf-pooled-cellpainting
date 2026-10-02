#!/usr/bin/env python
"""
Average per-well illumination-correction .npy files into per-plate ones.

--distributeillum runs CELLPROFILER_ILLUMCALC once per well instead of once per
plate (smaller, more parallelizable CellProfiler jobs). CellProfiler's SaveImages
module names each output file from Metadata_Plate (and Metadata_Cycle for
barcoding) only - never well - so every well's run for a given plate produces
identically-named files (e.g. Plate1_IllumDNA.npy). This script is the other half
of that trick: it averages all files sharing the same basename across the
well-numbered staging subdirectories, and writes one output file per basename, so
the result is usable downstream exactly like a normal per-plate illumcalc output.

Usage:
    mean_illum.py <staging_dir> --outdir .
"""

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import numpy as np


def group_by_basename(staging_dir: Path) -> Dict[str, List[Path]]:
    groups: Dict[str, List[Path]] = defaultdict(list)
    for file_path in sorted(staging_dir.rglob("*.npy")):
        groups[file_path.name].append(file_path)
    return groups


def write_means(groups: Dict[str, List[Path]], outdir: Path) -> None:
    for name, paths in groups.items():
        arrays = [np.load(p) for p in paths]
        mean = np.mean(arrays, axis=0).astype(arrays[0].dtype)
        np.save(outdir / name, mean)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging_dir", type=Path, help="Directory containing well*/ subdirectories of .npy files")
    parser.add_argument("--outdir", type=Path, default=Path("."), help="Directory to write averaged .npy files to")
    args = parser.parse_args()

    groups = group_by_basename(args.staging_dir)
    if not groups:
        raise SystemExit(f"No .npy files found under {args.staging_dir}")

    write_means(groups, args.outdir)


if __name__ == "__main__":
    main()
