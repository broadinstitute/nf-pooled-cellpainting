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
size = os.getenv("SIZE", "1480")
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

from ij import IJ, WindowManager
import os
import string
import sys
import time

from loci.plugins.out import Exporter
from loci.plugins import LociExporter
plugin = LociExporter()

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
        dirlist=os.listdir(subdir)
        welllist=[]
        presuflist = []
        permprefix = None
        permsuffix = None
        for eachfile in dirlist:
                        if '.tif' in eachfile:
                                if filterstring in eachfile:
                                        if 'Overlay' not in eachfile:
                                                prefixBeforeWell,suffixWithWell=eachfile.split('_Well_')
                                                Well,suffixAfterWell=suffixWithWell.split('_Site_')
                                                channelSuffix = suffixAfterWell[suffixAfterWell.index('_')+1:]
                                                if (prefixBeforeWell,channelSuffix) not in presuflist:
                                                        presuflist.append((prefixBeforeWell,channelSuffix))
                                                if Well not in welllist:
                                                        welllist.append(Well)
                                                if channame in channelSuffix:
                                                        if permprefix == None:
                                                                permprefix=prefixBeforeWell
                                                                permsuffix=channelSuffix

        for eachpresuf in presuflist:
                if eachpresuf[1][-4:]!='.tif':
                        if eachpresuf[1][-5:]!='.tiff':
                                presuflist.remove(eachpresuf)
        presuflist.sort()
        print welllist, presuflist

        # Fallback: if no channel matched channame, use the first available prefix/suffix
        if permprefix is None and len(presuflist) > 0:
                permprefix = presuflist[0][0]
                permsuffix = presuflist[0][1]
                print("Warning: CHANNAME '"+channame+"' not found in any file. Using first available channel: "+permsuffix)

        if round_or_square == 'square':
                stitchedsize=int(rows)*int(size)
                tileperside=int(tileperside)
                scale_factor=float(scalingstring)
                rounded_scale_factor=int(round(scale_factor))
                upscaledsize=int(stitchedsize*rounded_scale_factor)
                if upscaledsize > 46340:
                        upscaledsize = 46340
                tilesize=int(upscaledsize/tileperside)

                for eachwell in welllist:
                        standard_grid_instructions=["type=["+stitchorder+"] order=[Right & Down                ] grid_size_x="+rows+" grid_size_y="+columns+" tile_overlap="+overlap_pct+" first_file_index_i=0 directory="+subdir+" file_names=",
                        " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"]
                        copy_grid_instructions="type=[Positions from file] order=[Defined by TileConfiguration] directory="+subdir+" layout_file=TileConfiguration.registered_copy.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 ignore_z_stage computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"
                        filename=permprefix+'_Well_'+eachwell+'_Site_{i}_'+permsuffix
                        fileoutname='Stitched'+filename.replace("{i}","")
                        IJ.run("Grid/Collection stitching", standard_grid_instructions[0] + filename + standard_grid_instructions[1])
                        im=IJ.getImage()
                        #We're going to overwrite this file later, but it gives is a chance for an early checkpoint
                        #This doesn't seem to play nicely with the compression option on, it doesn't get overwritten later and bad things happen
                        if compress.lower()!='true':
                                savefile(im,os.path.join(out_subdir,fileoutname),plugin,compress=compress)
                        IJ.run("Close All")
                        for eachpresuf in presuflist: # for each channel
                                thisprefix, thissuffix=eachpresuf
                                thissuffixnicename = thissuffix.split('.')[0]
                                if thissuffixnicename[0]=='_':
                                        thissuffixnicename=thissuffixnicename[1:]

                                filename=thisprefix+'_Well_'+eachwell+'_Site_{i}_'+thissuffix
                                fileoutname='Stitched'+filename.replace("{i}","")
                                with open(os.path.join(subdir, 'TileConfiguration.registered.txt'),'r') as infile:
                                        with open(os.path.join(subdir, 'TileConfiguration.registered_copy.txt'),'w') as outfile:
                                                for line in infile:
                                                        line=line.replace(permprefix,thisprefix)
                                                        line=line.replace(permsuffix,thissuffix)
                                                        outfile.write(line)

                                IJ.run("Grid/Collection stitching", copy_grid_instructions)
                                im=IJ.getImage()
                                width = str(int(round(im.width*float(scalingstring))))
                                height = str(int(round(im.height*float(scalingstring))))
                                # scale the barcoding and cell painting images to match each other
                                print("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                                IJ.run("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                                time.sleep(15)
                                im2=IJ.getImage()
                                #padding to ensure tiles are all the same size (for CellProfiler later on)
                                print("Canvas Size...", "width="+str(upscaledsize)+" height="+str(upscaledsize)+" position=Top-Left zero")
                                IJ.run("Canvas Size...", "width="+str(upscaledsize)+" height="+str(upscaledsize)+" position=Top-Left zero")
                                time.sleep(15)
                                im3=IJ.getImage()
                                savefile(im3,os.path.join(out_subdir,fileoutname),plugin,compress=compress)
                                im=IJ.getImage()
                                #scaling to make a downsampled image for QC
                                print("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                                im_10=IJ.run("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                                im_10=IJ.getImage()
                                savefile(im_10,os.path.join(downsample_subdir,fileoutname),plugin,compress=compress)
                                IJ.run("Close All")
                                im=IJ.open(os.path.join(out_subdir,fileoutname))
                                im = IJ.getImage()
                                for eachxtile in range(tileperside):
                                        for eachytile in range(tileperside):
                                                each_tile_num = eachxtile*tileperside + eachytile + 1
                                                IJ.makeRectangle(eachxtile*tilesize, eachytile*tilesize,tilesize,tilesize)
                                                im_tile=im.crop()
                                                savefile(im_tile,os.path.join(tile_subdir,thissuffixnicename+'_Site_'+str(each_tile_num)+'.tiff'),plugin,compress=compress)
                                IJ.run("Close All")
        elif round_or_square == 'round':
                if imperwell == '1364':
                        row_widths = [8,14,18,22,26,28,30,
                        32,34,34,36,36,38,38,
                        40,40,40,42,42,42,42,
                        42,42,42,42,40,40,40,
                        38,38,36,36,34,34,32,
                        30,28,26,22,18,14,8]
                elif imperwell == '1332':
                        row_widths = [14,18,22,26,28,30,
                        32,34,34,36,36,38,38,
                        40,40,40,40,40,40,40,
                        40,40,40,40,40,40,40,
                        38,38,36,36,34,34,32,
                        30,28,26,22,18,14]
                elif imperwell == '1396':
                        row_widths = [18,22,26,28,30,
                        32,34,36,36,38,38,
                        40,40,40,40,40,40,40,40,40,
                        40,40,40,40,40,40,40,40,40,
                        38,38,36,36,34,32,
                        30,28,26,22,18]
                elif imperwell == '1025':
                        row_widths = [5,11,17,19,23,25,27,29,29,31,33,33,33,35,35,35,37,37,37,37,37,35,35,35,33,33,33,31,29,29,27,25,23,19,17,11,5]
                elif imperwell == '394':
                        row_widths = [3,7,9,11,11,
                        13,13,15,15,15,
                        17,17,17,17,17,17,17,17,17,17,
                        15,15,15,13,13,11,11,9,7,3]
                elif imperwell == '320':
                        row_widths = [4, 8, 12, 14, 16,
                        18, 18, 20, 20, 20,
                        20, 20, 20, 20, 18,
                        18, 16, 14, 12, 8, 4]
                elif imperwell == '316':
                        row_widths = [6, 10, 14, 16, 16,
                        18, 18, 20, 20, 20,
                        20, 20, 20, 18, 18,
                        16, 16, 14, 10, 6]
                elif imperwell == '293':
                        row_widths = [7, 11, 13, 15, 17, 17,
                        19, 19, 19, 19, 19, 19, 19, 17, 17,
                        15, 13, 11, 7]
                elif imperwell == '88':
                        row_widths = [6, 8, 10, 10, 10, 10, 10, 10, 8, 6]
                elif imperwell == '256':
                        row_widths = [6,10,12,14,16,16,18,18,18,18,18,18,16,16,14,12,10,6]
                elif imperwell == '52':
                        row_widths = [4,6,8,8,8,8,6,4]
                elif imperwell == '56':
                        row_widths = [2, 6, 8, 8, 8, 8, 8, 6, 2]
                elif imperwell == '45':
                        row_widths = [5,7,7,7,7,7,5]
                else:
                        print(imperwell, "images/well for a round well is not currently supported")
                        sys.exit()

                rows = str(len(row_widths))
                columns = str(max(row_widths))

                tileperside = int(tileperside)
                tilesize=int(final_tile_size)
                scale_factor=float(scalingstring)
                rounded_scale_factor=int(round(scale_factor))

                if quarter_if_round.lower() == "true":
                        # xoffset_tiles and yoffset_tiles can be used if you need to adjust the "where to draw the line between quarters"
                        # by a whole tile. You may want to add more padding if you do this
                        top_rows = str((int(rows)/2)+int(yoffset_tiles))
                        left_columns = str((int(columns)/2)+int(xoffset_tiles))
                        bot_rows = str(int(rows)-int(top_rows))
                        right_columns = str(int(columns)-int(left_columns))
                        #For upscaled row and column size, we're always going to use the biggest number, we'd rather pad than miss stuff
                        #Because we can't assure same final tile size now either, now we need to specify it, ugh, and make sure the padding is big enough
                        max_val = max(int(top_rows),int(bot_rows),int(left_columns),int(right_columns))
                        upscaled_row_size=int(size)*max_val*rounded_scale_factor
                        tiles_per_quarter = int(tileperside)/2
                        if tilesize * tiles_per_quarter > upscaled_row_size:
                                upscaled_row_size = tilesize * tiles_per_quarter
                        upscaled_col_size=upscaled_row_size
                        pixels_to_crop = int(round(int(size)*float(overlap_pct)/200))
                else:
                        max_val = max(int(rows), int(columns))
                        upscaled_row_size=int(size)*max_val*rounded_scale_factor
                        if tilesize * tileperside > upscaled_row_size:
                                upscaled_row_size = tilesize * tileperside
                        upscaled_col_size=upscaled_row_size

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
                for eachwell in welllist:
                        for eachpresuf in presuflist:
                                thisprefix, thissuffix=eachpresuf
                                for x in range(int(columns)):
                                        for y in range(int(rows)):
                                                out_name = thisprefix+'_Well_'+eachwell+'_x_'+ '%02d'%x+'_y_'+'%02d'%y+ '_'+ thissuffix
                                                if (x,y) in filled_positions:
                                                        series = pos_dict[(x,y)]
                                                        in_name = thisprefix+'_Well_'+eachwell+'_Site_'+str(series)+'_'+thissuffix
                                                        IJ.open(os.path.join(subdir,in_name))
                                                else:
                                                        IJ.newImage("Untitled", "16-bit noise",int(size),int(size), 1)
                                                        IJ.run("Divide...", "value=100") #get the noise value below the real camera noise level
                                                        emptylist.append(out_name)
                                                im = IJ.getImage()
                                                IJ.saveAs(im,'tiff',os.path.join(subdir, out_name))
                                                IJ.run("Close All")
                                                if (x,y) in filled_positions:
                                                        try: #try to clean up after yourself, but don't die if you can't
                                                                os.remove(os.path.join(subdir,in_name))
                                                        except:
                                                                pass
                                print("Renamed all files for prefix "+thisprefix+" and suffix "+thissuffix+" in well "+eachwell)
                        imagelist = os.listdir(subdir)
                        print(len(imagelist), 'files in subdir')
                        print(imagelist[:10])

                        if quarter_if_round.lower() == "false":
                                #all quarters
                                print('Stitching whole well')
                                standard_grid_instructions=["type=[Filename defined position] order=[Defined by filename         ] grid_size_x="+str(columns)+" grid_size_y="+str(rows)+" tile_overlap="+overlap_pct+" first_file_index_x=0 first_file_index_y=0 directory="+subdir+" file_names=",
                                " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"]
                                copy_grid_instructions="type=[Positions from file] order=[Defined by TileConfiguration] directory="+subdir+" layout_file=TileConfiguration.registered_copy.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 ignore_z_stage computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"
                                filename=permprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+permsuffix
                                fileoutname='Stitched'+filename.replace("{i}","")
                                instructions = standard_grid_instructions[0] + filename + standard_grid_instructions[1]
                                print(instructions)
                                IJ.run("Grid/Collection stitching", instructions)
                                im=IJ.getImage()
                                #We're going to overwrite this file later, but it gives us a chance for an early checkpoint
                                #This doesn't seem to play nicely with the compression option on, it doesn't get overwritten later and bad things happen
                                if compress.lower()!='true':
                                        savefile(im,os.path.join(out_subdir,fileoutname),plugin,compress=compress)
                                print(os.path.join(out_subdir,fileoutname))
                                time.sleep(300)
                                IJ.run("Close All")
                                # cropping
                                for eachpresuf in presuflist: # for each channel
                                        thisprefix, thissuffix=eachpresuf
                                        thissuffixnicename = thissuffix.split('.')[0]
                                        if thissuffixnicename[0]=='_':
                                                thissuffixnicename=thissuffixnicename[1:]

                                        filename=thisprefix+'_Well_'+eachwell+'_Site_{i}_'+thissuffix
                                        fileoutname='Stitched'+filename.replace("{i}","")
                                        with open(os.path.join(subdir, 'TileConfiguration.registered.txt'),'r') as infile:
                                                with open(os.path.join(subdir, 'TileConfiguration.registered_copy.txt'),'w') as outfile:
                                                        for line in infile:
                                                                line=line.replace(permprefix,thisprefix)
                                                                line=line.replace(permsuffix,thissuffix)
                                                                outfile.write(line)

                                        IJ.run("Grid/Collection stitching", copy_grid_instructions)
                                        im=IJ.getImage()
                                        width = str(int(round(im.width*float(scalingstring))))
                                        height = str(int(round(im.height*float(scalingstring))))
                                        # scale the barcoding and cell painting images to match each other
                                        print("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                                        IJ.run("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                                        time.sleep(15)
                                        im2=IJ.getImage()
                                        #padding to ensure tiles are all the same size (for CellProfiler later on)
                                        print("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Top-Left zero")
                                        IJ.run("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Top-Left zero")
                                        time.sleep(15)
                                        im3=IJ.getImage()
                                        savefile(im3,os.path.join(out_subdir,fileoutname),plugin,compress=compress)
                                        im=IJ.getImage()
                                        #scaling to make a downsampled image for QC
                                        print("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                                        im_10=IJ.run("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                                        im_10=IJ.getImage()
                                        savefile(im_10,os.path.join(downsample_subdir,fileoutname),plugin,compress=compress)
                                        IJ.run("Close All")
                                        im=IJ.open(os.path.join(out_subdir,fileoutname))
                                        im = IJ.getImage()
                                        for eachxtile in range(tileperside):
                                                for eachytile in range(tileperside):
                                                        each_tile_num = eachxtile*tileperside + eachytile + 1
                                                        IJ.makeRectangle(eachxtile*tilesize, eachytile*tilesize,tilesize,tilesize)
                                                        im_tile=im.crop()
                                                        savefile(im_tile,os.path.join(tile_subdir,thissuffixnicename+'_Site_'+str(each_tile_num)+'.tiff'),plugin,compress=compress)
                                        IJ.run("Close All")


                        else:
                                #top left quarter
                                print('Running top left')
                                #Change per quarter
                                standard_grid_instructions=["type=[Filename defined position] order=[Defined by filename         ] grid_size_x="+str(left_columns)+" grid_size_y="+top_rows+" tile_overlap="+overlap_pct+" first_file_index_x=0 first_file_index_y=0 directory="+subdir+" file_names=",
                                " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"]
                                copy_grid_instructions="type=[Positions from file] order=[Defined by TileConfiguration] directory="+subdir+" layout_file=TileConfiguration.registered_copy.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 ignore_z_stage computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"
                                filename=permprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+permsuffix
                                #Change per quarter
                                fileoutname='StitchedTopLeft'+filename.replace("{xx}","").replace("{yy}","")
                                instructions = standard_grid_instructions[0] + filename + standard_grid_instructions[1]
                                print(instructions)
                                IJ.run("Grid/Collection stitching", instructions)
                                im=IJ.getImage()
                                #We're going to overwrite this file later, but it gives us a chance for an early checkpoint
                                #This doesn't seem to play nicely with the compression option on, it doesn't get overwritten later and bad things happen
                                if compress.lower()!='true':
                                        savefile(im,os.path.join(out_subdir,fileoutname),plugin,compress=compress)
                                IJ.run("Close All")
                                for eachpresuf in presuflist:
                                        thisprefix, thissuffix=eachpresuf
                                        thissuffixnicename = thissuffix.split('.')[0]
                                        if thissuffixnicename[0]=='_':
                                                thissuffixnicename=thissuffixnicename[1:]

                                        filename=thisprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+thissuffix
                                        #Change per quarter
                                        fileoutname='StitchedTopLeft'+filename.replace("{xx}","").replace("{yy}","")
                                        with open(os.path.join(subdir, 'TileConfiguration.registered.txt'),'r') as infile:
                                                with open(os.path.join(subdir, 'TileConfiguration.registered_copy.txt'),'w') as outfile:
                                                        for line in infile:
                                                                if not any([empty in line for empty in emptylist]):
                                                                        line=line.replace(permprefix,thisprefix)
                                                                        line=line.replace(permsuffix,thissuffix)
                                                                        outfile.write(line)

                                        IJ.run("Grid/Collection stitching", copy_grid_instructions)
                                        im0=IJ.getImage()
                                        #chop off the bottom and right
                                        #Change per quarter
                                        IJ.makeRectangle(0,0,im0.width-pixels_to_crop,im0.height-pixels_to_crop)
                                        im1=im0.crop()
                                        width = str(int(round(im1.width*float(scalingstring))))
                                        height = str(int(round(im1.height*float(scalingstring))))
                                        print("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                                        IJ.run("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                                        time.sleep(15)
                                        im2=IJ.getImage()
                                        #Chnage per quarter
                                        print("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Bottom-Right zero")
                                        IJ.run("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Bottom-Right zero")
                                        time.sleep(15)
                                        im3=IJ.getImage()
                                        savefile(im3,os.path.join(out_subdir,fileoutname),plugin,compress=compress)
                                        im=IJ.getImage()
                                        print("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                                        im_10=IJ.run("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                                        im_10=IJ.getImage()
                                        savefile(im_10,os.path.join(downsample_subdir,fileoutname),plugin,compress=compress)
                                        IJ.run("Close All")
                                        im=IJ.open(os.path.join(out_subdir,fileoutname))
                                        im = IJ.getImage()
                                        tile_offset = upscaled_row_size - (tilesize * tiles_per_quarter)
                                        for eachxtile in range(tiles_per_quarter):
                                                for eachytile in range(tiles_per_quarter):
                                                        #Change per quarter
                                                        each_tile_num = eachxtile*int(tileperside) + eachytile + 1
                                                        #Change per quarter
                                                        IJ.makeRectangle((eachxtile*tilesize)+tile_offset, (eachytile*tilesize)+tile_offset,tilesize,tilesize)
                                                        im_tile=im.crop()
                                                        savefile(im_tile,os.path.join(tile_subdir,thissuffixnicename+'_Site_'+str(each_tile_num)+'.tiff'),plugin,compress=compress)
                                        IJ.run("Close All")

                                #top right quarter
                                print('Running top right')
                                #Change per quarter
                                standard_grid_instructions=["type=[Filename defined position] order=[Defined by filename         ] grid_size_x="+str(right_columns)+" grid_size_y="+top_rows+" tile_overlap="+overlap_pct+" first_file_index_x="+str(left_columns)+" first_file_index_y=0 directory="+subdir+" file_names=",
                                " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"]
                                copy_grid_instructions="type=[Positions from file] order=[Defined by TileConfiguration] directory="+subdir+" layout_file=TileConfiguration.registered_copy.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 ignore_z_stage computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"
                                filename=permprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+permsuffix
                                #Change per quarter
                                fileoutname='StitchedTopRight'+filename.replace("{xx}","").replace("{yy}","")
                                IJ.run("Grid/Collection stitching", standard_grid_instructions[0] + filename + standard_grid_instructions[1])
                                im=IJ.getImage()
                                #We're going to overwrite this file later, but it gives us a chance for an early checkpoint
                                #This doesn't seem to play nicely with the compression option on, it doesn't get overwritten later and bad things happen
                                if compress.lower()!='true':
                                        savefile(im,os.path.join(out_subdir,fileoutname),plugin,compress=compress)
                                IJ.run("Close All")
                                for eachpresuf in presuflist:
                                        thisprefix, thissuffix=eachpresuf
                                        thissuffixnicename = thissuffix.split('.')[0]
                                        if thissuffixnicename[0]=='_':
                                                thissuffixnicename=thissuffixnicename[1:]

                                        filename=thisprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+thissuffix
                                        #Change per quarter
                                        fileoutname='StitchedTopRight'+filename.replace("{xx}","").replace("{yy}","")
                                        with open(os.path.join(subdir, 'TileConfiguration.registered.txt'),'r') as infile:
                                                with open(os.path.join(subdir, 'TileConfiguration.registered_copy.txt'),'w') as outfile:
                                                        for line in infile:
                                                                if not any([empty in line for empty in emptylist]):
                                                                        line=line.replace(permprefix,thisprefix)
                                                                        line=line.replace(permsuffix,thissuffix)
                                                                        outfile.write(line)

                                        IJ.run("Grid/Collection stitching", copy_grid_instructions)
                                        im0=IJ.getImage()
                                        #chop off the bottom and left
                                        #Change per quarter
                                        IJ.makeRectangle(pixels_to_crop,0,im0.width-pixels_to_crop,im0.height-pixels_to_crop)
                                        im1=im0.crop()
                                        width = str(int(round(im1.width*float(scalingstring))))
                                        height = str(int(round(im1.height*float(scalingstring))))
                                        print("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                                        IJ.run("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                                        time.sleep(15)
                                        im2=IJ.getImage()
                                        #Chnage per quarter
                                        print("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Bottom-Left zero")
                                        IJ.run("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Bottom-Left zero")
                                        time.sleep(15)
                                        im3=IJ.getImage()
                                        savefile(im3,os.path.join(out_subdir,fileoutname),plugin,compress=compress)
                                        im=IJ.getImage()
                                        print("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                                        im_10=IJ.run("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                                        im_10=IJ.getImage()
                                        savefile(im_10,os.path.join(downsample_subdir,fileoutname),plugin,compress=compress)
                                        IJ.run("Close All")
                                        im=IJ.open(os.path.join(out_subdir,fileoutname))
                                        im = IJ.getImage()
                                        tile_offset = upscaled_row_size - (tilesize * tiles_per_quarter)
                                        for eachxtile in range(tiles_per_quarter):
                                                for eachytile in range(tiles_per_quarter):
                                                        #Change per quarter
                                                        each_tile_num = int(tiles_per_quarter)*int(tileperside)+ eachxtile*int(tileperside) + eachytile + 1
                                                        #Change per quarter
                                                        IJ.makeRectangle((eachxtile*tilesize), (eachytile*tilesize)+tile_offset,tilesize,tilesize)
                                                        im_tile=im.crop()
                                                        savefile(im_tile,os.path.join(tile_subdir,thissuffixnicename+'_Site_'+str(each_tile_num)+'.tiff'),plugin,compress=compress)
                                        IJ.run("Close All")

                                #bottom left quarter
                                print('Running bottom left')
                                #Change per quarter
                                standard_grid_instructions=["type=[Filename defined position] order=[Defined by filename         ] grid_size_x="+str(left_columns)+" grid_size_y="+bot_rows+" tile_overlap="+overlap_pct+" first_file_index_x=0 first_file_index_y="+top_rows+" directory="+subdir+" file_names=",
                                " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"]
                                copy_grid_instructions="type=[Positions from file] order=[Defined by TileConfiguration] directory="+subdir+" layout_file=TileConfiguration.registered_copy.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 ignore_z_stage computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"
                                filename=permprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+permsuffix
                                #Change per quarter
                                fileoutname='StitchedBottomLeft'+filename.replace("{xx}","").replace("{yy}","")
                                IJ.run("Grid/Collection stitching", standard_grid_instructions[0] + filename + standard_grid_instructions[1])
                                im=IJ.getImage()
                                #We're going to overwrite this file later, but it gives us a chance for an early checkpoint
                                #This doesn't seem to play nicely with the compression option on, it doesn't get overwritten later and bad things happen
                                if compress.lower()!='true':
                                        savefile(im,os.path.join(out_subdir,fileoutname),plugin,compress=compress)
                                IJ.run("Close All")
                                for eachpresuf in presuflist:
                                        thisprefix, thissuffix=eachpresuf
                                        thissuffixnicename = thissuffix.split('.')[0]
                                        if thissuffixnicename[0]=='_':
                                                thissuffixnicename=thissuffixnicename[1:]

                                        filename=thisprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+thissuffix
                                        #Change per quarter
                                        fileoutname='StitchedBottomLeft'+filename.replace("{xx}","").replace("{yy}","")
                                        with open(os.path.join(subdir, 'TileConfiguration.registered.txt'),'r') as infile:
                                                with open(os.path.join(subdir, 'TileConfiguration.registered_copy.txt'),'w') as outfile:
                                                        for line in infile:
                                                                if not any([empty in line for empty in emptylist]):
                                                                        line=line.replace(permprefix,thisprefix)
                                                                        line=line.replace(permsuffix,thissuffix)
                                                                        outfile.write(line)

                                        IJ.run("Grid/Collection stitching", copy_grid_instructions)
                                        im0=IJ.getImage()
                                        #chop off the top and right
                                        #Change per quarter
                                        IJ.makeRectangle(0,pixels_to_crop,im0.width-pixels_to_crop,im0.height-pixels_to_crop)
                                        im1=im0.crop()
                                        width = str(int(round(im1.width*float(scalingstring))))
                                        height = str(int(round(im1.height*float(scalingstring))))
                                        print("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                                        IJ.run("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                                        time.sleep(15)
                                        im2=IJ.getImage()
                                        #Chnage per quarter
                                        print("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Top-Right zero")
                                        IJ.run("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Top-Right zero")
                                        time.sleep(15)
                                        im3=IJ.getImage()
                                        savefile(im3,os.path.join(out_subdir,fileoutname),plugin,compress=compress)
                                        im=IJ.getImage()
                                        print("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                                        im_10=IJ.run("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                                        im_10=IJ.getImage()
                                        savefile(im_10,os.path.join(downsample_subdir,fileoutname),plugin,compress=compress)
                                        IJ.run("Close All")
                                        im=IJ.open(os.path.join(out_subdir,fileoutname))
                                        im = IJ.getImage()
                                        tile_offset = upscaled_row_size - (tilesize * tiles_per_quarter)
                                        for eachxtile in range(tiles_per_quarter):
                                                for eachytile in range(tiles_per_quarter):
                                                        #Change per quarter
                                                        each_tile_num = eachxtile*int(tileperside) + int(tiles_per_quarter) + eachytile + 1
                                                        #Change per quarter
                                                        IJ.makeRectangle((eachxtile*tilesize)+tile_offset, (eachytile*tilesize),tilesize,tilesize)
                                                        im_tile=im.crop()
                                                        savefile(im_tile,os.path.join(tile_subdir,thissuffixnicename+'_Site_'+str(each_tile_num)+'.tiff'),plugin,compress=compress)
                                        IJ.run("Close All")

                                #bottom right quarter
                                print('Running bottom right')
                                #Change per quarter
                                standard_grid_instructions=["type=[Filename defined position] order=[Defined by filename         ] grid_size_x="+str(right_columns)+" grid_size_y="+bot_rows+" tile_overlap="+overlap_pct+" first_file_index_x="+str(left_columns)+" first_file_index_y="+top_rows+" directory="+subdir+" file_names=",
                                " output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"]
                                copy_grid_instructions="type=[Positions from file] order=[Defined by TileConfiguration] directory="+subdir+" layout_file=TileConfiguration.registered_copy.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 ignore_z_stage computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]"
                                filename=permprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+permsuffix
                                #Change per quarter
                                fileoutname='StitchedBottomRight'+filename.replace("{xx}","").replace("{yy}","")
                                IJ.run("Grid/Collection stitching", standard_grid_instructions[0] + filename + standard_grid_instructions[1])
                                im=IJ.getImage()
                                #We're going to overwrite this file later, but it gives us a chance for an early checkpoint
                                #This doesn't seem to play nicely with the compression option on, it doesn't get overwritten later and bad things happen
                                if compress.lower()!='true':
                                        savefile(im,os.path.join(out_subdir,fileoutname),plugin,compress=compress)
                                IJ.run("Close All")
                                for eachpresuf in presuflist:
                                        thisprefix, thissuffix=eachpresuf
                                        thissuffixnicename = thissuffix.split('.')[0]
                                        if thissuffixnicename[0]=='_':
                                                thissuffixnicename=thissuffixnicename[1:]

                                        filename=thisprefix+'_Well_'+eachwell+'_x_{xx}_y_{yy}_'+thissuffix
                                        #Change per quarter
                                        fileoutname='StitchedBottomRight'+filename.replace("{xx}","").replace("{yy}","")
                                        with open(os.path.join(subdir, 'TileConfiguration.registered.txt'),'r') as infile:
                                                with open(os.path.join(subdir, 'TileConfiguration.registered_copy.txt'),'w') as outfile:
                                                        for line in infile:
                                                                if not any([empty in line for empty in emptylist]):
                                                                        line=line.replace(permprefix,thisprefix)
                                                                        line=line.replace(permsuffix,thissuffix)
                                                                        outfile.write(line)

                                        IJ.run("Grid/Collection stitching", copy_grid_instructions)
                                        im0=IJ.getImage()
                                        #chop off the top and left
                                        #Change per quarter
                                        IJ.makeRectangle(pixels_to_crop,pixels_to_crop,im0.width-pixels_to_crop,im0.height-pixels_to_crop)
                                        im1=im0.crop()
                                        width = str(int(round(im1.width*float(scalingstring))))
                                        height = str(int(round(im1.height*float(scalingstring))))
                                        print("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                                        IJ.run("Scale...", "x="+scalingstring+" y="+scalingstring+" width="+width+" height="+height+" interpolation=Bilinear average create")
                                        time.sleep(15)
                                        im2=IJ.getImage()
                                        #Chnage per quarter
                                        print("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Top-Left zero")
                                        IJ.run("Canvas Size...", "width="+str(upscaled_col_size)+" height="+str(upscaled_row_size)+" position=Top-Left zero")
                                        time.sleep(15)
                                        im3=IJ.getImage()
                                        savefile(im3,os.path.join(out_subdir,fileoutname),plugin,compress=compress)
                                        im=IJ.getImage()
                                        print("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                                        im_10=IJ.run("Scale...", "x=0.1 y=0.1 width="+str(im.width/10)+" height="+str(im.width/10)+" interpolation=Bilinear average create")
                                        im_10=IJ.getImage()
                                        savefile(im_10,os.path.join(downsample_subdir,fileoutname),plugin,compress=compress)
                                        IJ.run("Close All")
                                        im=IJ.open(os.path.join(out_subdir,fileoutname))
                                        im = IJ.getImage()
                                        tile_offset = upscaled_row_size - (tilesize * tiles_per_quarter)
                                        for eachxtile in range(tiles_per_quarter):
                                                for eachytile in range(tiles_per_quarter):
                                                        #Change per quarter
                                                        each_tile_num = int(tiles_per_quarter)*int(tileperside) +eachxtile*int(tileperside)+ int(tiles_per_quarter) + eachytile + 1
                                                        #Change per quarter
                                                        IJ.makeRectangle((eachxtile*tilesize), (eachytile*tilesize),tilesize,tilesize)
                                                        im_tile=im.crop()
                                                        savefile(im_tile,os.path.join(tile_subdir,thissuffixnicename+'_Site_'+str(each_tile_num)+'.tiff'),plugin,compress=compress)
                                        IJ.run("Close All")

        else:
                print("Must identify well as round or square")
else:
        print("Could not find input directory ",subdir)
for eachlogfile in ['TileConfiguration.txt','TileConfiguration.registered.txt','TileConfiguration.registered_copy.txt']:
        os.rename(os.path.join(subdir,eachlogfile),os.path.join(out_subdir,eachlogfile))
