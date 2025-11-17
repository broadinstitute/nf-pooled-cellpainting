# ruff: noqa: ANN002,ANN003,ANN202,ANN204,ANN401,D100,D104,D202,D400,D413,D415,E501,F401,F541,F821,F841,I001,N803,N806,N816,PTH102,PTH104,PTH110,PTH112,PTH113,PTH114,PTH115,PTH118,PTH123,UP015,UP024,UP031,UP035,W605,E722
"""Master script for stitching and cropping microscopy images using ImageJ/Fiji.

IMPORTANT: This script runs in Jython 2.7 (Python 2-like) environment within Fiji/ImageJ.
Many Python 3+ features are NOT available:
- No f-strings (use .format() instead)
- No FileNotFoundError (use OSError/IOError instead)
- No pathlib (use os.path instead)
- No type hints
- Limited standard library support
Keep all code compatible with Python 2.7/Jython when making changes.

This script:
1. Takes multi-site microscopy images from each well
2. Stitches them together into a full well image
3. Crops the stitched image into tiles for analysis
4. Creates downsampled versions for quality control

Supports both square and round wells with configurable parameters via environment variables.

Environment Variables (all optional with sensible defaults):

Grid Layout:
  ROWS                   Number of rows in site grid (default: 2)
  COLUMNS                Number of columns in site grid (default: 2)

Image Dimensions (dataset-specific):
  SIZE                   Input tile size in pixels (default: 1480)
                         Common values:
                         - 1480: Real/production data (no crop)
                         - 800: 50% cropped test data
                         - 400: 25% cropped test data (fix-s1)
  FINAL_TILE_SIZE        Output tile size in pixels (default: 2960)
                         Common values:
                         - 2960: Real/production data
                         - 1600: 50% cropped test data
                         - 800: 25% cropped test data (fix-s1)

Stitching Parameters:
  OVERLAP_PCT            Percentage overlap between adjacent images (default: 10)
  SCALINGSTRING          Scaling factor to apply (default: 1.99)
  TILEPERSIDE            Number of tiles per side when cropping (default: 2)
  STITCHORDER            Grid stitching order (default: "Grid: snake by rows")
  FIRST_SITE_INDEX       Starting site number in filenames (default: 0)

Well Shape:
  ROUND_OR_SQUARE        Well shape: "square" or "round" (default: square)
  IMPERWELL              Number of images per well for round wells (e.g., 1364, 1332, 1396, etc.)
  QUARTER_IF_ROUND       Whether to quarter round wells: "true" or "false" (default: true)

Processing Options:
  COMPRESS               Use LZW compression: "True" or "False" (default: True)
  STITCH_AUTORUN         Auto-run mode, skip confirmations (default: False)

Advanced (Troubleshooting):
  XOFFSET_TILES          X offset for tile cropping in pixels (default: 0)
  YOFFSET_TILES          Y offset for tile cropping in pixels (default: 0)

Usage Examples:

  1. Real/production data (no crop):
     export SIZE=1480
     export FINAL_TILE_SIZE=2960
     export ROWS=2
     export COLUMNS=2
     python stitch_crop.master.py -y

  2. Test data with 25% crop (fix-s1):
     export SIZE=400
     export FINAL_TILE_SIZE=800
     export ROWS=2
     export COLUMNS=2
     python stitch_crop.master.py -y

  3. Test data with 50% crop:
     export SIZE=800
     export FINAL_TILE_SIZE=1600
     export ROWS=2
     export COLUMNS=2
     python stitch_crop.master.py -y

  4. Round wells (1364 images per well):
     export SIZE=1480
     export FINAL_TILE_SIZE=2960
     export ROUND_OR_SQUARE=round
     export IMPERWELL=1364
     export QUARTER_IF_ROUND=true
     python stitch_crop.master.py -y

Interactive Mode:
  - Run normally for interactive mode with confirmations:
    python stitch_crop.master.py

  - Run in automatic mode (skip all confirmations):
    python stitch_crop.master.py -y
    python stitch_crop.master.py --yes
    python stitch_crop.master.py auto

Nextflow Integration:
  - Input files are staged by Nextflow to images/
  - Outputs go to flat directories in work dir (Nextflow handles final organization)
  - All parameters can be set via environment variables
  - Auto-run mode is recommended for pipeline execution
"""

import os
import time
import logging
import sys
from ij import IJ
from loci.plugins import LociExporter
from loci.plugins.out import Exporter

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Handle command-line arguments
autorun = False
if len(sys.argv) > 1:
    if sys.argv[1].lower() in ("-y", "--yes", "yes", "auto"):
        autorun = True
        logger.info("Auto mode: All confirmations will be skipped")

# Check environment variable (for ImageJ/Fiji execution)
if os.getenv("STITCH_AUTORUN", "").lower() in ("true", "1", "yes", "auto"):
    autorun = True
    logger.info("Auto mode: All confirmations will be skipped (via env var)")


def confirm_continue(message="Continue to the next step?"):
    """Ask the user for confirmation to continue.

    Args:
        message: The message to display to the user

    Returns:
        bool: True if the user wants to continue, False otherwise
    """
    global autorun
    logger.info(">>> CONFIRM: " + message)

    # If autorun is enabled, skip confirmation and return True
    if autorun:
        logger.info("Auto-confirmed: Proceeding automatically")
        return True

    # Otherwise ask for confirmation
    response = input("Continue? (y/n): ").strip().lower()
    return response == "y" or response == "yes"


# Helper function to get required environment variables
def get_required_env(var_name):
    """Get a required environment variable or exit."""
    value = os.getenv(var_name)
    if not value:
        logger.error("{} environment variable is required".format(var_name))
        sys.exit(1)
    return value


# Configuration parameters - simplified for Nextflow integration
# Input files are staged by Nextflow to images/
# Outputs go to flat directories in work dir (Nextflow handles final organization)
input_dir = "images"  # Nextflow stages files here
output_base = "."  # Write outputs to work dir root
localtemp = "/tmp/FIJI_temp"  # Temporary directory

# Grid stitching parameters - read from environment
rows = os.getenv("ROWS", "2")  # Number of rows in the site grid
columns = os.getenv("COLUMNS", "2")  # Number of columns in the site grid

# Image dimensions - read from environment (dataset-agnostic)
# SIZE: Input tile size in pixels (before stitching)
# FINAL_TILE_SIZE: Output tile size in pixels (after cropping)
# These must be set appropriately for your dataset:
#   - Real data (no crop): SIZE=1480, FINAL_TILE_SIZE=2960
#   - 50% crop test data: SIZE=800, FINAL_TILE_SIZE=1600
#   - 25% crop test data (fix-s1): SIZE=400, FINAL_TILE_SIZE=800
size = os.getenv("SIZE", "1480")
final_tile_size = os.getenv("FINAL_TILE_SIZE", "2960")

logger.info(
    "Configuration: Input size={}x{}, Final tile size={}x{}".format(
        size, size, final_tile_size, final_tile_size
    )
)

# Stitching parameters - read from environment variables set by Nextflow
overlap_pct = os.getenv("OVERLAP_PCT", "10")  # Percentage overlap between adjacent images
round_or_square = os.getenv("ROUND_OR_SQUARE", "square")  # Shape of the well (square or round)
quarter_if_round = os.getenv("QUARTER_IF_ROUND", "true")  # Whether to quarter round wells

# Tiling parameters - read from environment
tileperside = os.getenv("TILEPERSIDE", "2")  # Number of tiles to create per side when cropping
scalingstring = os.getenv("SCALINGSTRING", "1.99")  # Scaling factor to apply to images
imperwell = os.getenv("IMPERWELL", "")  # Number of images per well (used if round)
stitchorder = os.getenv("STITCHORDER", "Grid: snake by rows")  # Grid stitching order

# Troubleshooting parameters - read from environment
xoffset_tiles = os.getenv("XOFFSET_TILES", "0")  # X offset for tile cropping
yoffset_tiles = os.getenv("YOFFSET_TILES", "0")  # Y offset for tile cropping
compress = os.getenv("COMPRESS", "True")  # Whether to compress output TIFF files
first_site_index = os.getenv("FIRST_SITE_INDEX", "0")  # Starting site number in filenames (e.g., 0 or 1)

# Channel information
channame = "DNA"  # Target channel name for processing (always DNA for this workflow)

# Unused parameters (kept for compatibility with data flow handled by Nextflow)
filterstring = "unused"
awsdownload = "unused"
bucketname = "unused"
downloadfilter = "unused"

# Log configuration
logger.info("=== Configuration ===")
logger.info("Input directory: {}".format(input_dir))
logger.info("Output base: {}".format(output_base))
logger.info("Channel: {}".format(channame))
logger.info("Grid: {}x{} with {}% overlap".format(rows, columns, overlap_pct))
logger.info("Round or Square: {}".format(round_or_square))
logger.info("Quarter if round: {}".format(quarter_if_round))
logger.info("Tiles per side: {}".format(tileperside))
logger.info("Scaling factor: {}".format(scalingstring))
logger.info("Stitch order: {}".format(stitchorder))
logger.info("First site index: {}".format(first_site_index))
logger.info("Compress output: {}".format(compress))

plugin = LociExporter()


def tiffextend(imname):
    """Ensure filename has proper TIFF extension.

    Args:
        imname: The image filename

    Returns:
        Filename with .tif or .tiff extension
    """
    if ".tif" in imname:
        return imname
    if "." in imname:
        return imname[: imname.index(".")] + ".tiff"
    else:
        return imname + ".tiff"


def savefile(im, imname, plugin, compress="false"):
    """Save an image with optional compression.

    Args:
        im: ImageJ ImagePlus object to save
        imname: Output filename/path
        plugin: LociExporter plugin instance
        compress: Whether to use LZW compression ("true" or "false")
    """
    attemptcount = 0
    imname = tiffextend(imname)
    logger.info("Saving {}, width={}, height={}".format(imname, im.width, im.height))

    # Simple save without compression
    if compress.lower() != "true":
        IJ.saveAs(im, "tiff", imname)
    # Save with compression (with retry logic)
    else:
        while attemptcount < 5:
            try:
                plugin.arg = (
                    "outfile="
                    + imname
                    + " windowless=true compression=LZW saveROI=false"
                )
                exporter = Exporter(plugin, im)
                exporter.run()
                logger.info("Succeeded after attempt {}".format(attemptcount))
                return
            except:
                attemptcount += 1
        logger.error("Failed 5 times at saving {}".format(imname))


# STEP 1: Create flat output directory structure (Nextflow handles final organization)
# Simplified structure: no nested arm/batch/plate subdirectories
outfolder = os.path.join(output_base, "stitched_images")  # For stitched images
tile_outdir = os.path.join(output_base, "cropped_images")  # For cropped tiles
downsample_outdir = os.path.join(output_base, "downsampled_images")  # For downsampled QC images

logger.info(
    "Output folders: \n - Stitched: {}\n - Cropped: {}\n - Downsampled: {}".format(
        outfolder, tile_outdir, downsample_outdir
    )
)

# Create output directories
if not os.path.exists(outfolder):
    os.mkdir(outfolder)
if not os.path.exists(tile_outdir):
    os.mkdir(tile_outdir)
if not os.path.exists(downsample_outdir):
    os.mkdir(downsample_outdir)

# STEP 2: Prepare input directory and files
logger.info("Input directory: {}".format(input_dir))

# bypassed awsdownload == 'True' for test (would download files from AWS)

# Check what's in the input directory
logger.info("Checking if directory exists: {}".format(input_dir))

# Use os.walk to recursively find all TIFF files at any depth
logger.info("Recursively searching for TIFF files to flatten directory structure")
tiff_count = 0
for root, dirs, files in os.walk(input_dir):
    # Skip the root directory itself
    if root == input_dir:
        continue

    for filename in files:
        # Process only TIFF files, skip CSVs and others
        if filename.lower().endswith((".tif", ".tiff")):
            src = os.path.join(root, filename)
            dst = os.path.join(input_dir, filename)

            # Check if destination exists
            if os.path.exists(dst) or os.path.islink(dst):
                logger.info("Destination already exists, skipping: {}".format(dst))
            else:
                logger.info("Creating symlink: {} -> {}".format(src, dst))
                os.symlink(src, dst)
                tiff_count += 1

logger.info("Created {} symlinks to TIFF files".format(tiff_count))

# Confirm completion of directory setup
if not confirm_continue("Directory setup complete. Proceed to analyze files?"):
    logger.info("Exiting at user request after directory setup")
    sys.exit(0)

# STEP 3: Analyze input files and organize by well and channel
if os.path.isdir(input_dir):
    logger.info("Processing directory content: {}".format(input_dir))
    dirlist = os.listdir(input_dir)
    logger.info("Files in directory: {}".format(dirlist))

    # Lists to track wells and prefix/suffix combinations
    welllist = []  # List of all well IDs found
    presuflist = []  # List of (prefix, channel) tuples
    well_to_plate = {}  # Mapping of well ID to plate ID
    plate_to_prefix = {}  # Mapping of plate ID to its filename prefix
    permprefix = None  # Track a permanent prefix for reference
    permsuffix = None  # Track a permanent suffix for reference

    # Parse each file to extract well information and channel information
    for eachfile in dirlist:
        if ".tif" in eachfile:
            logger.info("Processing TIFF file: {}".format(eachfile))
            # Skip overlay files
            if "Overlay" not in eachfile:
                try:
                    # Parse filename according to expected pattern:
                    # {prefix}_Well_{wellID}_Site_{siteNumber}_{channel}.tif
                    prefixBeforeWell, suffixWithWell = eachfile.split("_Well_")
                    Well, suffixAfterWell = suffixWithWell.split("_Site_")
                    logger.info(
                        "File parts: Prefix={}, Well={}, SuffixAfter={}".format(
                            prefixBeforeWell, Well, suffixAfterWell
                        )
                    )

                    # Extract channel suffix (part after the Site_#_ portion)
                    channelSuffix = suffixAfterWell[suffixAfterWell.index("_") + 1 :]
                    logger.info("Channel suffix: {}".format(channelSuffix))

                    # Track this prefix-channel combination if new
                    if (prefixBeforeWell, channelSuffix) not in presuflist:
                        presuflist.append((prefixBeforeWell, channelSuffix))
                        logger.info(
                            "Added to presuflist: {}".format(
                                (prefixBeforeWell, channelSuffix)
                            )
                        )

                    # Extract plate ID from the prefix (e.g., "Plate_Plate1" -> "Plate1")
                    plate_id = (
                        prefixBeforeWell.split("_")[-1]
                        if "_" in prefixBeforeWell
                        else prefixBeforeWell
                    )
                    logger.info("Extracted plate ID: {}".format(plate_id))

                    # Track this well if new
                    if Well not in welllist:
                        welllist.append(Well)
                        well_to_plate[Well] = plate_id
                        logger.info(
                            "Added to welllist: {} (plate: {})".format(Well, plate_id)
                        )

                    # Track plate-to-prefix mapping
                    if plate_id not in plate_to_prefix:
                        plate_to_prefix[plate_id] = prefixBeforeWell
                        logger.info(
                            "Plate {} uses prefix: {}".format(
                                plate_id, prefixBeforeWell
                            )
                        )

                    # If this file has our target channel, note its prefix/suffix
                    if channame in channelSuffix:
                        logger.info(
                            "Found target channel ({}) in {}".format(
                                channame, channelSuffix
                            )
                        )
                        if permprefix is None:
                            permprefix = prefixBeforeWell
                            permsuffix = channelSuffix
                            logger.info(
                                "Set permanent prefix: {} and suffix: {}".format(
                                    permprefix, permsuffix
                                )
                            )
                except Exception as e:
                    logger.error("Error processing file {}: {}".format(eachfile, e))

    # Filter out non-TIFF files from presuflist
    logger.info("Before filtering presuflist: {}".format(presuflist))
    for eachpresuf in presuflist:
        if eachpresuf[1][-4:] != ".tif":
            if eachpresuf[1][-5:] != ".tiff":
                presuflist.remove(eachpresuf)
                logger.info("Removed from presuflist: {}".format(eachpresuf))

    # Sort for consistent processing order
    presuflist.sort()
    logger.info("Final welllist: {}".format(welllist))
    logger.info("Final presuflist: {}".format(presuflist))
    logger.info(
        "Analysis complete - wells: {}, channels: {}".format(welllist, presuflist)
    )

    # Confirm proceeding after file analysis
    if not confirm_continue(
        "Found {} wells and {} channels. Proceed to stitching?".format(
            len(welllist), len(presuflist)
        )
    ):
        logger.info("Exiting at user request after file analysis")
        sys.exit(0)

    # STEP 4: Set up parameters for image stitching and cropping
    if round_or_square == "square":
        # Calculate image dimensions
        stitchedsize = int(rows) * int(size)  # Base size of the stitched image
        tileperside = int(tileperside)  # How many tiles to create per side
        scale_factor = float(scalingstring)  # Scaling factor to apply
        rounded_scale_factor = int(round(scale_factor))

        # Calculate the final image size after scaling
        upscaledsize = int(stitchedsize * rounded_scale_factor)
        # ImageJ has a size limit, so cap if needed
        if upscaledsize > 46340:
            upscaledsize = 46340

        # Calculate the size of each tile
        tilesize = int(upscaledsize / tileperside)

        # Confirm proceeding with stitching
        if not confirm_continue(
            "Setup complete. Ready to process {} wells and {} channels. Proceed with stitching?".format(
                len(welllist), len(presuflist)
            )
        ):
            logger.info("Exiting at user request before processing wells")
            sys.exit(0)

        # STEP 5: Process each well
        for eachwell in welllist:
            # Get the plate ID for this well
            plate_id = well_to_plate.get(eachwell, "UnknownPlate")

            # Simplified flat output structure - files go directly into output folders
            # Nextflow will handle final organization by plate/well
            # Use Plate-Well format for filenames (e.g., Plate1-A1)
            well_prefix = "{}-{}".format(plate_id, eachwell)  # e.g., "Plate1-A1"

            logger.info(
                "Processing well {} (plate {}) - prefix: {}".format(eachwell, plate_id, well_prefix)
            )

            # Create the instructions for ImageJ's Grid/Collection stitching plugin
            # This defines how images will be stitched together
            standard_grid_instructions = [
                # First part of the command with grid setup
                "type=[Grid: row-by-row] order=[Right & Down                ] grid_size_x="
                + rows
                + " grid_size_y="
                + columns
                + " tile_overlap="
                + overlap_pct
                + " first_file_index_i="
                + first_site_index
                + " directory="
                + input_dir
                + " file_names=",
                # Second part with stitching parameters
                " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]",
            ]
            # Confirm before processing this well
            if eachwell == welllist[0]:  # Only confirm on the first well
                if not confirm_continue(
                    "Ready to process well {} and all its channels. Proceed?".format(
                        eachwell
                    )
                ):
                    logger.info(
                        "Exiting at user request before processing well {}".format(
                            eachwell
                        )
                    )
                    sys.exit(0)

            # STEP 6: Process each channel for this well
            for eachpresuf in presuflist:  # for each channel
                # Extract the prefix and suffix (channel name)
                thisprefix, thissuffix = eachpresuf

                # Clean up the suffix to use as channel name
                thissuffixnicename = thissuffix.split(".")[0]
                if thissuffixnicename[0] == "_":
                    thissuffixnicename = thissuffixnicename[1:]

                # Set up the filename pattern for input images
                # The {i} will be replaced with site numbers (1, 2, 3, 4...)
                filename = thisprefix + "_Well_" + eachwell + "_Site_{i}_" + thissuffix

                # Set up output filenames with well prefix for flat structure
                # Format: Plate1-A1-DNA-Stitched.tiff
                fileoutname = "{}-{}-Stitched.tiff".format(well_prefix, thissuffixnicename)

                # STEP 7: Run the ImageJ stitching operation for this channel and well
                IJ.run(
                    "Grid/Collection stitching",
                    standard_grid_instructions[0]
                    + filename
                    + standard_grid_instructions[1],
                )
                # Get the resulting stitched image
                im = IJ.getImage()

                # Log the actual stitched image dimensions to verify correct size
                expected_size = int(rows) * int(size)
                logger.info(
                    "=== Actual stitched dimensions: {}x{} (expected ~{}x{}) ===".format(
                        im.width, im.height, expected_size, expected_size
                    )
                )

                # Calculate dimensions for scaling
                width = str(int(round(im.width * float(scalingstring))))
                height = str(int(round(im.height * float(scalingstring))))

                # Log progress of stitching
                logger.info(
                    "Stitching complete for {} - {}".format(eachwell, thissuffix)
                )

                # STEP 8: Scale the stitched image
                # This scales the barcoding and cell painting images to match each other
                logger.info(
                    "Scale... x={} y={} width={} height={} interpolation=Bilinear average create".format(
                        scalingstring, scalingstring, width, height
                    )
                )
                IJ.run(
                    "Scale...",
                    "x="
                    + scalingstring
                    + " y="
                    + scalingstring
                    + " width="
                    + width
                    + " height="
                    + height
                    + " interpolation=Bilinear average create",
                )

                im2 = IJ.getImage()

                # STEP 9: Adjust the canvas size
                # Padding ensures tiles are all the same size (for CellProfiler later on)
                logger.info(
                    "Canvas Size... width={} height={} position=Top-Left zero".format(
                        upscaledsize, upscaledsize
                    )
                )
                IJ.run(
                    "Canvas Size...",
                    "width="
                    + str(upscaledsize)
                    + " height="
                    + str(upscaledsize)
                    + " position=Top-Left zero",
                )
                # Wait for the operation to complete
                # TODO: Uncomment this after testing
                # time.sleep(15)
                im3 = IJ.getImage()

                # STEP 10: Save the stitched image to flat output directory
                stitched_filepath = os.path.join(outfolder, fileoutname)
                savefile(
                    im3,
                    stitched_filepath,
                    plugin,
                    compress=compress,
                )

                # Close all images and reopen the saved stitched image
                IJ.run("Close All")
                im = IJ.open(stitched_filepath)
                im = IJ.getImage()

                # Log progress
                logger.info(
                    "Scaling and saving complete for {} - {}".format(
                        eachwell, thissuffix
                    )
                )

                # STEP 11: Crop the stitched image into tiles
                for eachxtile in range(tileperside):
                    for eachytile in range(tileperside):
                        # Calculate the tile number (1-indexed, matching samplesheet)
                        each_tile_num = eachxtile * tileperside + eachytile + 1

                        # Select a rectangular region for this tile
                        # Apply offset to adjust tile positions if needed
                        IJ.makeRectangle(
                            eachxtile * tilesize + int(xoffset_tiles),  # X position
                            eachytile * tilesize + int(yoffset_tiles),  # Y position
                            tilesize,  # Width
                            tilesize,  # Height
                        )

                        # Crop the selected region
                        im_tile = im.crop()

                        # Save the cropped tile with new naming pattern
                        # Format: Plate_Plate1_Well_A1_Site_1_DNA.tiff
                        # Site number matches the samplesheet (no conversion)
                        tile_filename = "Plate_{}_Well_{}_Site_{}_{}.tiff".format(
                            plate_id,
                            eachwell,
                            each_tile_num,  # Use site number directly from samplesheet
                            thissuffixnicename
                        )
                        savefile(
                            im_tile,
                            os.path.join(tile_outdir, tile_filename),
                            plugin,
                            compress=compress,
                        )

                # Close all images and reopen the saved stitched image
                IJ.run("Close All")
                im = IJ.open(stitched_filepath)
                im = IJ.getImage()

                # STEP 12: Create downsampled version for quality control
                logger.info(
                    "Scale... x=0.1 y=0.1 width={} height={} interpolation=Bilinear average create".format(
                        im.width / 10, im.width / 10
                    )
                )
                # Scale down to 10% of original size
                im_10 = IJ.run(
                    "Scale...",
                    "x=0.1 y=0.1 width="
                    + str(im.width / 10)
                    + " height="
                    + str(im.width / 10)
                    + " interpolation=Bilinear average create",
                )
                im_10 = IJ.getImage()

                # Save the downsampled image to flat output directory
                savefile(
                    im_10,
                    os.path.join(downsample_outdir, fileoutname),
                    plugin,
                    compress=compress,
                )

                # Log crop and downsample completion
                logger.info(
                    "Cropping and downsampling complete for {} - {}".format(
                        eachwell, thissuffix
                    )
                )

                # Close all open images before next iteration
                IJ.run("Close All")

    # STEP 4b: Process round wells
    elif round_or_square == "round":
        logger.info("Processing round wells")

        # Define row_widths based on images per well
        if imperwell == "1364":
            row_widths = [8,14,18,22,26,28,30,
            32,34,34,36,36,38,38,
            40,40,40,42,42,42,42,
            42,42,42,42,40,40,40,
            38,38,36,36,34,34,32,
            30,28,26,22,18,14,8]
        elif imperwell == "1332":
            row_widths = [14,18,22,26,28,30,
            32,34,34,36,36,38,38,
            40,40,40,40,40,40,40,
            40,40,40,40,40,40,40,
            38,38,36,36,34,34,32,
            30,28,26,22,18,14]
        elif imperwell == "1396":
            row_widths = [18,22,26,28,30,
            32,34,36,36,38,38,
            40,40,40,40,40,40,40,40,40,
            40,40,40,40,40,40,40,40,40,
            38,38,36,36,34,32,
            30,28,26,22,18]
        elif imperwell == "394":
            row_widths = [3,7,9,11,11,
            13,13,15,15,15,
            17,17,17,17,17,17,17,17,17,17,
            15,15,15,13,13,11,11,9,7,3]
        elif imperwell == "320":
            row_widths = [4, 8, 12, 14, 16,
            18, 18, 20, 20, 20,
            20, 20, 20, 20, 18,
            18, 16, 14, 12, 8, 4]
        elif imperwell == "316":
            row_widths = [6, 10, 14, 16, 16,
            18, 18, 20, 20, 20,
            20, 20, 20, 18, 18,
            16, 16, 14, 10, 6]
        elif imperwell == "293":
            row_widths = [7, 11, 13, 15, 17, 17,
            19, 19, 19, 19, 19, 19, 19, 17, 17,
            15, 13, 11, 7]
        elif imperwell == "88":
            row_widths = [6, 8, 10, 10, 10, 10, 10, 10, 8, 6]
        elif imperwell == "256":
            row_widths = [6,10,12,14,16,16,18,18,18,18,18,18,16,16,14,12,10,6]
        elif imperwell == "52":
            row_widths = [4,6,8,8,8,8,6,4]
        elif imperwell == "56":
            row_widths = [2, 6, 8, 8, 8, 8, 8, 6, 2]
        elif imperwell == "45":
            row_widths = [5,7,7,7,7,7,5]
        else:
            logger.error("{} images/well for a round well is not currently supported".format(imperwell))
            sys.exit(1)

        rows = str(len(row_widths))
        columns = str(max(row_widths))

        tileperside = int(tileperside)
        tilesize = int(final_tile_size)
        scale_factor = float(scalingstring)
        rounded_scale_factor = int(round(scale_factor))

        if quarter_if_round.lower() == "true":
            # xoffset_tiles and yoffset_tiles can be used if you need to adjust the "where to draw the line between quarters"
            # by a whole tile. You may want to add more padding if you do this
            top_rows = str((int(rows)/2)+int(yoffset_tiles))
            left_columns = str((int(columns)/2)+int(xoffset_tiles))
            bot_rows = str(int(rows)-int(top_rows))
            right_columns = str(int(columns)-int(left_columns))
            # For upscaled row and column size, we're always going to use the biggest number
            max_val = max(int(top_rows),int(bot_rows),int(left_columns),int(right_columns))
            upscaled_row_size = int(size)*max_val*rounded_scale_factor
            tiles_per_quarter = int(tileperside)/2
            if tilesize * tiles_per_quarter > upscaled_row_size:
                upscaled_row_size = tilesize * tiles_per_quarter
            upscaled_col_size = upscaled_row_size
            pixels_to_crop = int(round(int(size)*float(overlap_pct)/200))
        else:
            max_val = max(int(rows), int(columns))
            upscaled_row_size = int(size)*max_val*rounded_scale_factor
            if tilesize * tileperside > upscaled_row_size:
                upscaled_row_size = tilesize * tileperside
            upscaled_col_size = upscaled_row_size

        # Create position dictionary for round wells
        pos_dict = {}
        count = 0
        for row in range(len(row_widths)):
            row_width = row_widths[row]
            left_pos = int((int(columns)-row_width)/2)
            for col in range(row_width):
                if row%2 == 0:
                    pos_dict[(int(left_pos + col), row)] = str(count)
                    count += 1
                else:
                    right_pos = left_pos + row_width - 1
                    pos_dict[(int(right_pos - col), row)]= str(count)
                    count += 1

        filled_positions = pos_dict.keys()
        emptylist = []

        # Process each well
        for eachwell in welllist:
            plate_id = well_to_plate.get(eachwell, "UnknownPlate")
            well_prefix = "{}-{}".format(plate_id, eachwell)

            logger.info("Processing round well {} (plate {})".format(eachwell, plate_id))

            # Rename files to grid format and fill empty positions with noise
            for eachpresuf in presuflist:
                thisprefix, thissuffix = eachpresuf
                for x in range(int(columns)):
                    for y in range(int(rows)):
                        out_name = thisprefix+'_Well_'+eachwell+'_x_'+ '%02d'%x+'_y_'+'%02d'%y+ '_'+ thissuffix
                        if (x,y) in filled_positions:
                            series = pos_dict[(x,y)]
                            in_name = thisprefix+'_Well_'+eachwell+'_Site_'+str(series)+'_'+thissuffix
                            IJ.open(os.path.join(input_dir,in_name))
                        else:
                            IJ.newImage("Untitled", "16-bit noise",int(size),int(size), 1)
                            IJ.run("Divide...", "value=100")
                            emptylist.append(out_name)
                        im = IJ.getImage()
                        IJ.saveAs(im,'tiff',os.path.join(input_dir, out_name))
                        IJ.run("Close All")
                        if (x,y) in filled_positions:
                            try:
                                os.remove(os.path.join(input_dir,in_name))
                            except:
                                pass
                logger.info("Renamed all files for prefix {} and suffix {} in well {}".format(thisprefix, thissuffix, eachwell))

            if quarter_if_round.lower() == "false":
                # Process whole well (no quartering)
                logger.info("Stitching whole round well")
                standard_grid_instructions=["type=[Filename defined position] order=[Defined by filename         ] grid_size_x="+str(columns)+" grid_size_y="+str(rows)+" tile_overlap="+overlap_pct+" first_file_index_x=0 first_file_index_y=0 directory="+input_dir+" file_names=",
                " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"]
                copy_grid_instructions="type=[Positions from file] order=[Defined by TileConfiguration] directory="+input_dir+" layout_file=TileConfiguration.registered_copy.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 ignore_z_stage computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"
                filename=permprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+permsuffix
                fileoutname = "{}-{}-Stitched.tiff".format(well_prefix, "DNA")
                instructions = standard_grid_instructions[0] + filename + standard_grid_instructions[1]
                logger.info("Running stitching: {}".format(instructions))
                IJ.run("Grid/Collection stitching", instructions)
                im=IJ.getImage()
                if compress.lower()!='true':
                    savefile(im,os.path.join(outfolder,fileoutname),plugin,compress=compress)
                time.sleep(60)
                IJ.run("Close All")

                # Process each channel
                for eachpresuf in presuflist:
                    thisprefix, thissuffix=eachpresuf
                    thissuffixnicename = thissuffix.split('.')[0]
                    if thissuffixnicename[0]=='_':
                        thissuffixnicename=thissuffixnicename[1:]

                    filename=thisprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+thissuffix
                    fileoutname = "{}-{}-Stitched.tiff".format(well_prefix, thissuffixnicename)

                    with open(os.path.join(input_dir, 'TileConfiguration.registered.txt'),'r') as infile:
                        with open(os.path.join(input_dir, 'TileConfiguration.registered_copy.txt'),'w') as outfile:
                            for line in infile:
                                line=line.replace(permprefix,thisprefix)
                                line=line.replace(permsuffix,thissuffix)
                                outfile.write(line)

                    IJ.run("Grid/Collection stitching", copy_grid_instructions)
                    im=IJ.getImage()
                    width = str(int(round(im.width*float(scalingstring))))
                    height = str(int(round(im.height*float(scalingstring))))
                    logger.info("Scale... x={} y={} width={} height={}".format(scalingstring, scalingstring, width, height))
                    IJ.run("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                    time.sleep(15)
                    im2=IJ.getImage()
                    logger.info("Canvas Size... width={} height={}".format(upscaled_col_size, upscaled_row_size))
                    IJ.run("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Top-Left zero")
                    time.sleep(15)
                    im3=IJ.getImage()
                    savefile(im3,os.path.join(outfolder,fileoutname),plugin,compress=compress)
                    im=IJ.getImage()

                    # Downsample
                    logger.info("Scale... x=0.1 y=0.1")
                    im_10=IJ.run("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                    im_10=IJ.getImage()
                    savefile(im_10,os.path.join(downsample_outdir,fileoutname),plugin,compress=compress)
                    IJ.run("Close All")
                    im=IJ.open(os.path.join(outfolder,fileoutname))
                    im = IJ.getImage()

                    # Crop into tiles
                    for eachxtile in range(tileperside):
                        for eachytile in range(tileperside):
                            each_tile_num = eachxtile*tileperside + eachytile + 1
                            IJ.makeRectangle(eachxtile*tilesize, eachytile*tilesize,tilesize,tilesize)
                            im_tile=im.crop()
                            tile_filename = "Plate_{}_Well_{}_Site_{}_{}.tiff".format(
                                plate_id, eachwell, each_tile_num, thissuffixnicename
                            )
                            savefile(im_tile,os.path.join(tile_outdir,tile_filename),plugin,compress=compress)
                    IJ.run("Close All")

            else:
                # Process well in quarters
                logger.info("Processing round well in quarters")

                # Top left quarter
                logger.info("Running top left quarter")
                standard_grid_instructions=["type=[Filename defined position] order=[Defined by filename         ] grid_size_x="+str(left_columns)+" grid_size_y="+top_rows+" tile_overlap="+overlap_pct+" first_file_index_x=0 first_file_index_y=0 directory="+input_dir+" file_names=",
                " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"]
                copy_grid_instructions="type=[Positions from file] order=[Defined by TileConfiguration] directory="+input_dir+" layout_file=TileConfiguration.registered_copy.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 ignore_z_stage computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"
                filename=permprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+permsuffix
                fileoutname_tl = "{}-{}-StitchedTopLeft.tiff".format(well_prefix, "DNA")
                instructions = standard_grid_instructions[0] + filename + standard_grid_instructions[1]
                IJ.run("Grid/Collection stitching", instructions)
                im=IJ.getImage()
                if compress.lower()!='true':
                    savefile(im,os.path.join(outfolder,fileoutname_tl),plugin,compress=compress)
                IJ.run("Close All")

                for eachpresuf in presuflist:
                    thisprefix, thissuffix=eachpresuf
                    thissuffixnicename = thissuffix.split('.')[0]
                    if thissuffixnicename[0]=='_':
                        thissuffixnicename=thissuffixnicename[1:]

                    filename=thisprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+thissuffix
                    fileoutname_tl = "{}-{}-StitchedTopLeft.tiff".format(well_prefix, thissuffixnicename)

                    with open(os.path.join(input_dir, 'TileConfiguration.registered.txt'),'r') as infile:
                        with open(os.path.join(input_dir, 'TileConfiguration.registered_copy.txt'),'w') as outfile:
                            for line in infile:
                                if not any([empty in line for empty in emptylist]):
                                    line=line.replace(permprefix,thisprefix)
                                    line=line.replace(permsuffix,thissuffix)
                                    outfile.write(line)

                    IJ.run("Grid/Collection stitching", copy_grid_instructions)
                    im0=IJ.getImage()
                    # Chop off bottom and right
                    IJ.makeRectangle(0,0,im0.width-pixels_to_crop,im0.height-pixels_to_crop)
                    im1=im0.crop()
                    width = str(int(round(im1.width*float(scalingstring))))
                    height = str(int(round(im1.height*float(scalingstring))))
                    IJ.run("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                    time.sleep(15)
                    im2=IJ.getImage()
                    IJ.run("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Bottom-Right zero")
                    time.sleep(15)
                    im3=IJ.getImage()
                    savefile(im3,os.path.join(outfolder,fileoutname_tl),plugin,compress=compress)
                    im=IJ.getImage()
                    im_10=IJ.run("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                    im_10=IJ.getImage()
                    savefile(im_10,os.path.join(downsample_outdir,fileoutname_tl),plugin,compress=compress)
                    IJ.run("Close All")
                    im=IJ.open(os.path.join(outfolder,fileoutname_tl))
                    im = IJ.getImage()
                    tile_offset = upscaled_row_size - (tilesize * tiles_per_quarter)
                    for eachxtile in range(tiles_per_quarter):
                        for eachytile in range(tiles_per_quarter):
                            each_tile_num = eachxtile*int(tileperside) + eachytile + 1
                            IJ.makeRectangle((eachxtile*tilesize)+tile_offset, (eachytile*tilesize)+tile_offset,tilesize,tilesize)
                            im_tile=im.crop()
                            tile_filename = "Plate_{}_Well_{}_Site_{}_{}.tiff".format(
                                plate_id, eachwell, each_tile_num, thissuffixnicename
                            )
                            savefile(im_tile,os.path.join(tile_outdir,tile_filename),plugin,compress=compress)
                    IJ.run("Close All")

                # Top right quarter
                logger.info("Running top right quarter")
                standard_grid_instructions=["type=[Filename defined position] order=[Defined by filename         ] grid_size_x="+str(right_columns)+" grid_size_y="+top_rows+" tile_overlap="+overlap_pct+" first_file_index_x="+str(left_columns)+" first_file_index_y=0 directory="+input_dir+" file_names=",
                " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"]
                filename=permprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+permsuffix
                fileoutname_tr = "{}-{}-StitchedTopRight.tiff".format(well_prefix, "DNA")
                IJ.run("Grid/Collection stitching", standard_grid_instructions[0] + filename + standard_grid_instructions[1])
                im=IJ.getImage()
                if compress.lower()!='true':
                    savefile(im,os.path.join(outfolder,fileoutname_tr),plugin,compress=compress)
                IJ.run("Close All")

                for eachpresuf in presuflist:
                    thisprefix, thissuffix=eachpresuf
                    thissuffixnicename = thissuffix.split('.')[0]
                    if thissuffixnicename[0]=='_':
                        thissuffixnicename=thissuffixnicename[1:]

                    filename=thisprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+thissuffix
                    fileoutname_tr = "{}-{}-StitchedTopRight.tiff".format(well_prefix, thissuffixnicename)

                    with open(os.path.join(input_dir, 'TileConfiguration.registered.txt'),'r') as infile:
                        with open(os.path.join(input_dir, 'TileConfiguration.registered_copy.txt'),'w') as outfile:
                            for line in infile:
                                if not any([empty in line for empty in emptylist]):
                                    line=line.replace(permprefix,thisprefix)
                                    line=line.replace(permsuffix,thissuffix)
                                    outfile.write(line)

                    IJ.run("Grid/Collection stitching", copy_grid_instructions)
                    im0=IJ.getImage()
                    # Chop off bottom and left
                    IJ.makeRectangle(pixels_to_crop,0,im0.width-pixels_to_crop,im0.height-pixels_to_crop)
                    im1=im0.crop()
                    width = str(int(round(im1.width*float(scalingstring))))
                    height = str(int(round(im1.height*float(scalingstring))))
                    IJ.run("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                    time.sleep(15)
                    im2=IJ.getImage()
                    IJ.run("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Bottom-Left zero")
                    time.sleep(15)
                    im3=IJ.getImage()
                    savefile(im3,os.path.join(outfolder,fileoutname_tr),plugin,compress=compress)
                    im=IJ.getImage()
                    im_10=IJ.run("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                    im_10=IJ.getImage()
                    savefile(im_10,os.path.join(downsample_outdir,fileoutname_tr),plugin,compress=compress)
                    IJ.run("Close All")
                    im=IJ.open(os.path.join(outfolder,fileoutname_tr))
                    im = IJ.getImage()
                    tile_offset = upscaled_row_size - (tilesize * tiles_per_quarter)
                    for eachxtile in range(tiles_per_quarter):
                        for eachytile in range(tiles_per_quarter):
                            each_tile_num = int(tiles_per_quarter)*int(tileperside)+ eachxtile*int(tileperside) + eachytile + 1
                            IJ.makeRectangle((eachxtile*tilesize), (eachytile*tilesize)+tile_offset,tilesize,tilesize)
                            im_tile=im.crop()
                            tile_filename = "Plate_{}_Well_{}_Site_{}_{}.tiff".format(
                                plate_id, eachwell, each_tile_num, thissuffixnicename
                            )
                            savefile(im_tile,os.path.join(tile_outdir,tile_filename),plugin,compress=compress)
                    IJ.run("Close All")

                # Bottom left quarter
                logger.info("Running bottom left quarter")
                standard_grid_instructions=["type=[Filename defined position] order=[Defined by filename         ] grid_size_x="+str(left_columns)+" grid_size_y="+bot_rows+" tile_overlap="+overlap_pct+" first_file_index_x=0 first_file_index_y="+top_rows+" directory="+input_dir+" file_names=",
                " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"]
                filename=permprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+permsuffix
                fileoutname_bl = "{}-{}-StitchedBottomLeft.tiff".format(well_prefix, "DNA")
                IJ.run("Grid/Collection stitching", standard_grid_instructions[0] + filename + standard_grid_instructions[1])
                im=IJ.getImage()
                if compress.lower()!='true':
                    savefile(im,os.path.join(outfolder,fileoutname_bl),plugin,compress=compress)
                IJ.run("Close All")

                for eachpresuf in presuflist:
                    thisprefix, thissuffix=eachpresuf
                    thissuffixnicename = thissuffix.split('.')[0]
                    if thissuffixnicename[0]=='_':
                        thissuffixnicename=thissuffixnicename[1:]

                    filename=thisprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+thissuffix
                    fileoutname_bl = "{}-{}-StitchedBottomLeft.tiff".format(well_prefix, thissuffixnicename)

                    with open(os.path.join(input_dir, 'TileConfiguration.registered.txt'),'r') as infile:
                        with open(os.path.join(input_dir, 'TileConfiguration.registered_copy.txt'),'w') as outfile:
                            for line in infile:
                                if not any([empty in line for empty in emptylist]):
                                    line=line.replace(permprefix,thisprefix)
                                    line=line.replace(permsuffix,thissuffix)
                                    outfile.write(line)

                    IJ.run("Grid/Collection stitching", copy_grid_instructions)
                    im0=IJ.getImage()
                    # Chop off top and right
                    IJ.makeRectangle(0,pixels_to_crop,im0.width-pixels_to_crop,im0.height-pixels_to_crop)
                    im1=im0.crop()
                    width = str(int(round(im1.width*float(scalingstring))))
                    height = str(int(round(im1.height*float(scalingstring))))
                    IJ.run("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                    time.sleep(15)
                    im2=IJ.getImage()
                    IJ.run("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Top-Right zero")
                    time.sleep(15)
                    im3=IJ.getImage()
                    savefile(im3,os.path.join(outfolder,fileoutname_bl),plugin,compress=compress)
                    im=IJ.getImage()
                    im_10=IJ.run("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                    im_10=IJ.getImage()
                    savefile(im_10,os.path.join(downsample_outdir,fileoutname_bl),plugin,compress=compress)
                    IJ.run("Close All")
                    im=IJ.open(os.path.join(outfolder,fileoutname_bl))
                    im = IJ.getImage()
                    tile_offset = upscaled_row_size - (tilesize * tiles_per_quarter)
                    for eachxtile in range(tiles_per_quarter):
                        for eachytile in range(tiles_per_quarter):
                            each_tile_num = eachxtile*int(tileperside) + int(tiles_per_quarter) + eachytile + 1
                            IJ.makeRectangle((eachxtile*tilesize)+tile_offset, (eachytile*tilesize),tilesize,tilesize)
                            im_tile=im.crop()
                            tile_filename = "Plate_{}_Well_{}_Site_{}_{}.tiff".format(
                                plate_id, eachwell, each_tile_num, thissuffixnicename
                            )
                            savefile(im_tile,os.path.join(tile_outdir,tile_filename),plugin,compress=compress)
                    IJ.run("Close All")

                # Bottom right quarter
                logger.info("Running bottom right quarter")
                standard_grid_instructions=["type=[Filename defined position] order=[Defined by filename         ] grid_size_x="+str(right_columns)+" grid_size_y="+bot_rows+" tile_overlap="+overlap_pct+" first_file_index_x="+str(left_columns)+" first_file_index_y="+top_rows+" directory="+input_dir+" file_names=",
                " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"]
                filename=permprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+permsuffix
                fileoutname_br = "{}-{}-StitchedBottomRight.tiff".format(well_prefix, "DNA")
                IJ.run("Grid/Collection stitching", standard_grid_instructions[0] + filename + standard_grid_instructions[1])
                im=IJ.getImage()
                if compress.lower()!='true':
                    savefile(im,os.path.join(outfolder,fileoutname_br),plugin,compress=compress)
                IJ.run("Close All")

                for eachpresuf in presuflist:
                    thisprefix, thissuffix=eachpresuf
                    thissuffixnicename = thissuffix.split('.')[0]
                    if thissuffixnicename[0]=='_':
                        thissuffixnicename=thissuffixnicename[1:]

                    filename=thisprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+thissuffix
                    fileoutname_br = "{}-{}-StitchedBottomRight.tiff".format(well_prefix, thissuffixnicename)

                    with open(os.path.join(input_dir, 'TileConfiguration.registered.txt'),'r') as infile:
                        with open(os.path.join(input_dir, 'TileConfiguration.registered_copy.txt'),'w') as outfile:
                            for line in infile:
                                if not any([empty in line for empty in emptylist]):
                                    line=line.replace(permprefix,thisprefix)
                                    line=line.replace(permsuffix,thissuffix)
                                    outfile.write(line)

                    IJ.run("Grid/Collection stitching", copy_grid_instructions)
                    im0=IJ.getImage()
                    # Chop off top and left
                    IJ.makeRectangle(pixels_to_crop,pixels_to_crop,im0.width-pixels_to_crop,im0.height-pixels_to_crop)
                    im1=im0.crop()
                    width = str(int(round(im1.width*float(scalingstring))))
                    height = str(int(round(im1.height*float(scalingstring))))
                    IJ.run("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                    time.sleep(15)
                    im2=IJ.getImage()
                    IJ.run("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Top-Left zero")
                    time.sleep(15)
                    im3=IJ.getImage()
                    savefile(im3,os.path.join(outfolder,fileoutname_br),plugin,compress=compress)
                    im=IJ.getImage()
                    im_10=IJ.run("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                    im_10=IJ.getImage()
                    savefile(im_10,os.path.join(downsample_outdir,fileoutname_br),plugin,compress=compress)
                    IJ.run("Close All")
                    im=IJ.open(os.path.join(outfolder,fileoutname_br))
                    im = IJ.getImage()
                    tile_offset = upscaled_row_size - (tilesize * tiles_per_quarter)
                    for eachxtile in range(tiles_per_quarter):
                        for eachytile in range(tiles_per_quarter):
                            each_tile_num = int(tiles_per_quarter)*int(tileperside) +eachxtile*int(tileperside)+ int(tiles_per_quarter) + eachytile + 1
                            IJ.makeRectangle((eachxtile*tilesize), (eachytile*tilesize),tilesize,tilesize)
                            im_tile=im.crop()
                            tile_filename = "Plate_{}_Well_{}_Site_{}_{}.tiff".format(
                                plate_id, eachwell, each_tile_num, thissuffixnicename
                            )
                            savefile(im_tile,os.path.join(tile_outdir,tile_filename),plugin,compress=compress)
                    IJ.run("Close All")

    else:
        logger.error("Must identify well as round or square")
        sys.exit(1)
else:
    logger.error("Could not find input directory {}".format(input_dir))
    sys.exit(1)

# STEP 13: Move the TileConfiguration.txt file to the output directory
# Note: This file gets overwritten for each well, so we just keep the last one
for eachlogfile in ["TileConfiguration.txt"]:
    try:
        # Move to the stitched images output folder
        os.rename(
            os.path.join(input_dir, eachlogfile),
            os.path.join(outfolder, eachlogfile),
        )
        logger.info("Moved {} to output directory".format(eachlogfile))
    except (OSError, IOError):  # Python 2/Jython compatibility
        logger.warning("Could not find TileConfiguration.txt in {}".format(input_dir))
        # Create an empty file if it doesn't exist (for testing purposes)
        if not os.path.exists(os.path.join(outfolder, eachlogfile)):
            with open(os.path.join(outfolder, eachlogfile), "w") as f:
                f.write("# This is a placeholder file\n")
            logger.info("Created empty {} in output directory".format(eachlogfile))

# Final confirmation
logger.info("Processing complete")
# In autorun mode, always show summary
if autorun or confirm_continue(
    "All processing is complete. Would you like to see a summary?"
):
    logger.info("======== PROCESSING SUMMARY =========")
    logger.info("Input directory: {}".format(input_dir))
    logger.info("Stitched images: {}".format(outfolder))
    logger.info("Cropped tiles: {}".format(tile_outdir))
    logger.info("Downsampled QC images: {}".format(downsample_outdir))
    logger.info("Wells processed: {}".format(welllist))
    logger.info("Channels processed: {}".format([s[1] for s in presuflist]))
    logger.info("=====================================")

logger.info("Processing completed successfully")
