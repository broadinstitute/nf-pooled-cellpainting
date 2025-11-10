# ruff: noqa: ANN002,ANN003,ANN202,ANN204,ANN401,D100,D104,D202,D400,D413,D415,E501,F401,F541,F821,F841,I001,N803,N806,N816,PTH102,PTH104,PTH110,PTH112,PTH113,PTH114,PTH115,PTH118,PTH123,UP015,UP024,UP031,UP035,W605,E722
"""Script for stitching and cropping microscopy images using ImageJ/Fiji.

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

Usage:
  - Run normally for interactive mode with confirmations:
    python stitch_crop.py

  - Run in automatic mode (skip all confirmations):
    python stitch_crop.py -y
    python stitch_crop.py --yes
    python stitch_crop.py auto
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

# Grid stitching parameters
rows = "2"  # Number of rows in the site grid
columns = "2"  # Number of columns in the site grid

# Dynamically set size based on crop percentage (default to no crop for real datasets)
# Original images are 1600x1600, after crop:
# - 25% crop (CROP_PERCENT=25): 400x400 (test data)
# - 50% crop (CROP_PERCENT=50): 800x800
# - No crop (default): ~1480x1480 (with some built-in crop)
crop_percent_str = os.getenv("CROP_PERCENT", "100")
if not crop_percent_str:  # Handle empty string case
    crop_percent_str = "100"
crop_percent = int(crop_percent_str)
if crop_percent == 25:
    size = "400"
    final_tile_size = "800"
    logger.info(
        "=== CROP_PERCENT=25 detected: Using 400x400 input images, 800x800 output tiles ==="
    )
elif crop_percent == 50:
    size = "800"
    final_tile_size = "1600"
    logger.info(
        "=== CROP_PERCENT=50 detected: Using 800x800 input images, 1600x1600 output tiles ==="
    )
else:
    # Default/no crop
    size = "1480"
    final_tile_size = "2960"
    logger.info(
        "=== No crop/default: Using 1480x1480 input images, 2960x2960 output tiles ==="
    )

logger.info(
    "Configuration: Input size={}x{}, Final tile size={}x{}".format(
        size, size, final_tile_size, final_tile_size
    )
)
overlap_pct = "10"  # Percentage overlap between adjacent images

# Tiling parameters
tileperside = "2"  # Number of tiles to create per side when cropping
scalingstring = "1.99"  # Scaling factor to apply to images
round_or_square = "square"  # Shape of the well (square or round)
xoffset_tiles = "0"  # X offset for tile cropping
yoffset_tiles = "0"  # Y offset for tile cropping
compress = "True"  # Whether to compress output TIFF files

# Channel information
channame = "DNA"  # Target channel name for processing (always DNA for this workflow)

# Unused parameters (kept for compatibility)
imperwell = "unused"
stitchorder = "unused"
filterstring = "unused"
awsdownload = "unused"
bucketname = "unused"
downloadfilter = "unused"
quarter_if_round = "unused"

# Log configuration
logger.info("=== Configuration ===")
logger.info("Input directory: {}".format(input_dir))
logger.info("Output base: {}".format(output_base))
logger.info("Channel: {}".format(channame))
logger.info("Grid: {}x{} with {}% overlap".format(rows, columns, overlap_pct))

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
                + " first_file_index_i=0 directory="
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
                        IJ.makeRectangle(
                            eachxtile * tilesize,  # X position
                            eachytile * tilesize,  # Y position
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
                # Commented out code for reference:
                # im=IJ.open(os.path.join(out_subdir,fileoutname))
                # im = IJ.getImage()
                # IJ.run("Close All")
    # Code for round wells is disabled for testing
    elif round_or_square == "round":
        logger.info("Removed round for testing")

    else:
        logger.error("Must identify well as round or square")
else:
    logger.error("Could not find input directory {}".format(input_dir))

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
