# /// script
# dependencies = [
#     "marimo",
#     "numpy==2.5.5",
#     "pillow==13.0.0",
# ]
# requires-python = ">=3.13"
# ///

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _():
    import glob
    import math
    import textwrap

    return glob, math, textwrap


@app.cell
def _(mo):
    qc_folder_explorer=mo.ui.file_browser (label="Directory with QC reports",selection_mode='directory',multiple=False, restrict_navigation=False)
    plate = mo.ui.text(label='Plate name',placeholder="BR00150248")
    return plate, qc_folder_explorer


@app.cell
def _(mo):
    mo.md("""
    # nf-pooled-cellpainting QC browser

    Allows easier reading of the QC reports.

    For already-stitched-together pngs (currently 1, 3, 5, 7, 11), put up a single image viewer); for full HTML report (13) embed it directly; for one-align-per-well (currently 4, 8) make a grid. For cross-cycle barcode alignment (currently 9), show one set per well
    """)
    return


@app.cell
def _(plate):
    plate
    return


@app.cell
def _(qc_folder_explorer):
    qc_folder_explorer
    return


@app.cell
def _(glob, plate, qc_folder_explorer):
    images_to_view = glob.glob(f"{qc_folder_explorer.value[0].path}/**/{plate.value}/*.png",recursive=True) + glob.glob(f"{qc_folder_explorer.value[0].path}/**/{plate.value}/**/*.png",recursive=True)
    return (images_to_view,)


@app.cell
def _(mo):
    mo.md("""
    ## Illums
    """)
    return


@app.cell
def _(images_to_view, mo):
    illum_painting = [x for x in images_to_view if 'illumination_painting' in x]
    if len(illum_painting) > 0:
        ill_im = mo.image(illum_painting[0])
    else:
        ill_im = mo.md("Nothing with `illumination_painting` detected")
    ill_im
    return


@app.cell
def _(images_to_view, mo):
    illum_bc = [x for x in images_to_view if 'illumination_barcoding' in x]
    if len(illum_bc) > 0:
        ill_bc = mo.image(illum_bc[0])
    else:
        ill_bc = mo.md("Nothing with `illumination_barcoding` detected")
    ill_bc
    return


@app.cell
def _(mo):
    mo.md("""
    ## Stitching
    """)
    return


@app.cell
def _(images_to_view, mo):
    stitch_painting = [x for x in images_to_view if 'stitching_painting' in x]
    if len(stitch_painting) > 0:
        stitch_p_im = mo.image(stitch_painting[0])
    else:
        stitch_p_im = mo.md("Nothing with `stitching_painting` detected")
    stitch_p_im
    return


@app.cell
def _(images_to_view, mo):
    stitch_barcoding = [x for x in images_to_view if 'stitching_barcoding' in x]
    if len(stitch_barcoding) > 0:
        stitch_b_im = mo.image(stitch_barcoding[0])
    else:
        stitch_b_im = mo.md("Nothing with `stitching_barcoding` detected")
    stitch_b_im
    return


@app.cell
def _(mo):
    mo.md("""
    ## Alignment
    """)
    return


@app.cell
def _(images_to_view):
    alignment = [x for x in images_to_view if 'alignment' in x]
    return (alignment,)


@app.cell
def _(math, mo, textwrap):
    def make_image_grid(list_of_images,size=400,textwidth=50,columns=False):
        if not columns:
            columns = round(len(list_of_images)**0.5)
        rows = math.ceil(len(list_of_images)/columns)
        grid_image_dict = {x:mo.vstack([mo.md(f"""**{'\n'.join(textwrap.wrap(list_of_images[x],width=textwidth))}**"""),
                                        mo.image(list_of_images[x],width=size)]) for x in range(len(list_of_images))}
        grid_row_list = []
        for row in range(rows):
            grid_col_list = []
            for col in range(columns):
                if (row*columns+col) in grid_image_dict.keys():
                    grid_col_list.append(grid_image_dict[row*columns+col])
            grid_row_list.append(mo.hstack(grid_col_list))
        return mo.vstack(grid_row_list)
    

    return (make_image_grid,)


@app.cell
def _(alignment, make_image_grid):
    paint_align = [x for x in alignment if 'painting' in x]
    paint_align.sort()
    paint_grid = make_image_grid(paint_align)
    paint_grid
    return


@app.cell
def _(alignment, make_image_grid):
    comb_align = [x for x in alignment if 'combined' in x]
    comb_align.sort()
    comb_grid = make_image_grid(comb_align)
    comb_grid
    return


@app.cell
def _(alignment, make_image_grid, mo, plate):
    bc_align = [x for x in alignment if 'barcoding' in x]
    bc_align.sort()
    well_list = list(set([x.split(f"{plate.value}-")[1].split('/')[0] for x in bc_align]))
    well_list.sort()
    #well_picker = mo.ui.dropdown(label="Well",value=well_list[0],options=well_list)
    grid_stack = []
    for well in well_list:
        grid_stack.append(mo.md(f"### {well}"))
        bc_well_list = [x for x in bc_align if well in x]
        grid_stack.append(make_image_grid(bc_well_list,columns=3))
    mo.md("### Barcoding intra-arm grids are long for many wells; they are collapsed behind a dropdown below")
    return (grid_stack,)


@app.cell
def _(grid_stack, mo):
    mo.accordion({"Barcoding cross-cycle alignment (collapsible for length)":mo.vstack(grid_stack)})
    return


@app.cell
def _(mo):
    mo.md("""
    ## Segmentation
    """)
    return


@app.cell
def _(images_to_view, mo):
    seg = [x for x in images_to_view if 'segmentation' in x]
    if len(seg) > 0:
        seg = mo.image(seg[0])
    else:
        seg = mo.md("Nothing with `segmentation` detected")
    seg
    return


@app.cell
def _(mo):
    mo.md("""
    ## Barcode Calling
    """)
    return


@app.cell
def _(glob, plate, qc_folder_explorer):
    htmls_to_view = glob.glob(f"{qc_folder_explorer.value[0].path}/**/{plate.value}/*.html",recursive=True)
    return (htmls_to_view,)


@app.cell
def _(htmls_to_view):
    if len(htmls_to_view) >0:
        a = open(htmls_to_view[0],'r',encoding='utf-8')
        b = a.read()
    return (b,)


@app.cell
def _(b, mo):
    mo.iframe(b)
    return


if __name__ == "__main__":
    app.run()
