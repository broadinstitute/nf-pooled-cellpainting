#!/usr/bin/env python
"""
Simple montage creator for image folders.

Design philosophy:
- Detect image patterns in a folder and arrange them automatically
- Support both numpy arrays (.npy) and regular images (.png, .jpg)
- Use PIL for proper image handling
- Keep the interface minimal and intuitive

Usage:
    # Direct execution (requires numpy and pillow installed):
    ./montage.py input_dir output.png --pattern ".*\\.npy$"

    # Using pixi for dependency management (recommended):
    python montage.py input_dir output.png --pattern ".*\\.npy$"

    # Examples with regex patterns:
    # All .npy files:
    python montage.py data/illum/Plate1 illum_montage.png --pattern ".*\\.npy$"

    # Cell Painting illumination only (exclude Cycle):
    python montage.py data/illum/Plate1 illum_montage.png --pattern "^(?!.*Cycle).*\\.npy$"

    # Barcoding illumination only (must contain Cycle):
    python montage.py data/illum/Plate1 illum_montage.png --pattern ".*Cycle.*\\.npy$"

    # Segmentation check images:
    python montage.py data/segmentation/Plate1-A1 seg_montage.png --pattern ".*SegmentCheck\\.png$"
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# Montages larger than this are split into multiple files (_part01, _part02, ...)
DEFAULT_MAX_DIM = 16000
DEFAULT_MAX_PIXELS = 100_000_000


def natural_sort_key(s: str) -> List:
    """Natural sorting key that handles numbers properly."""
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split("([0-9]+)", s)
    ]


def load_image(file_path: Path, apply_sqrt: bool = False):
    """
    Load an image file and convert to PIL Image.

    Args:
        file_path: Path to the file
        apply_sqrt: Apply sqrt transform (for illumination functions)

    Returns:
        Tuple of (PIL Image, (min_val, max_val)) for .npy files, or (PIL Image, None) for others.
    """
    if file_path.suffix == ".npy":
        # Load numpy array
        arr = np.load(file_path)

        # Handle grayscale illumination functions
        if apply_sqrt:
            arr = np.sqrt(np.maximum(arr, 0))  # Ensure non-negative before sqrt

        min_val, max_val = float(arr.min()), float(arr.max())

        # Normalize to 0-255 range
        if max_val > min_val:
            arr = (arr - min_val) / (max_val - min_val)
        arr = (arr * 255).astype(np.uint8)

        img = Image.fromarray(arr)
        img = img.resize((img.width // 4, img.height // 4), Image.LANCZOS)
        return img, (min_val, max_val)

    else:
        # Load regular image file
        return Image.open(file_path), None


def extract_pattern_groups(files: List[Path]) -> Dict[str, List[Tuple[str, Path]]]:
    """
    Analyze filenames to extract natural groupings.

    Returns dict of pattern_type -> [(label, path), ...]
    """
    patterns = {}

    for file_path in files:
        name = file_path.stem

        # Check for cycle-based patterns (for barcoding)
        cycle_match = re.search(r"Cycle(\d+)", name)
        if cycle_match:
            cycle = f"Cycle{cycle_match.group(1)}"
            # Extract channel from the rest
            channel_match = re.search(r"Illum([A-Za-z0-9]+)", name)
            if channel_match:
                channel = channel_match.group(1)
                key = f"{cycle}_{channel}"
                patterns.setdefault("cycle_channel", []).append((key, file_path))
            continue

        # Check for illumination patterns (without cycle)
        illum_match = re.search(r"Illum([A-Za-z0-9]+)", name)
        if illum_match:
            channel = illum_match.group(1)
            patterns.setdefault("channel", []).append((channel, file_path))
            continue

        # Check for site-based patterns (segmentation images)
        site_match = re.search(r"Site[_\s]?(\d+)", name)
        if site_match:
            site_num = site_match.group(1)
            well_match = re.search(r"(?:^|[-_])([A-P]\d{1,2})(?:[-_])", name)
            well = well_match.group(1) if well_match else ""
            label = f"{well}\nSite{site_num}" if well else f"Site{site_num}"
            sort_key = (well, int(site_num))
            patterns.setdefault("site", []).append((sort_key, label, file_path))
            continue

        # Default: use filename stem
        patterns.setdefault("default", []).append((name, file_path))

    return patterns


def determine_grid_layout(n_items: int, aspect_ratio: float = 1.5) -> Tuple[int, int]:
    """
    Determine optimal grid layout for n items.

    Args:
        n_items: Number of items to arrange
        aspect_ratio: Desired width/height ratio

    Returns:
        (n_cols, n_rows)
    """
    if n_items <= 0:
        return 0, 0
    if n_items == 1:
        return 1, 1

    # Try to get close to desired aspect ratio
    n_cols = int(np.ceil(np.sqrt(n_items * aspect_ratio)))
    n_rows = int(np.ceil(n_items / n_cols))

    # Adjust to minimize empty cells
    while n_cols * (n_rows - 1) >= n_items and n_rows > 1:
        n_rows -= 1

    return n_cols, n_rows


def create_montage(
    images: List[Tuple[str, Image.Image]],
    grid: Optional[Tuple[int, int]] = None,
    padding: int = 5,
    background_color: tuple = (255, 255, 255),
    label_height: int = 90,
) -> Image.Image:
    """
    Create a montage from a list of images.

    Args:
        images: List of (label, PIL.Image) tuples
        grid: Optional (cols, rows) specification
        padding: Space between images
        background_color: Background color (R, G, B)
        label_height: Height reserved for labels

    Returns:
        Montage as PIL Image
    """
    if not images:
        raise ValueError("No images to create montage")

    # Determine grid layout
    n_images = len(images)
    if grid is None:
        n_cols, n_rows = determine_grid_layout(n_images)
    else:
        n_cols, n_rows = grid

    # Get maximum dimensions
    max_width = max(img.width for _, img in images)
    max_height = max(img.height for _, img in images)

    # Calculate montage dimensions
    cell_width = max_width + padding * 2
    cell_height = max_height + label_height + padding * 2
    montage_width = n_cols * cell_width
    montage_height = n_rows * cell_height

    # Create montage image
    montage = Image.new("RGB", (montage_width, montage_height), background_color)
    draw = ImageDraw.Draw(montage)

    # Try to load a font for labels (fallback to default)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
    except:
        try:
            # Try a common Linux font path
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36
            )
        except:
            font = ImageFont.load_default(size=36)

    # Place images
    for idx, (label, img) in enumerate(images):
        row = idx // n_cols
        col = idx % n_cols

        # Calculate position (center image in cell)
        x = col * cell_width + padding + (max_width - img.width) // 2
        y = row * cell_height + padding + label_height + (max_height - img.height) // 2

        # Convert grayscale to RGB if needed
        if img.mode == "L":
            img = img.convert("RGB")
        elif img.mode == "RGBA":
            # Handle RGBA by compositing on white background
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3] if len(img.split()) > 3 else None)
            img = bg

        # Paste image
        montage.paste(img, (x, y))

        # Add label
        label_x = col * cell_width + cell_width // 2
        label_y = row * cell_height + padding + label_height // 2

        # Get text bounding box for centering
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        draw.text(
            (label_x - text_width // 2, label_y - text_height // 2),
            label,
            fill=(0, 0, 0),
            font=font,
        )

    return montage


def cell_size(images: List[Tuple[str, Image.Image]], padding: int = 5, label_height: int = 90) -> Tuple[int, int]:
    """Size of one montage cell (must match create_montage)."""
    return (
        max(img.width for _, img in images) + padding * 2,
        max(img.height for _, img in images) + label_height + padding * 2,
    )


def plan_parts(
    n_images: int,
    cell_w: int,
    cell_h: int,
    grid: Optional[Tuple[int, int]],
    max_dim: int,
    max_pixels: int,
) -> List[Tuple[slice, Optional[Tuple[int, int]]]]:
    """
    Decide how to split n_images across one or more montage files so that no
    file exceeds max_dim pixels on a side or max_pixels in total.

    Returns a list of (slice into the image list, grid for that part). A single
    entry means no splitting is needed and the original grid is kept.
    """
    if grid is None:
        n_cols, _ = determine_grid_layout(n_images)
        n_cols = min(n_cols, max(1, max_dim // cell_w))
    else:
        n_cols = grid[0]
    max_rows = max(1, max_dim // cell_h)
    max_rows = min(max_rows, max(1, max_pixels // (n_cols * cell_w * cell_h)))
    per_part = n_cols * max_rows
    if n_images <= per_part:
        return [(slice(0, n_images), grid)]
    parts = []
    for start in range(0, n_images, per_part):
        n = min(per_part, n_images - start)
        parts.append((slice(start, start + n), (n_cols, -(-n // n_cols))))
    return parts


def organize_cycle_channel_layout(
    items: List[Tuple[str, Path]],
) -> List[Tuple[str, Path]]:
    """
    Organize cycle-channel data into a grid layout.
    Returns items sorted for row-major grid placement.
    """
    # Parse cycle and channel from each item
    parsed = []
    for label, path in items:
        match = re.match(r"Cycle(\d+)_(.+)", label)
        if match:
            cycle = int(match.group(1))
            channel = match.group(2)
            parsed.append((cycle, channel, label, path))

    if not parsed:
        return items

    # Get unique cycles and channels
    cycles = sorted(set(p[0] for p in parsed))
    channels = sorted(set(p[1] for p in parsed))

    # Create lookup
    lookup = {(p[0], p[1]): (p[2], p[3]) for p in parsed}

    # Arrange in grid order (cycles as rows, channels as columns)
    result = []
    for cycle in cycles:
        for channel in channels:
            if (cycle, channel) in lookup:
                result.append(lookup[(cycle, channel)])

    return result


def main(
    input_dir: Path,
    output_file: Path,
    pattern: str = ".*",
    apply_sqrt: bool = None,
    grid: Optional[Tuple[int, int]] = None,
    max_dim: int = DEFAULT_MAX_DIM,
    max_pixels: int = DEFAULT_MAX_PIXELS,
):
    """
    Create a montage from images in a directory.

    Args:
        input_dir: Directory containing images
        output_file: Output file path
        pattern: Regex pattern to match filenames (e.g., ".*\\.npy$", "^(?!.*Cycle).*\\.npy$")
        apply_sqrt: Apply sqrt transform (auto-detect if None)
        grid: Optional (cols, rows) grid specification
        max_dim: Max pixels per side of an output file; larger montages are split
        max_pixels: Max total pixels of an output file; larger montages are split
    """
    # Find matching files using regex
    import re

    regex = re.compile(pattern)
    all_files = input_dir.iterdir()
    files = sorted(
        [f for f in all_files if f.is_file() and regex.match(f.name)],
        key=lambda p: natural_sort_key(p.name),
    )

    if not files:
        print(f"No files matching '{pattern}' found in {input_dir}")
        return

    print(f"Found {len(files)} files")

    # Auto-detect if we should apply sqrt (for .npy illumination files)
    if apply_sqrt is None:
        apply_sqrt = all(f.suffix == ".npy" and "Illum" in f.name for f in files)
        if apply_sqrt:
            print("Detected illumination functions - applying sqrt transform")

    # Analyze patterns
    pattern_groups = extract_pattern_groups(files)

    # Determine organization strategy
    if "cycle_channel" in pattern_groups:
        # Barcoding-style cycle x channel grid
        items = organize_cycle_channel_layout(pattern_groups["cycle_channel"])

        # Calculate grid dimensions
        cycles = len(
            set(
                re.match(r"Cycle(\d+)", label).group(1)
                for label, _ in items
                if re.match(r"Cycle(\d+)", label)
            )
        )
        channels = len(items) // cycles if cycles > 0 else len(items)

        if grid is None:
            grid = (channels, cycles)

        print(f"Organizing as {cycles} cycles x {channels} channels")

    elif "channel" in pattern_groups:
        # Simple channel layout (single row)
        items = sorted(pattern_groups["channel"], key=lambda x: natural_sort_key(x[0]))
        if grid is None:
            grid = (len(items), 1)
        print(f"Organizing {len(items)} channels in a row")

    elif "site" in pattern_groups:
        # Site-based layout — sort by well then site number, label includes both
        items = [(label, fp) for _, label, fp in sorted(pattern_groups["site"], key=lambda x: x[0])]
        print(f"Organizing {len(items)} sites")

    else:
        # Default layout
        items = [(f.stem, f) for f in files]
        print(f"Using default layout for {len(items)} files")

    # Load images
    images = []
    all_max_vals = []
    all_min_vals = []
    dup_detect = False
    for label, file_path in items:
        try:
            img, stats = load_image(file_path, apply_sqrt=apply_sqrt)
            if stats is not None:
                min_val, max_val = stats
                all_max_vals.append(max_val)
                all_min_vals.append(min_val)
                label = f"{label}\nmax={max_val:.2g}"
            for prev_label, prev_img in images:
                if np.array_equal(np.array(img), np.array(prev_img)):
                    dup_detect = True
            images.append((label, img))
            print(f"  Loaded: {file_path.name} -> {label}")
        except Exception as e:
            print(f"  Error loading {file_path.name}: {e}")

    if not images:
        print("No images could be loaded")
        return

    def render_part(part_images, part_grid, out_path):
        # Create montage
        print(f"\nCreating montage with grid {part_grid if part_grid else 'auto'}...")
        montage = create_montage(part_images, grid=part_grid)

        # Append footer with global max if .npy files were loaded
        if all_max_vals:
            global_max = max(all_max_vals)
            footer_text = f"Max of all max values: {global_max:.4g}"
            if global_max > 4:
                footer_text += "  WARNING: HIGH VALUE. POTENTIAL PROBLEM"
            if any(val == 1 for val in all_max_vals):
                footer_text += "  ERROR: ILLUMS IMPROPERLY MADE!!! ILLUM WITH MAX=1 DETECTED"
            if any(val != 1 for val in all_min_vals):
                footer_text += "  ERROR: ILLUMS IMPROPERLY MADE!!! ILLUM WITH MIN!=1 DETECTED"
            if dup_detect:
                footer_text += "  ERROR: DUPLICATED ILLUMS DETECTED!!!"
            footer_height = 100
            footer = Image.new("RGB", (montage.width, footer_height), (255, 255, 255))
            draw = ImageDraw.Draw(footer)
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
            except:
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
                except:
                    font = ImageFont.load_default(size=36)
            bbox = draw.textbbox((0, 0), footer_text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            draw.text(((montage.width - text_w) // 2, (footer_height - text_h) // 2), footer_text, fill=(0, 0, 0), font=font)
            combined = Image.new("RGB", (montage.width, montage.height + footer_height), (255, 255, 255))
            combined.paste(montage, (0, 0))
            combined.paste(footer, (0, montage.height))
            montage = combined

        # Save
        out_path.parent.mkdir(parents=True, exist_ok=True)
        montage.save(out_path, quality=95)
        print(f"Saved montage to: {out_path}")
        print(f"Dimensions: {montage.width}x{montage.height}")

    cell_w, cell_h = cell_size(images)
    parts = plan_parts(len(images), cell_w, cell_h, grid, max_dim, max_pixels)
    if len(parts) == 1:
        render_part(images, grid, output_file)
    else:
        print(
            f"Montage would exceed {max_dim}px per side / {max_pixels:,} pixels; "
            f"splitting {len(images)} images into {len(parts)} files"
        )
        for i, (chunk, part_grid) in enumerate(parts, start=1):
            out_path = output_file.with_name(
                f"{output_file.stem}_part{i:02d}{output_file.suffix}"
            )
            render_part(images[chunk], part_grid, out_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Create image montage from a directory"
    )
    parser.add_argument("input_dir", type=Path, help="Directory containing images")
    parser.add_argument("output_file", type=Path, help="Output montage file")
    parser.add_argument(
        "-p",
        "--pattern",
        default=".*",
        help="Regex pattern for filenames (default: .* matches all)",
    )
    parser.add_argument("--sqrt", action="store_true", help="Apply sqrt transform")
    parser.add_argument(
        "--no-sqrt", action="store_true", help="Don't apply sqrt transform"
    )
    parser.add_argument(
        "-g", "--grid", type=str, help="Grid layout as 'COLSxROWS' (e.g., '3x2')"
    )

    parser.add_argument(
        "--max-dim",
        type=int,
        default=DEFAULT_MAX_DIM,
        help="Max pixels per side of an output file; split into _partNN files if exceeded",
    )
    parser.add_argument(
        "--max-pixels",
        type=int,
        default=DEFAULT_MAX_PIXELS,
        help="Max total pixels of an output file; split into _partNN files if exceeded",
    )

    args = parser.parse_args()

    # Parse grid
    grid = None
    if args.grid:
        try:
            cols, rows = map(int, args.grid.lower().split("x"))
            grid = (cols, rows)
        except:
            print(f"Invalid grid format: {args.grid}. Use format like '3x2'")
            sys.exit(1)

    # Determine sqrt application
    apply_sqrt = None
    if args.sqrt:
        apply_sqrt = True
    elif args.no_sqrt:
        apply_sqrt = False

    main(
        args.input_dir,
        args.output_file,
        pattern=args.pattern,
        apply_sqrt=apply_sqrt,
        grid=grid,
        max_dim=args.max_dim,
        max_pixels=args.max_pixels,
    )
