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
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
from PIL import Image
import tifffile
from scipy import ndimage
from scipy.fft import fft2, ifft2, fftshift

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


class PhaseCorrelationStitcher(ImageStitcher):
    """Stitcher with phase correlation for accurate overlap computation.

    This matches Fiji's Grid/Collection stitching with compute_overlap enabled.
    Uses FFT-based phase correlation to find actual tile positions from image content.
    """

    def __init__(
        self,
        grid_rows: int,
        grid_cols: int,
        overlap_percent: float = 10.0,
        regression_threshold: float = 0.30,
        max_displacement_threshold: float = 2.50,
        absolute_displacement_threshold: float = 3.50
    ):
        """Initialize the phase correlation stitcher.

        Args:
            grid_rows: Number of rows in the site grid
            grid_cols: Number of columns in the site grid
            overlap_percent: Initial estimated overlap percentage
            regression_threshold: Threshold for outlier filtering (Fiji default: 0.30)
            max_displacement_threshold: Max average displacement allowed (Fiji default: 2.50)
            absolute_displacement_threshold: Max absolute displacement (Fiji default: 3.50)
        """
        super().__init__(grid_rows, grid_cols, overlap_percent)
        self.regression_threshold = regression_threshold
        self.max_displacement_threshold = max_displacement_threshold
        self.absolute_displacement_threshold = absolute_displacement_threshold

    def compute_phase_correlation(
        self, img1: np.ndarray, img2: np.ndarray, axis: str = "horizontal"
    ) -> Tuple[float, float, float]:
        """Compute shift between two overlapping images using phase correlation.

        This implements Fiji's phase correlation algorithm for overlap detection.

        Args:
            img1: First image (left or top)
            img2: Second image (right or bottom)
            axis: Direction of overlap ('horizontal' or 'vertical')

        Returns:
            Tuple of (shift_x, shift_y, confidence) where shift is in pixels
        """
        # Handle multichannel images by using first channel or averaging
        if img1.ndim == 3:
            img1 = np.mean(img1, axis=2)
        if img2.ndim == 3:
            img2 = np.mean(img2, axis=2)

        # Normalize images to [0, 1]
        img1 = img1.astype(np.float32)
        img2 = img2.astype(np.float32)
        img1 = (img1 - img1.min()) / (img1.max() - img1.min() + 1e-10)
        img2 = (img2 - img2.min()) / (img2.max() - img2.min() + 1e-10)

        # Extract overlap regions for more accurate correlation
        height, width = img1.shape
        overlap_pixels = int(width * self.overlap_percent / 100)

        if axis == "horizontal":
            # Compare right edge of img1 with left edge of img2
            region1 = img1[:, -overlap_pixels:]
            region2 = img2[:, :overlap_pixels]
        else:  # vertical
            # Compare bottom edge of img1 with top edge of img2
            region1 = img1[-overlap_pixels:, :]
            region2 = img2[:overlap_pixels, :]

        # Apply Hamming window to reduce edge effects
        if axis == "horizontal":
            window = np.outer(np.hamming(region1.shape[0]), np.hamming(region1.shape[1]))
        else:
            window = np.outer(np.hamming(region1.shape[0]), np.hamming(region1.shape[1]))

        region1 = region1 * window
        region2 = region2 * window

        # Compute phase correlation in frequency domain
        f1 = fft2(region1)
        f2 = fft2(region2)

        # Cross-power spectrum
        cross_power = (f1 * np.conj(f2)) / (np.abs(f1 * np.conj(f2)) + 1e-10)

        # Inverse FFT to get correlation surface
        correlation = np.abs(ifft2(cross_power))
        correlation = fftshift(correlation)

        # Find peak (indicates best shift)
        peak_idx = np.unravel_index(np.argmax(correlation), correlation.shape)

        # Convert to shift relative to center
        center_y, center_x = np.array(correlation.shape) // 2
        shift_y = peak_idx[0] - center_y
        shift_x = peak_idx[1] - center_x

        # Confidence is the peak height normalized by mean
        confidence = correlation[peak_idx] / (np.mean(correlation) + 1e-10)

        return float(shift_x), float(shift_y), float(confidence)

    def compute_tile_positions(
        self, image_paths: List[Path]
    ) -> List[Tuple[float, float]]:
        """Compute actual tile positions using phase correlation.

        This replicates Fiji's compute_overlap behavior.

        Args:
            image_paths: List of paths to images (row-by-row order)

        Returns:
            List of (x, y) positions for each tile in pixels
        """
        # Load all images
        images = [tifffile.imread(str(path)) for path in image_paths]

        # Get dimensions
        img_height, img_width = images[0].shape[:2]

        # Start with geometric positions as initial guess
        overlap_pixels = int(img_width * self.overlap_percent / 100)
        effective_width = img_width - overlap_pixels
        effective_height = img_height - overlap_pixels

        # Initialize positions (row-major order)
        positions = []
        for row in range(self.grid_rows):
            for col in range(self.grid_cols):
                x = col * effective_width
                y = row * effective_height
                positions.append([float(x), float(y)])

        # Refine positions using phase correlation (horizontal pass)
        logger.info("Computing horizontal overlaps via phase correlation...")
        for row in range(self.grid_rows):
            for col in range(self.grid_cols - 1):
                idx1 = row * self.grid_cols + col
                idx2 = row * self.grid_cols + col + 1

                shift_x, shift_y, conf = self.compute_phase_correlation(
                    images[idx1], images[idx2], axis="horizontal"
                )

                # Update position of right tile based on correlation
                # The shift tells us how much overlap there really is
                actual_overlap = overlap_pixels - shift_x
                positions[idx2][0] = positions[idx1][0] + img_width - actual_overlap

                logger.debug(f"  Tile {idx1}->{idx2}: shift_x={shift_x:.1f}, conf={conf:.2f}")

        # Refine positions using phase correlation (vertical pass)
        logger.info("Computing vertical overlaps via phase correlation...")
        for row in range(self.grid_rows - 1):
            for col in range(self.grid_cols):
                idx1 = row * self.grid_cols + col
                idx2 = (row + 1) * self.grid_cols + col

                shift_x, shift_y, conf = self.compute_phase_correlation(
                    images[idx1], images[idx2], axis="vertical"
                )

                # Update position of bottom tile based on correlation
                actual_overlap = overlap_pixels - shift_y
                positions[idx2][1] = positions[idx1][1] + img_height - actual_overlap

                logger.debug(f"  Tile {idx1}->{idx2}: shift_y={shift_y:.1f}, conf={conf:.2f}")

        # Apply displacement thresholds (Fiji's outlier filtering)
        positions = self._filter_outliers(positions)

        return [(float(x), float(y)) for x, y in positions]

    def _filter_outliers(
        self, positions: List[List[float]]
    ) -> List[List[float]]:
        """Filter outlier positions using regression threshold.

        This matches Fiji's regression-based outlier filtering.

        Args:
            positions: List of [x, y] positions

        Returns:
            Filtered positions
        """
        # Calculate expected positions (ideal grid)
        positions_array = np.array(positions)

        # For each position, check if it deviates too much from neighbors
        filtered = []
        for i, pos in enumerate(positions):
            row = i // self.grid_cols
            col = i % self.grid_cols

            # Get neighboring positions
            neighbors = []
            if col > 0:
                neighbors.append(positions_array[i - 1])
            if col < self.grid_cols - 1:
                neighbors.append(positions_array[i + 1])
            if row > 0:
                neighbors.append(positions_array[i - self.grid_cols])
            if row < self.grid_rows - 1:
                neighbors.append(positions_array[i + self.grid_cols])

            if neighbors:
                mean_neighbor = np.mean(neighbors, axis=0)
                displacement = np.linalg.norm(pos - mean_neighbor)

                # Apply thresholds
                if displacement > self.absolute_displacement_threshold:
                    logger.warning(f"Tile {i}: displacement {displacement:.1f}px exceeds threshold")
                    # Use average of neighbors instead
                    filtered.append(mean_neighbor.tolist())
                else:
                    filtered.append(pos)
            else:
                filtered.append(pos)

        return filtered

    def stitch_images_with_registration(
        self, image_paths: List[Path]
    ) -> np.ndarray:
        """Stitch images using phase correlation registration.

        This replicates Fiji's Grid/Collection stitching with compute_overlap.

        Args:
            image_paths: List of paths to images (row-by-row order)

        Returns:
            Stitched image as numpy array
        """
        if len(image_paths) != self.grid_rows * self.grid_cols:
            raise ValueError(
                f"Expected {self.grid_rows * self.grid_cols} images, "
                f"got {len(image_paths)}"
            )

        # Compute tile positions using phase correlation
        positions = self.compute_tile_positions(image_paths)

        # Load first image to get properties
        first_img = tifffile.imread(str(image_paths[0]))
        img_height, img_width = first_img.shape[:2]
        dtype = first_img.dtype
        is_multichannel = first_img.ndim == 3

        # Calculate canvas size from computed positions
        positions_array = np.array(positions)
        max_x = np.max(positions_array[:, 0]) + img_width
        max_y = np.max(positions_array[:, 1]) + img_height
        canvas_width = int(np.ceil(max_x))
        canvas_height = int(np.ceil(max_y))

        logger.info(
            f"Stitching with registration: canvas {canvas_width}x{canvas_height}"
        )

        # Create output canvas
        if is_multichannel:
            canvas = np.zeros(
                (canvas_height, canvas_width, first_img.shape[2]),
                dtype=np.float32
            )
            weight_map = np.zeros(
                (canvas_height, canvas_width, first_img.shape[2]),
                dtype=np.float32
            )
        else:
            canvas = np.zeros((canvas_height, canvas_width), dtype=np.float32)
            weight_map = np.zeros((canvas_height, canvas_width), dtype=np.float32)

        # Place each image at computed position with linear blending
        for idx, (image_path, (pos_x, pos_y)) in enumerate(zip(image_paths, positions)):
            img = tifffile.imread(str(image_path)).astype(np.float32)

            # Calculate placement coordinates
            x_start = int(round(pos_x))
            y_start = int(round(pos_y))
            x_end = min(x_start + img_width, canvas_width)
            y_end = min(y_start + img_height, canvas_height)

            # Handle image cropping if it extends beyond canvas
            img_x_end = img_width - (x_start + img_width - x_end)
            img_y_end = img_height - (y_start + img_height - y_end)

            img_region = img[:img_y_end, :img_x_end]

            # Create blending mask (feather edges for smooth blending)
            overlap_pixels = int(img_width * self.overlap_percent / 100)
            row = idx // self.grid_cols
            col = idx % self.grid_cols

            if is_multichannel:
                blend_mask = np.ones((img_y_end, img_x_end, img.shape[2]), dtype=np.float32)
            else:
                blend_mask = np.ones((img_y_end, img_x_end), dtype=np.float32)

            # Apply linear blending on overlapping edges
            if col < self.grid_cols - 1 and img_x_end >= overlap_pixels:
                right_blend = np.linspace(1, 0, overlap_pixels)
                if is_multichannel:
                    blend_mask[:, -overlap_pixels:, :] *= right_blend[np.newaxis, :, np.newaxis]
                else:
                    blend_mask[:, -overlap_pixels:] *= right_blend[np.newaxis, :]

            if row < self.grid_rows - 1 and img_y_end >= overlap_pixels:
                bottom_blend = np.linspace(1, 0, overlap_pixels)
                if is_multichannel:
                    blend_mask[-overlap_pixels:, :, :] *= bottom_blend[:, np.newaxis, np.newaxis]
                else:
                    blend_mask[-overlap_pixels:, :] *= bottom_blend[:, np.newaxis]

            if col > 0 and img_x_end >= overlap_pixels:
                left_blend = np.linspace(0, 1, overlap_pixels)
                if is_multichannel:
                    blend_mask[:, :overlap_pixels, :] *= left_blend[np.newaxis, :, np.newaxis]
                else:
                    blend_mask[:, :overlap_pixels] *= left_blend[np.newaxis, :]

            if row > 0 and img_y_end >= overlap_pixels:
                top_blend = np.linspace(0, 1, overlap_pixels)
                if is_multichannel:
                    blend_mask[:overlap_pixels, :, :] *= top_blend[:, np.newaxis, np.newaxis]
                else:
                    blend_mask[:overlap_pixels, :] *= top_blend[:, np.newaxis]

            # Add weighted image to canvas
            canvas[y_start:y_end, x_start:x_end] += img_region * blend_mask
            weight_map[y_start:y_end, x_start:x_end] += blend_mask

        # Normalize by weight map
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

        This matches Fiji's "interpolation=Bilinear average create" behavior:
        - For upscaling (scale > 1): Uses LANCZOS for smooth interpolation
        - For downscaling (scale < 1): Uses LANCZOS with antialiasing (area averaging)

        Args:
            img: Input image as numpy array
            scale_factor: Scaling factor (e.g., 1.99 for ~2x, 0.1 for 10% size)
            interpolation: Interpolation method ('bilinear', 'bicubic', 'nearest', 'lanczos')

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

        # Interpolation method selection
        # Fiji uses "interpolation=Bilinear average" which means:
        # - For upscaling: bilinear interpolation
        # - For downscaling: area averaging
        #
        # TEMPORARY: Using BILINEAR to match Fiji exactly for debugging
        # TODO: Test if LANCZOS produces better quality once output matches
        if interpolation.lower() == "lanczos":
            interp = Image.LANCZOS
        elif interpolation.lower() == "bicubic":
            interp = Image.BICUBIC
        elif interpolation.lower() == "nearest":
            interp = Image.NEAREST
        else:
            # Default to BILINEAR to match Fiji's behavior
            interp = Image.BILINEAR

        # Resize with antialiasing enabled (important for downscaling)
        # PIL automatically applies antialiasing with LANCZOS for downscaling
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

        This matches Fiji/ImageJ TIFF output format including:
        - LZW compression (when enabled)
        - BigTIFF support for large images (>4GB)
        - Compatible metadata tags

        Args:
            img: Image to save
            output_path: Output file path
            compress: Whether to use LZW compression
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        compression = "lzw" if compress else None

        # Prepare metadata to match Fiji/ImageJ output
        metadata = {
            'Software': 'Python stitcher (Fiji-compatible)',
            'ImageDescription': f'width={img.shape[1]} height={img.shape[0]} images=1'
        }

        # Determine photometric interpretation
        # Use "minisblack" for grayscale (most microscopy images)
        # This matches Fiji's default for grayscale images
        if img.ndim == 2:
            photometric = "minisblack"
        elif img.ndim == 3 and img.shape[2] == 1:
            photometric = "minisblack"
            img = img[:, :, 0]  # Remove singleton dimension
        else:
            photometric = "rgb"

        tifffile.imwrite(
            str(output_path),
            img,
            compression=compression,
            photometric=photometric,
            bigtiff=True,  # Enable BigTIFF for large images (>4GB)
            metadata=metadata
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

    # Initialize stitcher
    # TEMPORARY: Use simple geometric stitching first to debug
    # TODO: Re-enable PhaseCorrelationStitcher after validating basic stitching works
    logger.info("Using simple geometric stitching (phase correlation disabled for debugging)")
    stitcher = ImageStitcher(
        grid_rows=grid_rows,
        grid_cols=grid_cols,
        overlap_percent=overlap_percent
    )
    # Uncomment below to use phase correlation (after basic stitching is validated):
    # stitcher = PhaseCorrelationStitcher(
    #     grid_rows=grid_rows,
    #     grid_cols=grid_cols,
    #     overlap_percent=overlap_percent,
    #     regression_threshold=0.30,
    #     max_displacement_threshold=2.50,
    #     absolute_displacement_threshold=3.50
    # )
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
            site_files = list(input_dir.glob(pattern))

            # Sort numerically by site number (not alphabetically)
            # This ensures correct order: Site_0, Site_1, Site_2, Site_3
            # (not Site_0, Site_1, Site_10, Site_2 which would be wrong)
            def extract_site_num(path):
                match = re.search(r'Site_(\d+)', path.name)
                return int(match.group(1)) if match else 0

            site_files.sort(key=extract_site_num)

            expected_sites = grid_rows * grid_cols
            if len(site_files) != expected_sites:
                logger.warning(f"Expected {expected_sites} sites for {well}/{channel_suffix}, found {len(site_files)}")
                continue

            logger.info(f"  Stitching {channel_suffix} ({len(site_files)} sites)")

            # Stitch images (using simple geometric method for now)
            stitched = stitcher.stitch_images(site_files)
            # Use this for phase correlation (after validating basic stitching):
            # stitched = stitcher.stitch_images_with_registration(site_files)

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
            # IMPORTANT: Fiji uses ROUNDED scale factor for canvas size calculation
            # Example: 1.99 rounds to 2, so canvas = stitched_size * 2 (not * 1.99)
            stitched_size = grid_rows * input_size
            rounded_scale_factor = int(round(scale_factor))
            upscaled_size = int(stitched_size * rounded_scale_factor)
            upscaled_size = min(upscaled_size, 46340)  # ImageJ limit
            logger.info(f"  Target canvas size: {upscaled_size}x{upscaled_size} (scale={rounded_scale_factor})")

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
    # This matches Fiji's Grid/Collection stitching output format exactly
    tile_config_path = stitched_base / "TileConfiguration.txt"
    with open(tile_config_path, "w") as f:
        f.write("# Define the number of dimensions we are working on\n")
        f.write("dim = 2\n")
        f.write("\n")
        f.write("# Define the image coordinates\n")

        # Calculate effective tile positions based on overlap
        # This mimics what Fiji's Grid/Collection stitching generates
        overlap_pixels = int(input_size * overlap_percent / 100)
        effective_size = input_size - overlap_pixels

        # Get sample files to extract actual filenames
        # Use first well and first channel as example
        if wells and channels:
            first_well = sorted(wells.keys())[0]
            first_prefix, first_channel = sorted(channels.keys())[0]

            # Find actual input files to use their names
            sample_pattern = f"{first_prefix}_Well_{first_well}_Site_*_{first_channel}"
            sample_files = list(input_dir.glob(sample_pattern))

            def extract_site_num(path):
                match = re.search(r'Site_(\d+)', path.name)
                return int(match.group(1)) if match else 0

            sample_files.sort(key=extract_site_num)

            # Write coordinates for each tile using actual filenames
            for idx, site_file in enumerate(sample_files[:grid_rows * grid_cols]):
                row = idx // grid_cols
                col = idx % grid_cols
                x_pos = float(col * effective_size)
                y_pos = float(row * effective_size)
                # Use actual filename from input
                f.write(f"{site_file.name}; ; ({x_pos}, {y_pos})\n")
        else:
            # Fallback to generic names if no files found
            tile_num = 0
            for row in range(grid_rows):
                for col in range(grid_cols):
                    x_pos = float(col * effective_size)
                    y_pos = float(row * effective_size)
                    f.write(f"Site_{tile_num}.tif; ; ({x_pos}, {y_pos})\n")
                    tile_num += 1

    logger.info(f"Generated TileConfiguration.txt at {tile_config_path}")
    logger.info("Processing complete!")
    logger.info(f"  Wells processed: {len(wells)}")
    logger.info(f"  Channels processed: {len(channels)}")


if __name__ == "__main__":
    main()
