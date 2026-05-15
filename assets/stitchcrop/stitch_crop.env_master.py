import os

# Input variables from Environment
input_file_location = os.getenv("INPUT_FILE_LOCATION", ".")
step_to_stitch = os.getenv("STEP_TO_STITCH", "Stitch")
subdir = os.getenv("SUBDIR", "images")
out_subdir_tag = os.getenv("OUT_SUBDIR_TAG", "Batch1")
rows = os.getenv("ROWS", "2")
columns = os.getenv("COLUMNS", "2")
imperwell = os.getenv("IMPERWELL", "")
stitchorder = os.getenv("STITCHORDER", "Grid: snake by rows")
channame = os.getenv("CHANNAME", "DNA")
overlap_pct = os.getenv("OVERLAP_PCT", "10")
tileperside = os.getenv("TILEPERSIDE", "2")
filterstring = os.getenv("FILTERSTRING", "")
scalingstring = os.getenv("SCALINGSTRING", "1.99")
# awsdownload removed
# bucketname removed
# localtemp removed
# downloadfilter removed
round_or_square = os.getenv("ROUND_OR_SQUARE", "square")
quarter_if_round = os.getenv("QUARTER_IF_ROUND", "true")
final_tile_size = os.getenv("FINAL_TILE_SIZE", "2960")
xoffset_tiles = os.getenv("XOFFSET_TILES", "0")
yoffset_tiles = os.getenv("YOFFSET_TILES", "0")
compress = os.getenv("COMPRESS", "True")
phenix = os.getenv("PHENIX","False")

from ij import IJ, WindowManager
import os
import string
import sys
import time

from loci.plugins.out import Exporter
from loci.plugins import LociExporter
plugin = LociExporter()

#Dict of well sizes we understand for well-patterns that start in the top left and snake towards the right and bottom
im_per_well_dict = {
    "1396": [
        18, 22, 26, 28, 30, 32, 34, 36, 36, 38, 38, 40, 40, 40, 40, 40, 40, 40, 40, 40, 
        40, 40, 40, 40, 40, 40, 40, 40, 40, 38, 38, 36, 36, 34, 32, 30, 28, 26, 22, 18,
    ],
    "1364": [8, 14, 18, 22, 26, 28, 30, 32, 34, 34, 36, 36, 38, 38, 40, 40, 40, 42, 42,
        42, 42, 42, 42, 42, 42, 40, 40, 40, 38, 38, 36, 36, 34, 34, 32, 30, 28, 26, 22, 
        18, 14, 8,
    ],
    "1332": [
        14, 18, 22, 26, 28, 30, 32, 34, 34, 36, 36, 38, 38, 40, 40, 40, 40, 40, 40, 40,
        40, 40, 40, 40, 40, 40, 40, 38, 38, 36, 36, 34, 34, 32, 30, 28, 26, 22, 18, 14,
    ],
    "1025":[
        5,11,17,19,23,25,27,29,29,31,33,33,33,35,35,35,37,37,37,37,37,35,35,35,33,
        33,33,31,29,29,27,25,23,19,17,11,5,
    ],
    "394": [
        3, 7, 9, 11, 11, 13, 13, 15, 15, 15, 17, 17, 17, 17, 17, 17, 17, 17, 17, 17,
        15, 15, 15, 13, 13, 11, 11, 9, 7, 3,
    ],
    "320": [
        4, 8, 12, 14, 16, 18, 18, 20, 20, 20, 20, 20, 20, 20, 18, 18, 16, 14, 12, 8, 
        4,
    ],
    "316": [6, 10, 14, 16, 16, 18, 18, 20, 20, 20, 20, 20, 20, 18, 18, 16, 16, 14, 10, 6],
    "293": [7, 11, 13, 15, 17, 17, 19, 19, 19, 19, 19, 19, 19, 17, 17, 15, 13, 11, 7],
    "256": [6, 10, 12, 14, 16, 16, 18, 18, 18, 18, 18, 18, 16, 16, 14, 12, 10, 6],
    "88": [6, 8, 10, 10, 10, 10, 10, 10, 8, 6],
    "56": [2, 6, 8, 8, 8, 8, 8, 6, 2],
    "52": [4, 6, 8, 8, 8, 8, 6, 4],
    "45": [5,7,7,7,7,7,5],
}

#Dict of well sizes we understand for well-patterns that start in the center, then jump to the top left and snake 
#towards the right and bottom. As far as we know, this is just the Phenix (and friends like the Operetta)
phenix_im_per_well_dict = {
    "80": [['']*3+list(range(2,6))+['']*3,
            ['']+list(range(13,5,-1))+[''],
            ['']+list(range(14,22))+[''],
            list(range(31,21,-1)),
            list(range(32,42)),
            list(range(50,46,-1))+[1]+list(range(46,41,-1)),
            list(range(51,61)),
            ['']+list(range(68,60,-1))+[''],
            ['']+list(range(69,77))+[''],
            ['']*3+list(range(80,76,-1))+['']*3,
            ],
    "21": [['']+list(range(2,5))+[''],
            list(range(9,4,-1)),
            list(range(10,12))+[1]+list(range(12,14)),
            list(range(18,13,-1)),
            ['']+list(range(19,22))+[''],
            ]
}

#This carries the per-quarter variable options for stitching in quarters
#It is prepopulated with anything we know that's size-agnostic; size-dependent
#parameters are calculated and added by determine_final_tile_size_and_offsets
stitched_quarter_dict = {"TopLeft":
                         {"name":"StitchedTopLeft",
                          "position":"Bottom-Right zero",
                          "tile_coords_for_final_tiles":{}
                         },
                        "TopRight":
                        {"name":"StitchedTopRight",
                          "position":"Bottom-Left zero", 
                          "tile_coords_for_final_tiles":{}
                         },
                        "BotLeft":
                        {"name":"StitchedBottomLeft",
                          "position":"Top-Right zero", 
                          "tile_coords_for_final_tiles":{}
                         },
                        "BotRight":
                        {"name":"StitchedBottomRight",
                          "position":"Top-Left zero", 
                          "tile_coords_for_final_tiles":{}
                         },
                        }


def tiffextend(imname):
        if '.tif' in imname:
                return imname
        if '.' in imname:
                return imname[:imname.index('.')]+'.tiff'
        else:
                return imname+'.tiff'

def savefile(im,imname,plugin,compress='false'):
        attemptcount = 0
        imname = tiffextend(imname)
        print('Saving ',imname,im.width,im.height)
        if compress.lower()!='true':
                IJ.saveAs(im, "tiff",imname)
        else:
                while attemptcount <5:
                        try:
                                plugin.arg="outfile="+imname+" windowless=true compression=LZW saveROI=false"
                                exporter = Exporter(plugin, im)
                                exporter.run()
                                print('Succeeded after attempt ',attemptcount)
                                return
                        except:
                                attemptcount +=1
                print('failed 5 times at saving')


def parse_files(subdir, channame, filterstring):
    """
    Figure out the wells present and channels present in our data, therefore what we should stitch
    Right now, assumes all output comes from our nice CellProfiler pipelines upstream
    Future versions where barcoding comes off the microscope (or phenotyping, for a scope
    where on-scope FFC is good) will need new and better parsing"""
    dir_list = os.listdir(subdir)
    well_list = []
    prefix_suffix_list = []
    perm_prefix = None
    perm_suffix = None
    for eachfile in dir_list:
        if ".tif" in eachfile:
            if filterstring in eachfile:
                if "Overlay" not in eachfile:
                    prefix_before_well, suffix_with_well = eachfile.split("_Well_")
                    well, suffix_after_well = suffix_with_well.split("_Site_")
                    channel_suffix = suffix_after_well[suffix_after_well.index("_") + 1 :]
                    if (prefix_before_well, channel_suffix) not in prefix_suffix_list:
                        prefix_suffix_list.append((prefix_before_well, channel_suffix))
                    if well not in well_list:
                        well_list.append(well)
                    if channame in channel_suffix:
                        if perm_prefix is None:
                            perm_prefix = prefix_before_well
                            perm_suffix = channel_suffix

    for eachpresuf in prefix_suffix_list:
        if eachpresuf[1][-4:] != ".tif":
            if eachpresuf[1][-5:] != ".tiff":
                prefix_suffix_list.remove(eachpresuf)
    prefix_suffix_list.sort()
    print("final parse results", well_list, prefix_suffix_list)
    if perm_prefix is None or perm_suffix is None:
        print("Something went wrong with parsing, couldn't find files with the channel name", channame)
        print("Can also be caused by your filterstring", filterstring, "removing all files")
        print("Can also be caused if images are not .tif or .tiff")
        sys.exit()
    return dir_list, well_list,prefix_suffix_list, perm_prefix, perm_suffix
    
def run_initial_stitching_per_well_section(round_or_square, stitchorder, rows, columns, overlap_pct, subdir, 
                                 perm_prefix, eachwell, perm_suffix, compress, 
                                 out_subdir, plugin, stitched_quarter_dict, quarter = False,):
    """Actually does the initial stitching, outputs the Tile Configuration file, no Python return.
    Could probably be refactored/shortened even further but it's probably fine."""
    if round_or_square == 'square':
        standard_grid_instructions = [
            "type=["
            + stitchorder
            + "] order=[Right & Down                ] grid_size_x="
            + rows
            + " grid_size_y="
            + columns
            + " tile_overlap="
            + overlap_pct
            + " first_file_index_i=0 directory="
            + subdir
            + " file_names=",
            " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]",
        ]
        filename = perm_prefix + "_Well_" + eachwell + "_Site_{i}_" + perm_suffix
        fileoutname = "Stitched" + filename.replace("{i}", "")
        IJ.run(
            "Grid/Collection stitching",
            standard_grid_instructions[0]
            + filename
            + standard_grid_instructions[1],
        )
        im = IJ.getImage()
        # We're going to overwrite this file later, but it gives is a chance for an early checkpoint
        # This doesn't seem to play nicely with the compression option on, it doesn't get overwritten later and bad things happen
        if compress.lower() != "true":
            savefile(
                im, os.path.join(out_subdir, fileoutname), plugin, compress=compress
            )
        IJ.run("Close All")
    else:
        if quarter_if_round.lower() == "false":
            standard_grid_instructions = [
                "type=[Filename defined position] order=[Defined by filename         ] grid_size_x="
                + str(columns)
                + " grid_size_y="
                + str(rows)
                + " tile_overlap="
                + overlap_pct
                + " first_file_index_x=0 first_file_index_y=0 directory="
                + subdir
                + " file_names=",
                " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]",
            ]
            filename = (
                perm_prefix + "_Well_" + eachwell + "_x_{xx}_y_{yy}_" + perm_suffix
            )
            fileoutname = "Stitched" + filename.replace("{i}", "")
            instructions = (
                standard_grid_instructions[0]
                + filename
                + standard_grid_instructions[1]
            )
            print(instructions)
            IJ.run("Grid/Collection stitching", instructions)
            im = IJ.getImage()
            # We're going to overwrite this file later, but it gives us a chance for an early checkpoint
            # This doesn't seem to play nicely with the compression option on, it doesn't get overwritten later and bad things happen
            if compress.lower() != "true":
                savefile(
                    im,
                    os.path.join(out_subdir, fileoutname),
                    plugin,
                    compress=compress,
                )
            print(os.path.join(out_subdir, fileoutname))
            time.sleep(30)
            IJ.run("Close All")
        else:
            quarter_options = stitched_quarter_dict[quarter]
            print(quarter_options)
            standard_grid_instructions = [
                "type=[Filename defined position] order=[Defined by filename         ] grid_size_x="
                + quarter_options["grid_size_x"]
                + " grid_size_y="
                + quarter_options["grid_size_y"]
                + " tile_overlap="
                + overlap_pct
                + " first_file_index_x="
                + str(quarter_options["first_file_index_offset_x"])
                +" first_file_index_y="
                + str(quarter_options["first_file_index_offset_y"])
                +" directory="
                + os.path.abspath(subdir)
                + " file_names=",
                " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]",
            ]
            filename = (
                perm_prefix + "_Well_" + eachwell + "_x_{xx}_y_{yy}_" + perm_suffix
            )
            fileoutname = quarter_options["name"] + filename.replace("{xx}", "").replace(
                "{yy}", ""
            )
            instructions = (
                standard_grid_instructions[0]
                + filename
                + standard_grid_instructions[1]
            )
            print(instructions)
            IJ.run("Grid/Collection stitching", instructions)
            im = IJ.getImage()
            # We're going to overwrite this file later, but it gives us a chance for an early checkpoint
            # This doesn't seem to play nicely with the compression option on, it doesn't get overwritten later and bad things happen
            if compress.lower() != "true":
                savefile(
                    im,
                    os.path.join(out_subdir, fileoutname),
                    plugin,
                    compress=compress,
                )
            IJ.run("Close All")

def apply_stitching_per_well_section_and_channel(eachpresuf, subdir,round_or_square,quarter_if_round, tileperside,tilesize, 
                                          stitched_quarter_dict, compress, quarter = False, emptylist=None,  upscaled_row_size=0, upscaled_col_size=0):
    """Apply the stitching pattern calculated in run_initial_stitching_per_well to each channel for this well (or well quarter).
    For round wells where we've padded with noise tiles, uses the emptylist to remove them from the final configuration file we pass
    to the Grid/Stitch plugin, avoiding a very old bug that just dumps them on the top-left real tile.
    We make a full-sized stitch and a 10x downsampled stitch (for easy QC), then close everything and re-open the full-sized stitch
    to create a set of sub-tiled crops"""
    copy_grid_instructions = (
            "type=[Positions from file] order=[Defined by TileConfiguration] directory="
            + subdir
            + " layout_file=TileConfiguration.registered_copy.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 ignore_z_stage computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"
        )
    
    #set up
    if round_or_square == 'square':
            do_quarter = False
    else:
        if quarter_if_round.lower()== "true":
            do_quarter = True
        else:
            do_quarter = False
    if not do_quarter:
        thisprefix, thissuffix = eachpresuf
        thissuffixnicename = thissuffix.split(".")[0]
        if thissuffixnicename[0] == "_":
            thissuffixnicename = thissuffixnicename[1:]
        tile_subdir_persuf = os.path.join(tile_subdir, thissuffixnicename)
        if not os.path.exists(tile_subdir_persuf):
            os.mkdir(tile_subdir_persuf)
        filename = thisprefix + "_Well_" + eachwell + "_Site_{i}_" + thissuffix
        fileoutname = "Stitched" + filename.replace("{i}", "")
        with open(
            os.path.join(subdir, "TileConfiguration.registered.txt"), "r"
        ) as infile:
            with open(
                os.path.join(subdir, "TileConfiguration.registered_copy.txt"),
                "w",
            ) as outfile:
                for line in infile:
                    if emptylist is not None:
                        if not any([empty in line for empty in emptylist]):
                            line = line.replace(perm_prefix, thisprefix)
                            line = line.replace(perm_suffix, thissuffix)
                            outfile.write(line)
                    else:
                        line = line.replace(perm_prefix, thisprefix)
                        line = line.replace(perm_suffix, thissuffix)
                        outfile.write(line)

        IJ.run("Grid/Collection stitching", copy_grid_instructions)
        im = IJ.getImage()
        width = str(int(round(im.width * float(scalingstring))))
        height = str(int(round(im.height * float(scalingstring))))
        # scale the barcoding and cell painting images to match each other
        print(
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
        time.sleep(15)
        im2 = IJ.getImage()
        # padding to ensure tiles are all the same size (for CellProfiler later on)
        print(
            "Canvas Size...",
            "width="
            + str(upscaled_col_size)
            + " height="
            + str(upscaled_row_size)
            + " position=Top-Left zero",
        )
        IJ.run(
            "Canvas Size...",
            "width="
            + str(upscaled_col_size)
            + " height="
            + str(upscaled_row_size)
            + " position=Top-Left zero",
        )
        time.sleep(15)
        im3 = IJ.getImage()
        savefile(
            im3,
            os.path.join(out_subdir, fileoutname),
            plugin,
            compress=compress,
        )
        im = IJ.getImage()
        # scaling to make a downsampled image for QC
        print(
            "Scale...",
            "x=0.1 y=0.1 width="
            + str(im.width / 10)
            + " height="
            + str(im.width / 10)
            + " interpolation=Bilinear average create",
        )
        im_10 = IJ.run(
            "Scale...",
            "x=0.1 y=0.1 width="
            + str(im.width / 10)
            + " height="
            + str(im.width / 10)
            + " interpolation=Bilinear average create",
        )
        im_10 = IJ.getImage()
        savefile(
            im_10,
            os.path.join(downsample_subdir, fileoutname),
            plugin,
            compress=compress,
        )
        IJ.run("Close All")
        im = IJ.open(os.path.abspath(os.path.join(out_subdir, fileoutname)))
        im = IJ.getImage()
        plate = fileoutname.split("Plate_")[1].split("_Well_")[0]
        for eachxtile in range(int(tileperside)):
            for eachytile in range(int(tileperside)):
                each_tile_num = eachxtile * int(tileperside) + eachytile + 1
                IJ.makeRectangle(
                    eachxtile * tilesize,
                    eachytile * tilesize,
                    tilesize,
                    tilesize,
                )
                im_tile = im.crop()
                savefile(
                    im_tile,
                    os.path.join(
                        tile_subdir_persuf,
                        thissuffixnicename
                        + "_Plate_"
                        + str(plate)
                        + "_Well_"
                        + str(eachwell)
                        + "_Site_"
                        + str(each_tile_num)
                        + ".tiff",
                    ),
                    plugin,
                    compress=compress,
                )
        IJ.run("Close All")
    else:
        quarter_options = stitched_quarter_dict[quarter]
        thisprefix, thissuffix = eachpresuf
        thissuffixnicename = thissuffix.split(".")[0]
        if thissuffixnicename[0] == "_":
            thissuffixnicename = thissuffixnicename[1:]
        tile_subdir_persuf = os.path.join(tile_subdir, thissuffixnicename)
        if not os.path.exists(tile_subdir_persuf):
            os.mkdir(tile_subdir_persuf)
        filename = (
            thisprefix
            + "_Well_"
            + eachwell
            + "_x_{xx}_y_{yy}_"
            + thissuffix
        )
        fileoutname = quarter_options["name"] + filename.replace(
            "{xx}", ""
        ).replace("{yy}", "")
        with open(
            os.path.join(subdir, "TileConfiguration.registered.txt"), "r"
        ) as infile:
            with open(
                os.path.join(
                    subdir, "TileConfiguration.registered_copy.txt"
                ),
                "w",
            ) as outfile:
                for line in infile:
                    if not any([empty in line for empty in emptylist]):
                        line = line.replace(perm_prefix, thisprefix)
                        line = line.replace(perm_suffix, thissuffix)
                        outfile.write(line)

        IJ.run("Grid/Collection stitching", copy_grid_instructions)
        im0 = IJ.getImage()
        # chop off the opposite edige
        IJ.makeRectangle(
            quarter_options["crop_numerical_position"][0], 
            quarter_options["crop_numerical_position"][1], 
            im0.width + quarter_options["crop_numerical_position"][2], 
            im0.height + quarter_options["crop_numerical_position"][3]
        )
        im1 = im0.crop()
        width = str(int(round(im1.width * float(scalingstring))))
        height = str(int(round(im1.height * float(scalingstring))))
        print(
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
        time.sleep(15)
        im2 = IJ.getImage()
        print(
            "Canvas Size...",
            "width="
            + str(upscaled_col_size)
            + " height="
            + str(upscaled_row_size)
            + " position="+quarter_options["position"],
        )
        IJ.run(
            "Canvas Size...",
            "width="
            + str(upscaled_col_size)
            + " height="
            + str(upscaled_row_size)
            + " position="+quarter_options["position"],
        )
        time.sleep(15)
        im3 = IJ.getImage()
        savefile(
            im3,
            os.path.join(out_subdir, fileoutname),
            plugin,
            compress=compress,
        )
        im = IJ.getImage()
        print(
            "Scale...",
            "x=0.1 y=0.1 width="
            + str(im.width / 10)
            + " height="
            + str(im.width / 10)
            + " interpolation=Bilinear average create",
        )
        im_10 = IJ.run(
            "Scale...",
            "x=0.1 y=0.1 width="
            + str(im.width / 10)
            + " height="
            + str(im.width / 10)
            + " interpolation=Bilinear average create",
        )
        im_10 = IJ.getImage()
        savefile(
            im_10,
            os.path.join(downsample_subdir, fileoutname),
            plugin,
            compress=compress,
        )
        IJ.run("Close All")
        im = IJ.open(os.path.abspath(os.path.join(out_subdir, fileoutname)))
        im = IJ.getImage()
        tiles_to_make = quarter_options["tile_coords_for_final_tiles"]
        plate = fileoutname.split("Plate_")[1].split("_Well_")[0]
        for eachtile in tiles_to_make.keys():
            IJ.makeRectangle(
                tiles_to_make[eachtile][0],
                tiles_to_make[eachtile][1],
                tilesize,
                tilesize,
            )
            im_tile = im.crop()
            savefile(
                im_tile,
                os.path.join(
                    tile_subdir_persuf,
                    thissuffixnicename
                    + "_Plate_"
                    + str(plate)
                    + "_Well_"
                    + str(eachwell)
                    + "_Site_"
                    + str(eachtile)
                    + ".tiff",
                ),
                plugin,
                compress=compress,
            )
        IJ.run("Close All")

def get_round_rows_cols(im_per_well_dict, phenix_im_per_well_dict, imperwell, phenix):
    if not phenix: #assume we snake back and forth, like a sane microscope
        try:
            row_widths = im_per_well_dict[imperwell]
            rows = str(len(row_widths))
            columns = str(max(row_widths))
        except:
            print(imperwell, "images/well for a round well is not currently supported")
            sys.exit()
        
    else:
        try: 
            row_pattern = phenix_im_per_well_dict[imperwell]
            row_widths = range(len(row_pattern))
            column_widths = range(len(row_pattern[0]))
            rows = str(len(row_widths))
            columns = str(len(column_widths))
        except:
            print(imperwell, "images/well for a round Phenix well is not currently supported")
            sys.exit()
    return rows, columns
        
def map_and_rename_round_wells(im_per_well_dict,phenix_im_per_well_dict,imperwell,size,
                      well_list, prefix_suffix_list, subdir, phenix=False):
    """Makes the new blank file and the renamed files, return the empty list of things that won't align"""
    pos_dict = {}
    emptylist = [] 

    if not phenix: #assume we snake back and forth, like a sane microscope
        row_widths = im_per_well_dict[imperwell]
        try:
            rows = str(len(row_widths))
            columns = str(max(row_widths))
            count = 0

            for row in range(len(row_widths)):
                row_width = row_widths[row]
                left_pos = int((int(columns) - row_width) / 2)
                for col in range(row_width):
                    if row % 2 == 0:
                        pos_dict[(int(left_pos + col), row)] = str(count)
                        count += 1
                    else:
                        right_pos = left_pos + row_width - 1
                        pos_dict[(int(right_pos - col), row)] = str(count)
                        count += 1
        except:
            print("failed at trying to create position dict from images per well")
            sys.exit()
    else: #since the Phenix, due to its initial center position, isn't easy to mathematically model, we just had to hardcode the positions
        row_pattern = phenix_im_per_well_dict[imperwell]

        try:
            row_widths = range(len(row_pattern))
            column_widths = range(len(row_pattern[0]))
            rows = str(len(row_widths))
            columns = str(len(column_widths))
            for row in row_widths:
                for col in column_widths:
                    siteval = row_pattern[row][col]
                    if siteval != "":
                        pos_dict[(col, row)] = str(siteval)
        except:
            print("failed at trying to create position dict from images per well") 
            sys.exit()

    filled_positions = pos_dict.keys()
    #print(os.listdir('.'),os.listdir(subdir))
    for eachwell in well_list:
        for eachpresuf in prefix_suffix_list:
            thisprefix, thissuffix = eachpresuf
            for x in range(int(columns)):
                for y in range(int(rows)):
                    out_name = (
                        thisprefix
                        + "_Well_"
                        + eachwell
                        + "_x_"
                        + "%02d" % x
                        + "_y_"
                        + "%02d" % y
                        + "_"
                        + thissuffix
                    )
                    if (x, y) in filled_positions:
                        #Note- if we ever decide to not have renamed things (ie, not illum correct barcode), work is needed here
                        series = pos_dict[(x, y)]
                        in_name = (
                            thisprefix
                            + "_Well_"
                            + eachwell
                            + "_Site_"
                            + str(series)
                            + "_"
                            + thissuffix
                        )
                        IJ.open(os.path.abspath(os.path.join(subdir,in_name)))
                    else:
                        IJ.newImage(
                            "Untitled", "16-bit noise", int(size), int(size), 1
                        )
                        IJ.run(
                            "Divide...", "value=100"
                        )  # get the noise value below the real camera noise level
                        emptylist.append(out_name)
                    im = IJ.getImage()
                    IJ.saveAs(im, "tiff", os.path.join(subdir, out_name))
                    IJ.run("Close All")
                    if (x, y) in filled_positions:
                        try:  # try to clean up after yourself, but don't die if you can't
                            os.remove(os.path.join(subdir, in_name))
                        except:
                            pass
            print(
                "Renamed all files for prefix "
                + thisprefix
                + " and suffix "
                + thissuffix
                + " in well "
                + eachwell
            )
        imagelist = os.listdir(subdir)
        print(len(imagelist), "files in subdir")
        print("first ten images in imagelist", imagelist[:10])
        return emptylist, rows, columns

def determine_final_tile_size_and_offsets(tileperside,scalingstring, rows, columns, 
                                          stitched_quarter_dict, final_tile_size, yoffset_tiles=0, xoffset_tiles=0):
    """Return final parameters for how many tiles we're going to have, and what sizes they'll be.
    
    For cases where we're quartering a large round well, it also does the crop determination;
    this includes the first_file_offset indices passed to GridStitcher (so that it knows and expects
    to stitch e.g. only columns 6-10 rather than 1-5) and human-determined offsets which alter where the
    lines between parts of the circle are drawn (rare, implmented I THINK mostly for alignment issues if 
    I recall correctly, which I may not). """

    tileperside = int(tileperside)
    scale_factor = float(scalingstring)
    rounded_scale_factor = int(round(scale_factor))
    if round_or_square == 'square':
        stitchedsize = int(rows) * int(size)
        upscaled_row_size = int(stitchedsize * rounded_scale_factor)
        if upscaled_row_size > 46340:
            upscaled_row_size = 46340
        upscaled_col_size = upscaled_row_size
        tilesize = int(upscaled_row_size / tileperside)
        pixels_to_crop = None
    else:
        tilesize = int(final_tile_size)
    if quarter_if_round.lower() == "true":
        # xoffset_tiles and yoffset_tiles can be used if you need to adjust the "where to draw the line between quarters"
        # by a whole tile. You may want to add more padding if you do this
        top_rows = str((int(rows) / 2) + int(yoffset_tiles))
        left_columns = str((int(columns) / 2) + int(xoffset_tiles))
        bot_rows = str(int(rows) - int(top_rows))
        right_columns = str(int(columns) - int(left_columns))
        # For upscaled row and column size, we're always going to use the biggest number, we'd rather pad than miss stuff
        # Because we can't assure same final tile size now either, now we need to specify it, ugh, and make sure the padding is big enough
        max_val = max(
            int(top_rows), int(bot_rows), int(left_columns), int(right_columns)
        )
        upscaled_row_size = int(size) * max_val * rounded_scale_factor
        tiles_per_quarter = int(tileperside) / 2
        if tilesize * tiles_per_quarter > upscaled_row_size:
            upscaled_row_size = tilesize * tiles_per_quarter
        upscaled_col_size = upscaled_row_size
        tile_offset = upscaled_row_size - (tilesize * tiles_per_quarter) #I'm not sure how this works? 
        pixels_to_crop = int(round(int(size) * float(overlap_pct) / 200)) #I'm not sure how this works either?

        #top left
        stitched_quarter_dict["TopLeft"]["grid_size_x"] = left_columns
        stitched_quarter_dict["TopLeft"]["grid_size_y"] = top_rows
        stitched_quarter_dict["TopLeft"]["crop_numerical_position"] = [0,0,-pixels_to_crop,-pixels_to_crop]
        stitched_quarter_dict["TopLeft"]["first_file_index_offset_x"] = 0
        stitched_quarter_dict["TopLeft"]["first_file_index_offset_y"] = 0
        for eachxtile in range(tiles_per_quarter):
            for eachytile in range(tiles_per_quarter):
                each_tile_num = eachxtile*int(tileperside) + eachytile + 1
                stitched_quarter_dict["TopLeft"]["tile_coords_for_final_tiles"][each_tile_num] = ((eachxtile*tilesize)+tile_offset, (eachytile*tilesize)+tile_offset)
        #top right
        stitched_quarter_dict["TopRight"]["grid_size_x"] = right_columns
        stitched_quarter_dict["TopRight"]["grid_size_y"] = top_rows
        stitched_quarter_dict["TopRight"]["crop_numerical_position"] = [pixels_to_crop,0,-pixels_to_crop,-pixels_to_crop]
        stitched_quarter_dict["TopRight"]["first_file_index_offset_x"] = left_columns
        stitched_quarter_dict["TopRight"]["first_file_index_offset_y"] = 0
        for eachxtile in range(tiles_per_quarter):
            for eachytile in range(tiles_per_quarter):
                each_tile_num = (
                                int(tiles_per_quarter) * int(tileperside)
                                + eachxtile * int(tileperside)
                                + eachytile
                                + 1
                            )
                stitched_quarter_dict["TopRight"]["tile_coords_for_final_tiles"][each_tile_num] = ((eachxtile*tilesize), (eachytile*tilesize)+tile_offset)
        #bot left
        stitched_quarter_dict["BotLeft"]["grid_size_x"] = left_columns
        stitched_quarter_dict["BotLeft"]["grid_size_y"] = bot_rows
        stitched_quarter_dict["BotLeft"]["crop_numerical_position"] = [0,pixels_to_crop,-pixels_to_crop,-pixels_to_crop]
        stitched_quarter_dict["BotLeft"]["first_file_index_offset_x"] = 0
        stitched_quarter_dict["BotLeft"]["first_file_index_offset_y"] = top_rows 
        for eachxtile in range(tiles_per_quarter):
            for eachytile in range(tiles_per_quarter):
                each_tile_num = (
                                eachxtile * int(tileperside)
                                + int(tiles_per_quarter)
                                + eachytile
                                + 1
                            )
                stitched_quarter_dict["BotLeft"]["tile_coords_for_final_tiles"][each_tile_num] = ((eachxtile*tilesize)+tile_offset, (eachytile*tilesize))
        #bot right
        stitched_quarter_dict["BotRight"]["grid_size_x"] = right_columns
        stitched_quarter_dict["BotRight"]["grid_size_y"] = bot_rows
        stitched_quarter_dict["BotRight"]["crop_numerical_position"] = [pixels_to_crop,pixels_to_crop,-pixels_to_crop,-pixels_to_crop]
        stitched_quarter_dict["BotRight"]["first_file_index_offset_x"] = left_columns
        stitched_quarter_dict["BotRight"]["first_file_index_offset_y"] = top_rows
        for eachxtile in range(tiles_per_quarter):
            for eachytile in range(tiles_per_quarter):
                each_tile_num = each_tile_num = (
                                int(tiles_per_quarter) * int(tileperside)
                                + eachxtile * int(tileperside)
                                + int(tiles_per_quarter)
                                + eachytile
                                + 1
                            )
                stitched_quarter_dict["BotRight"]["tile_coords_for_final_tiles"][each_tile_num] = ((eachxtile * tilesize),(eachytile * tilesize))

    else:
        max_val = max(int(rows), int(columns))
        upscaled_row_size = int(size) * max_val * rounded_scale_factor
        if tilesize * tileperside > upscaled_row_size:
            upscaled_row_size = tilesize * tileperside
        upscaled_col_size = upscaled_row_size
        pixels_to_crop = None
    
    return tilesize, upscaled_row_size, upscaled_col_size, pixels_to_crop, stitched_quarter_dict, scale_factor

# ACTUAL CODE TO RUN STARTS HERE, EVERYTHING ABOVE COULD BE A UTIL

# Define and create the folders where the images will be output
out_subdir = 'stitched_images'
tile_subdir = 'cropped_images'
downsample_subdir = 'downsampled_images'

if not os.path.exists(out_subdir):
        os.mkdir(out_subdir)
if not os.path.exists(tile_subdir):
        os.mkdir(tile_subdir)
if not os.path.exists(downsample_subdir):
        os.mkdir(downsample_subdir)

subdir=os.path.join(input_file_location,subdir)

if os.path.isdir(subdir):
    dir_list, well_list, prefix_suffix_list, perm_prefix, perm_suffix = parse_files(subdir, channame, filterstring)

    # Measure actual image size from the first file
    first_image_path = os.path.join(subdir, perm_prefix + "_Well_" + well_list[0] + "_Site_1_" + perm_suffix)
    imp = IJ.openImage(first_image_path)
    size = str(imp.getWidth())
    imp.close()

    if round_or_square == "round": # We usually infer rows and columns from the im_per_well_dict for round
        do_phenix = phenix.lower()=="true"
        rows, columns = get_round_rows_cols(im_per_well_dict, phenix_im_per_well_dict, imperwell, phenix = do_phenix)
    
    #Get final sizes for things, including all random funky offsets
    tilesize, upscaled_row_size, upscaled_col_size, pixels_to_crop, stitched_quarter_dict, scale_factor = determine_final_tile_size_and_offsets(tileperside,scalingstring, rows, columns, 
                                        stitched_quarter_dict, final_tile_size, yoffset_tiles=yoffset_tiles, xoffset_tiles=xoffset_tiles)
    
    print("finished the parsing",tilesize, upscaled_row_size, upscaled_col_size, pixels_to_crop, stitched_quarter_dict, scale_factor)
    if round_or_square == "square":
        for eachwell in well_list:
            run_initial_stitching_per_well_section(round_or_square, stitchorder, rows, columns, overlap_pct, subdir, 
                                perm_prefix, eachwell, perm_suffix, compress, out_subdir, plugin, stitched_quarter_dict, quarter = False,)
            for eachpresuf in prefix_suffix_list:  # for each channel
                apply_stitching_per_well_section_and_channel(eachpresuf, subdir,round_or_square,quarter_if_round, tileperside,tilesize, 
                                stitched_quarter_dict, compress, upscaled_row_size=upscaled_row_size, upscaled_col_size=upscaled_col_size)
    elif round_or_square == "round":
        # do renaming and mapping of where each position is
        # Since the Grid/Collection plugin requires squares, this also makes empty tiles 
        # at the edges to pad the circle into a square
        emptylist, rows, columns = map_and_rename_round_wells(im_per_well_dict,phenix_im_per_well_dict,imperwell,size,
                      well_list, prefix_suffix_list, subdir, phenix=do_phenix)
        
        #The mapper doesn't know what the permament prefix and suffix are, so we'll subset this for speed
        print("perm_prefix", perm_prefix)
        print("perm_suffix", perm_suffix)
        print("emptylist before subsetting", emptylist)
        emptylist = [x for x in emptylist if perm_prefix in x if perm_suffix in x]
        print("emptylist after subsetting", emptylist)

        for eachwell in well_list:
            if quarter_if_round.lower() == "false": #The whole well should be stitched
                run_initial_stitching_per_well_section(round_or_square, stitchorder, rows, columns, overlap_pct, subdir, 
                                perm_prefix, eachwell, perm_suffix, compress, 
                                out_subdir, plugin, stitched_quarter_dict, quarter = False,)
                # cropping
                for eachpresuf in prefix_suffix_list:  # for each channel
                    apply_stitching_per_well_section_and_channel(eachpresuf, subdir,round_or_square,quarter_if_round, tileperside,tilesize, 
                                stitched_quarter_dict, compress, emptylist=emptylist, upscaled_row_size=upscaled_row_size, upscaled_col_size=upscaled_col_size)
            else:
                for quarter in stitched_quarter_dict.keys(): #The well is over Fiji's max size limit, so we'll stitch in quarters
                    run_initial_stitching_per_well_section(round_or_square, stitchorder, rows, columns, overlap_pct, subdir, 
                                perm_prefix, eachwell, perm_suffix, compress, 
                                out_subdir, plugin, stitched_quarter_dict, quarter = quarter)
                    for eachpresuf in prefix_suffix_list:
                        apply_stitching_per_well_section_and_channel(eachpresuf, subdir,round_or_square,quarter_if_round, tileperside,tilesize,
                                stitched_quarter_dict, compress, quarter = quarter, emptylist=emptylist, upscaled_row_size=upscaled_row_size, 
                                upscaled_col_size=upscaled_col_size)

    else:
        print("Must identify well as round or square")
else:
    print("Could not find input directory ", subdir)
for eachlogfile in [
    "TileConfiguration.txt",
    "TileConfiguration.registered.txt",
    "TileConfiguration.registered_copy.txt",
]:
    os.rename(os.path.join(subdir, eachlogfile), os.path.join(out_subdir, eachlogfile))