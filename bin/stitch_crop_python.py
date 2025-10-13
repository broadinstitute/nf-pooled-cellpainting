#!/usr/bin/env python3
"""Modern Python implementation of microscopy image stitching and cropping.

This replaces the Fiji/ImageJ-based stitch_crop.py with a pure Python implementation
using standard libraries: PIL/Pillow, numpy, and tifffile.

Features:
- Grid-based image stitching with overlap handling
- Linear blending for seamless stitching
- Image scaling and cropping into tiles
- Downsampling for QC
- LZW compression support
- No Fiji/ImageJ dependency

Usage:
    python stitch_crop_modern.py INPUT_BASE TRACK_TYPE [OPTIONS]

Arguments:
    INPUT_BASE          Base directory containing input images
    TRACK_TYPE          Track type identifier (e.g., barcoding, cellpainting)

Options:
    --crop-percent INT  Crop percentage (25, 50, or other) [default: 25]
    --grid-rows INT     Number of rows in site grid [default: 2]
    --grid-cols INT     Number of columns in site grid [default: 2]
    --overlap FLOAT     Overlap percentage between tiles [default: 10.0]
    --scale FLOAT       Scaling factor for stitched images [default: 1.99]
    --tiles-per-side INT Number of tiles to crop per side [default: 2]
    --no-compress       Disable LZW compression
    --help              Show this help message

Examples:
    python stitch_crop_modern.py /data/experiment barcoding --crop-percent 25
    python stitch_crop_modern.py /data/experiment cellpainting --crop-percent 50 --no-compress
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
from PIL import Image
import tifffile

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ImageStitcher:
    """Handles stitching of microscopy images with overlap."""

    def __init__(self, grid_rows: int, grid_cols: int, overlap_percent: float = 10.0):
        """Initialize the stitcher.

        Args:
            grid_rows: Number of rows in the site grid
            grid_cols: Number of columns in the site grid
            overlap_percent: Percentage overlap between adjacent images
        """
        self.grid_rows = grid_rows
        self.grid_cols = grid_cols
        self.overlap_percent = overlap_percent

    def stitch_images(
        self, image_paths: List[Path], output_size: Optional[Tuple[int, int]] = None
    ) -> np.ndarray:
        """Stitch images in a grid pattern with linear blending.

        Args:
            image_paths: List of paths to images (ordered row-by-row, left-to-right)
            output_size: Optional (height, width) for the output canvas

        Returns:
            Stitched image as numpy array
        """
        if len(image_paths) != self.grid_rows * self.grid_cols:
            raise ValueError(
                f"Expected {self.grid_rows * self.grid_cols} images, "
                f"got {len(image_paths)}"
            )

        # Load first image to get dimensions and dtype
        first_img = tifffile.imread(str(image_paths[0]))
        img_height, img_width = first_img.shape[:2]
        dtype = first_img.dtype
        is_multichannel = first_img.ndim == 3

        # Calculate overlap in pixels
        overlap_pixels = int(img_width * self.overlap_percent / 100)

        # Calculate stitched dimensions
        effective_width = img_width - overlap_pixels
        effective_height = img_height - overlap_pixels
        stitched_width = img_width + (self.grid_cols - 1) * effective_width
        stitched_height = img_height + (self.grid_rows - 1) * effective_height

        logger.info(
            f"Stitching {self.grid_rows}x{self.grid_cols} grid: "
            f"tile size {img_width}x{img_height}, "
            f"overlap {overlap_pixels}px, "
            f"output {stitched_width}x{stitched_height}"
        )

        # Create output canvas
        if is_multichannel:
            canvas = np.zeros(
                (stitched_height, stitched_width, first_img.shape[2]),
                dtype=np.float32
            )
            weight_map = np.zeros(
                (stitched_height, stitched_width, first_img.shape[2]),
                dtype=np.float32
            )
        else:
            canvas = np.zeros((stitched_height, stitched_width), dtype=np.float32)
            weight_map = np.zeros((stitched_height, stitched_width), dtype=np.float32)

        # Place each image with blending
        idx = 0
        for row in range(self.grid_rows):
            for col in range(self.grid_cols):
                # Load image
                img = tifffile.imread(str(image_paths[idx]))
                img = img.astype(np.float32)

                # Calculate position
                y_start = row * effective_height
                x_start = col * effective_width
                y_end = y_start + img_height
                x_end = x_start + img_width

                # Create blending mask - start with full weight everywhere
                if is_multichannel:
                    blend_mask = np.ones((img_height, img_width, img.shape[2]), dtype=np.float32)
                else:
                    blend_mask = np.ones((img_height, img_width), dtype=np.float32)

                # Apply fade-out on right edge (for all columns except last)
                if col < self.grid_cols - 1:
                    right_blend = np.linspace(1, 0, overlap_pixels)
                    if is_multichannel:
                        blend_mask[:, -overlap_pixels:, :] *= right_blend[np.newaxis, :, np.newaxis]
                    else:
                        blend_mask[:, -overlap_pixels:] *= right_blend[np.newaxis, :]

                # Apply fade-out on bottom edge (for all rows except last)
                if row < self.grid_rows - 1:
                    bottom_blend = np.linspace(1, 0, overlap_pixels)
                    if is_multichannel:
                        blend_mask[-overlap_pixels:, :, :] *= bottom_blend[:, np.newaxis, np.newaxis]
                    else:
                        blend_mask[-overlap_pixels:, :] *= bottom_blend[:, np.newaxis]

                # Apply fade-in on left edge (for columns after first)
                if col > 0:
                    left_blend = np.linspace(0, 1, overlap_pixels)
                    if is_multichannel:
                        blend_mask[:, :overlap_pixels, :] *= left_blend[np.newaxis, :, np.newaxis]
                    else:
                        blend_mask[:, :overlap_pixels] *= left_blend[np.newaxis, :]

                # Apply fade-in on top edge (for rows after first)
                if row > 0:
                    top_blend = np.linspace(0, 1, overlap_pixels)
                    if is_multichannel:
                        blend_mask[:overlap_pixels, :, :] *= top_blend[:, np.newaxis, np.newaxis]
                    else:
                        blend_mask[:overlap_pixels, :] *= top_blend[:, np.newaxis]

                # Add weighted image to canvas
                canvas[y_start:y_end, x_start:x_end] += img * blend_mask
                weight_map[y_start:y_end, x_start:x_end] += blend_mask

                idx += 1

        # Normalize by weight map (avoid division by zero)
        weight_map = np.maximum(weight_map, 1e-10)
        canvas = canvas / weight_map

        # Convert back to original dtype
        canvas = np.clip(canvas, 0, np.iinfo(dtype).max if np.issubdtype(dtype, np.integer) else 1.0)
        return canvas.astype(dtype)


class ImageProcessor:
    """Handles image processing operations (scaling, cropping, saving)."""

    @staticmethod
    def scale_image(img: np.ndarray, scale_factor: float, interpolation: str = "bilinear") -> np.ndarray:
        """Scale an image by a given factor.

        Args:
            img: Input image as numpy array
            scale_factor: Scaling factor (e.g., 1.99 for ~2x)
            interpolation: Interpolation method ('bilinear', 'bicubic', 'nearest')

        Returns:
            Scaled image as numpy array
        """
        is_multichannel = img.ndim == 3

        # Convert to PIL Image
        if is_multichannel:
            pil_img = Image.fromarray(img)
        else:
            pil_img = Image.fromarray(img)

        # Calculate new size
        new_width = int(round(pil_img.width * scale_factor))
        new_height = int(round(pil_img.height * scale_factor))

        # Map interpolation method
        interp_map = {
            "bilinear": Image.BILINEAR,
            "bicubic": Image.BICUBIC,
            "nearest": Image.NEAREST
        }
        interp = interp_map.get(interpolation.lower(), Image.BILINEAR)

        # Resize
        scaled = pil_img.resize((new_width, new_height), interp)

        return np.array(scaled)

    @staticmethod
    def adjust_canvas(img: np.ndarray, target_size: int, position: str = "top-left") -> np.ndarray:
        """Adjust canvas size by padding or cropping.

        Args:
            img: Input image
            target_size: Target width and height
            position: Position for placement ('top-left', 'center')

        Returns:
            Image with adjusted canvas
        """
        height, width = img.shape[:2]
        is_multichannel = img.ndim == 3

        # Create new canvas
        if is_multichannel:
            canvas = np.zeros((target_size, target_size, img.shape[2]), dtype=img.dtype)
        else:
            canvas = np.zeros((target_size, target_size), dtype=img.dtype)

        # Calculate position
        if position == "top-left":
            y_offset, x_offset = 0, 0
        elif position == "center":
            y_offset = (target_size - height) // 2
            x_offset = (target_size - width) // 2
        else:
            y_offset, x_offset = 0, 0

        # Copy image to canvas (crop if necessary)
        h_end = min(height, target_size)
        w_end = min(width, target_size)
        canvas[y_offset:y_offset + h_end, x_offset:x_offset + w_end] = img[:h_end, :w_end]

        return canvas

    @staticmethod
    def crop_into_tiles(img: np.ndarray, tiles_per_side: int) -> List[np.ndarray]:
        """Crop image into square tiles.

        Args:
            img: Input image
            tiles_per_side: Number of tiles per side (e.g., 2 for 2x2 grid)

        Returns:
            List of tile images
        """
        height, width = img.shape[:2]
        tile_height = height // tiles_per_side
        tile_width = width // tiles_per_side

        tiles = []
        for row in range(tiles_per_side):
            for col in range(tiles_per_side):
                y_start = row * tile_height
                x_start = col * tile_width
                y_end = y_start + tile_height
                x_end = x_start + tile_width

                tile = img[y_start:y_end, x_start:x_end]
                tiles.append(tile)

        return tiles

    @staticmethod
    def save_tiff(img: np.ndarray, output_path: Path, compress: bool = True):
        """Save image as TIFF with optional LZW compression.

        Args:
            img: Image to save
            output_path: Output file path
            compress: Whether to use LZW compression
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        compression = "lzw" if compress else None

        tifffile.imwrite(
            str(output_path),
            img,
            compression=compression,
            photometric="minisblack" if img.ndim == 2 else "rgb"
        )

        logger.info(f"Saved: {output_path} ({img.shape})")


def parse_filename(filename: str) -> Optional[Dict[str, str]]:
    """Parse microscopy filename to extract metadata.

    Expected format: {prefix}_Well_{wellID}_Site_{siteNumber}_{channel}.tif

    Args:
        filename: Input filename

    Returns:
        Dictionary with parsed metadata or None if parsing fails
    """
    try:
        if "Overlay" in filename or ".tif" not in filename.lower():
            return None

        # Split by _Well_
        prefix, suffix_with_well = filename.split("_Well_")
        well, suffix_after_well = suffix_with_well.split("_Site_")

        # Extract site number and channel
        site_and_channel = suffix_after_well.split("_", 1)
        site = site_and_channel[0]
        channel = site_and_channel[1] if len(site_and_channel) > 1 else ""

        # Extract plate ID from prefix (e.g., "Plate_Plate1" -> "Plate1")
        plate_id = prefix.split("_")[-1] if "_" in prefix else prefix

        return {
            "prefix": prefix,
            "well": well,
            "site": site,
            "channel": channel,
            "plate_id": plate_id
        }
    except Exception as e:
        logger.debug(f"Could not parse filename {filename}: {e}")
        return None


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Stitch and crop microscopy images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /data/experiment barcoding --crop-percent 25
  %(prog)s /data/experiment cellpainting --crop-percent 50 --no-compress
        """
    )

    # Required arguments
    parser.add_argument(
        "input_base",
        type=str,
        help="Base directory containing input images"
    )
    parser.add_argument(
        "track_type",
        type=str,
        help="Track type identifier (e.g., barcoding, cellpainting)"
    )

    # Optional arguments
    parser.add_argument(
        "--crop-percent",
        type=int,
        default=25,
        choices=[25, 50],
        help="Crop percentage (default: 25)"
    )
    parser.add_argument(
        "--grid-rows",
        type=int,
        default=2,
        help="Number of rows in site grid (default: 2)"
    )
    parser.add_argument(
        "--grid-cols",
        type=int,
        default=2,
        help="Number of columns in site grid (default: 2)"
    )
    parser.add_argument(
        "--overlap",
        type=float,
        default=10.0,
        help="Overlap percentage between tiles (default: 10.0)"
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.99,
        help="Scaling factor for stitched images (default: 1.99)"
    )
    parser.add_argument(
        "--tiles-per-side",
        type=int,
        default=2,
        help="Number of tiles to crop per side (default: 2)"
    )
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="Disable LZW compression for output TIFFs"
    )
    parser.add_argument(
        "--output-stitched",
        type=str,
        default=None,
        help="Output directory for stitched images (default: {input_base}/images_corrected_stitched/{track_type})"
    )
    parser.add_argument(
        "--output-cropped",
        type=str,
        default=None,
        help="Output directory for cropped images (default: {input_base}/images_corrected_cropped/{track_type})"
    )
    parser.add_argument(
        "--output-downsampled",
        type=str,
        default=None,
        help="Output directory for downsampled images (default: {input_base}/images_corrected_stitched_10X/{track_type})"
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default=None,
        help="Direct path to input images directory (overrides input_base/images_corrected/track_type structure)"
    )

    return parser.parse_args()


def main():
    """Main processing function."""
    # Parse arguments
    args = parse_args()

    input_base = args.input_base
    track_type = args.track_type
    crop_percent = args.crop_percent
    grid_rows = args.grid_rows
    grid_cols = args.grid_cols
    overlap_percent = args.overlap
    scale_factor = args.scale
    tiles_per_side = args.tiles_per_side
    compress = not args.no_compress

    # Configure dimensions based on crop percentage
    if crop_percent == 25:
        input_size = 400
        final_tile_size = 800
    elif crop_percent == 50:
        input_size = 800
        final_tile_size = 1600
    else:
        input_size = 1480
        final_tile_size = 2960

    logger.info(f"Configuration: crop={crop_percent}%, input={input_size}px, output={final_tile_size}px")

    # Setup paths
    if args.input_dir:
        input_dir = Path(args.input_dir)
        output_base = input_dir.parent.parent if len(input_dir.parts) > 2 else Path.cwd()
    else:
        input_dir = Path(input_base) / "images_corrected" / track_type
        output_base = Path(input_base)

    # Use custom output paths if provided, otherwise use defaults
    if args.output_stitched:
        stitched_base = Path(args.output_stitched)
    else:
        stitched_base = output_base / "images_corrected_stitched" / track_type

    if args.output_cropped:
        cropped_base = Path(args.output_cropped)
    else:
        cropped_base = output_base / "images_corrected_cropped" / track_type

    if args.output_downsampled:
        downsampled_base = Path(args.output_downsampled)
    else:
        downsampled_base = output_base / "images_corrected_stitched_10X" / track_type

    logger.info(f"Input: {input_dir}")
    logger.info(f"Output stitched: {stitched_base}")
    logger.info(f"Output cropped: {cropped_base}")
    logger.info(f"Output downsampled: {downsampled_base}")

    # Create output directories
    for base_dir in [stitched_base, cropped_base, downsampled_base]:
        base_dir.mkdir(parents=True, exist_ok=True)

    # Flatten directory structure (create symlinks if needed)
    tiff_count = 0
    for root, _, files in os.walk(input_dir):
        if root == str(input_dir):
            continue
        for filename in files:
            if filename.lower().endswith((".tif", ".tiff")):
                src = Path(root) / filename
                dst = input_dir / filename
                if not dst.exists():
                    dst.symlink_to(src)
                    tiff_count += 1

    logger.info(f"Created {tiff_count} symlinks")

    # Analyze input files
    files = list(input_dir.glob("*.tif*"))
    wells: Dict[str, str] = {}  # well -> plate_id
    channels: Dict[Tuple[str, str], str] = {}  # (prefix, channel) -> channel_suffix

    for file_path in files:
        metadata = parse_filename(file_path.name)
        if metadata:
            well = metadata["well"]
            plate_id = metadata["plate_id"]
            prefix = metadata["prefix"]
            channel = metadata["channel"]

            if well not in wells:
                wells[well] = plate_id

            if (prefix, channel) not in channels:
                channels[(prefix, channel)] = channel

    logger.info(f"Found {len(wells)} wells and {len(channels)} channels")

    # Initialize stitcher and processor
    stitcher = ImageStitcher(grid_rows=grid_rows, grid_cols=grid_cols, overlap_percent=overlap_percent)
    processor = ImageProcessor()

    # Process each well
    for well, plate_id in sorted(wells.items()):
        logger.info(f"Processing well {well} (plate {plate_id})")

        # Write directly to output directories (no subdirectories)
        well_stitched = stitched_base
        well_cropped = cropped_base
        well_downsampled = downsampled_base

        for d in [well_stitched, well_cropped, well_downsampled]:
            d.mkdir(parents=True, exist_ok=True)

        # Process each channel
        for (prefix, channel_suffix), _ in sorted(channels.items()):
            # Find all site images for this well and channel
            pattern = f"{prefix}_Well_{well}_Site_*_{channel_suffix}"
            site_files = sorted(input_dir.glob(pattern))

            expected_sites = grid_rows * grid_cols
            if len(site_files) != expected_sites:
                logger.warning(f"Expected {expected_sites} sites for {well}/{channel_suffix}, found {len(site_files)}")
                continue

            logger.info(f"  Stitching {channel_suffix} ({len(site_files)} sites)")

            # Stitch images
            stitched = stitcher.stitch_images(site_files)

            # Log actual stitched dimensions to verify correctness
            expected_stitched_size = grid_rows * input_size
            logger.info(
                f"=== Actual stitched dimensions: {stitched.shape[1]}x{stitched.shape[0]} "
                f"(expected ~{expected_stitched_size}x{expected_stitched_size}) ==="
            )

            # Scale image
            scaled = processor.scale_image(stitched, scale_factor=scale_factor)
            logger.info(
                f"  Scaled to: {scaled.shape[1]}x{scaled.shape[0]} "
                f"(factor={scale_factor})"
            )

            # Adjust canvas size
            stitched_size = grid_rows * input_size
            upscaled_size = int(round(stitched_size * scale_factor))
            upscaled_size = min(upscaled_size, 46340)  # ImageJ limit
            logger.info(f"  Target canvas size: {upscaled_size}x{upscaled_size}")

            final = processor.adjust_canvas(scaled, upscaled_size, position="top-left")

            # Save stitched image
            channel_name = channel_suffix.split(".")[0].lstrip("_")
            stitched_filename = f"Stitched_{channel_name}.tiff"
            processor.save_tiff(final, well_stitched / stitched_filename, compress=compress)

            # Crop into tiles
            tiles = processor.crop_into_tiles(final, tiles_per_side=tiles_per_side)

            # Create channel-specific subdirectory for tiles (matching Fiji behavior)
            channel_tile_dir = well_cropped / channel_name
            channel_tile_dir.mkdir(parents=True, exist_ok=True)

            # Save tiles to channel-specific subdirectory
            for idx, tile in enumerate(tiles, start=1):
                tile_filename = f"{channel_name}_Site_{idx}.tiff"
                processor.save_tiff(tile, channel_tile_dir / tile_filename, compress=compress)

            # Create downsampled version (10% size)
            downsampled = processor.scale_image(final, scale_factor=0.1)
            processor.save_tiff(downsampled, well_downsampled / stitched_filename, compress=compress)

            logger.info(f"  Completed {channel_suffix}")

    # Generate TileConfiguration.txt (for Fiji compatibility)
    tile_config_path = stitched_base / "TileConfiguration.txt"
    with open(tile_config_path, "w") as f:
        f.write("# Define the number of dimensions we are working on\n")
        f.write("dim = 2\n")
        f.write("\n")
        f.write("# Define the image coordinates (in pixels)\n")

        # Calculate effective tile positions based on overlap
        # This mimics what Fiji's Grid/Collection stitching generates
        overlap_pixels = int(input_size * overlap_percent / 100)
        effective_size = input_size - overlap_pixels

        tile_num = 0
        for row in range(grid_rows):
            for col in range(grid_cols):
                x_pos = col * effective_size
                y_pos = row * effective_size
                f.write(f"Site_{tile_num}.tif; ; ({x_pos}, {y_pos})\n")
                tile_num += 1

    logger.info(f"Generated TileConfiguration.txt at {tile_config_path}")
    logger.info("Processing complete!")
    logger.info(f"  Wells processed: {len(wells)}")
    logger.info(f"  Channels processed: {len(channels)}")


if __name__ == "__main__":
    main()
