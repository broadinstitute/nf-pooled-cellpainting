# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Pipeline 2 QC: Multicycle Painting Alignment Analysis
#
# Analyzes alignment quality between painting cycles by examining pixel shifts
# and correlation scores from Pipeline 2 outputs.

# %% [markdown]
# ## Setup and Configuration

# %%
import os
from pathlib import Path
import re
import pandas as pd
import seaborn as sns
import datetime
import matplotlib.pyplot as plt
import sys

# %matplotlib inline

# %% tags=["parameters"]
# PAPERMILL PARAMETERS
# This cell is tagged as "parameters" for Papermill injection
# When running with papermill, these values will be overridden
# When running interactively, edit these defaults directly

# Analysis parameters
shift_threshold = 50.0
corr_threshold = 0.9

# Input/output paths (edit these for interactive use)
input_dir = "../data/Source1/images/Batch1/images_aligned/barcoding/Plate1"
output_dir = "../data/Source1/workspace/qc_reports/6_alignment/Plate1"

# Acquisition geometry for spatial plot (optional)
# For square: set both rows and columns
# For circular: set row_widths as comma-separated list
rows = 2
columns = 2
imperwell = None
row_widths = None  # Example: [5, 11, 17, 19, 23, 25, 27, 29, ...]

# Cache control
# Set to True for interactive use (fast re-runs with cached data)
# Set to False for production pipelines (always regenerate from source)
use_cache = True

# %% [markdown]
# **For portable mode**:
# - Download notebook and `cached_alignment_data.parquet`
# - set `use_cache = True`
# - set `output_dir = "."` in the cell above (input_dir will be ignored when using cache)

# %%
# Process parameters and create output directory
Path(output_dir).mkdir(parents=True, exist_ok=True)

print("Configuration:")
print(f"  imperwell: {imperwell if imperwell is not None else 'auto-detect'}")
print(f"  shift_threshold: {shift_threshold}")
print(f"  corr_threshold: {corr_threshold}")
print(f"  input_dir: {input_dir}")
print(f"  output_dir: {output_dir}")
if rows and columns:
    print(f"  geometry: square {rows}x{columns}")
elif row_widths:
    print(f"  geometry: circular with {len(row_widths)} rows")

# %% [markdown]
# ## Helper Functions


# %%
def merge_csvs(csvfolder, filename, column_list=None, backup_list=None, filter_string=None):
    """
    Merge CSV files from multiple subdirectories.

    Original function from Erin's notebook - handles well-based directory structure.
    """
    df_dict = {}
    count = 0
    folderlist = os.listdir(csvfolder)
    if filter_string:
        folderlist = [x for x in folderlist if filter_string in x]
    print(count, datetime.datetime.ctime(datetime.datetime.now()))
    for eachfolder in folderlist:
        if os.path.isfile(os.path.join(csvfolder, eachfolder, filename)):
            if not column_list:
                df_dict[eachfolder] = pd.read_csv(
                    os.path.join(csvfolder, eachfolder, filename), index_col=False
                )
            else:
                try:
                    df_dict[eachfolder] = pd.read_csv(
                        os.path.join(csvfolder, eachfolder, filename),
                        index_col=False,
                        usecols=column_list,
                    )
                except:
                    df_dict[eachfolder] = pd.read_csv(
                        os.path.join(csvfolder, eachfolder, filename),
                        index_col=False,
                        usecols=backup_list,
                    )
            count += 1
            if count % 500 == 0:
                print(count, datetime.datetime.ctime(datetime.datetime.now()))
    print(count, datetime.datetime.ctime(datetime.datetime.now()))
    df_merged = pd.concat(df_dict, ignore_index=True)
    print("done concatenating at", datetime.datetime.ctime(datetime.datetime.now()))

    return df_merged


# %% [markdown]
# ## Load Alignment Data

# %%
csvfolder = input_dir
cache_file = Path(output_dir) / "cached_alignment_data.parquet"

channel_name = "DNA"  # default
folderlist = os.listdir(csvfolder)
test_file = os.path.join(csvfolder, folderlist[0], "PaintingIllumApplication_Image.csv")
# Can't pull columns to load from single sample file because not all images go through all of pipeline


# Load data with caching support
if use_cache and cache_file.exists():
    print(f"Loading cached data from: {cache_file}")
    df_image = pd.read_parquet(cache_file)
    print(f"Loaded {len(df_image)} rows from cache")
else:
    print(f"Loading data from: {csvfolder}")
    df_image = merge_csvs(
        csvfolder, "PaintingIllumApplication_Image.csv", backup_list=None, filter_string=None
    )
    if not [x for x in df_image.columns if 'Align' in x]:
        print("No alignment occurred in pipeline. Hopefully single-cycle of phenotypic acquisition")
        sys.exit()
    corr_cols = [x for x in df_image.columns if "Correlation_Correlation" in x and channel_name in x]
    OL_cols = [x for x in df_image.columns if "Overlap_Recall" in x and channel_name in x]
    MI_cols = [x for x in df_image.columns if 'MI' in x and channel_name in x]
    shift_cols = [x for x in df_image.columns if 'Align_' in x and 'shift' in x and channel_name in x]

    # Build column lists using detected channel name
    id_list = ["Metadata_Well", "Metadata_Plate", "Metadata_Site"]
    column_list = list(set(corr_cols + OL_cols + shift_cols + MI_cols + id_list))

    print(f"Loaded {len(df_image)} rows")

    # Cache for future use
    print(f"Caching data to: {cache_file}")
    df_image.to_parquet(cache_file, compression="gzip", index=False)
    print("Cache saved")

# Detect site numbering convention (0-based or 1-based)
min_site = df_image["Metadata_Site"].min()
max_site = df_image["Metadata_Site"].max()
site_offset = min_site
print(f"Detected site numbering: starting at {min_site} ({'0-based' if min_site == 0 else '1-based'})")

# Auto-detect imperwell if not set
if imperwell is None:
    # Calculate number of images per well (works for both 0-based and 1-based indexing)
    imperwell = max_site - min_site + 1
    print(f"Auto-detected imperwell: {imperwell}")

# %% [markdown]
# ## Create Position Mapping for Spatial Plots
#
# This cell creates a mapping from site number to (x, y) position.
# Supports both square and circular acquisition patterns.
# Position mapping is created after data loading to detect the site numbering convention.

# %%
# Only create position mapping if geometry is provided
"""
pos_df = None

if rows and columns: #TODO rows and columns now required for circular too. need to update.
    # Square/rectangular acquisition
    print(f"Creating square position mapping: {rows}x{columns}")
    pos_data = []
    for site in range(rows * columns):
        row = site // columns
        col = site % columns
        # Use min_site offset to match data's site numbering convention
        pos_data.append({"Metadata_Site": site + min_site, "x_loc": col, "y_loc": row})
    pos_df = pd.DataFrame(pos_data)

elif row_widths:
    # Circular acquisition (from original notebook)
    print(f"Creating circular position mapping with {len(row_widths)} rows")
    max_width = max(row_widths)
    pos_dict = {}
    count = 0
    # creates dict of (xpos,ypos) = imnumber
    for row in range(len(row_widths)):
        row_width = row_widths[row]
        left_pos = int((max_width - row_width) / 2)
        for col in range(row_width):
            if row % 2 == 0:
                # Use min_site offset to match data's site numbering convention
                pos_dict[(int(left_pos + col), row)] = count + min_site
                count += 1
            else:
                right_pos = left_pos + row_width - 1
                # Use min_site offset to match data's site numbering convention
                pos_dict[(int(right_pos - col), row)] = count + min_site
                count += 1
    # make dict into df
    pos_df = (
        pd.DataFrame.from_dict(pos_dict, orient="index")
        .reset_index()
        .rename(columns={"index": "loc", 0: "Metadata_Site"})
    )
    pos_df[["x_loc", "y_loc"]] = pd.DataFrame(
        pos_df["loc"].tolist(), index=pos_df.index
    )
else:
    print("No geometry provided - spatial plot will be skipped")

if pos_df is not None:
    print(f"Position mapping created for {len(pos_df)} sites (starting at site {min_site})")
"""
# %% [markdown]
# ## Prepare Data for Analysis

# %%
df_shift = df_image[[x for x in shift_cols if 'MI' not in x] + id_list]
df_shift = pd.melt(df_shift, id_vars=id_list)
df_corr = df_image[[x for x in corr_cols if 'MI' not in x] + id_list]
df_corr = pd.melt(df_corr, id_vars=id_list)
if MI_cols:
    df_shift_MI = df_image[[x for x in shift_cols if 'MI' in x] + id_list]
    df_shift_MI = pd.melt(df_shift_MI, id_vars=id_list).dropna()
    df_corr_MI = df_image[[x for x in corr_cols if 'MI' in x] + id_list]
    df_corr_MI = pd.melt(df_corr_MI, id_vars=id_list).dropna()

print("Prepared data:")
print(f"  Shifts: {len(df_shift)} rows")
print(f"  All correlations: {len(df_corr)} rows")

# %% [markdown]
# ## Pixel Shifts Analysis - ORIGINAL NCC ALIGNMENT METHOD
#
# ### Pixels shifted to align the second round (no axis limits)

# %%
g = sns.catplot(
    data=df_shift,
    x="value",
    y="variable",
    orient="h",
    col="Metadata_Well",
    col_wrap=4,
)
for ax in g.axes.flat:
    ax.tick_params(labelbottom=True)
plt.show()

# %% [markdown]
# ### Pixels shifted to align the second round (x axis limited to a range)

# %%
g = sns.catplot(
    data=df_shift,
    x="value",
    y="variable",
    orient="h",
    col="Metadata_Well",
    col_wrap=4,
)
for ax in g.axes.flat:
    ax.tick_params(labelbottom=True)
g.set(xlim=(-200, 200))
plt.show()

# %% [markdown]
# ### Summary: Sites with large shifts

# %%
value = shift_threshold
temp = (
    df_shift.loc[df_shift["value"] > value]
    .groupby(["Metadata_Plate", "Metadata_Well", "Metadata_Site"])
    .count()
    .reset_index()
)
for well in temp["Metadata_Well"].unique():
    print(
        f"{well} has {len(temp.loc[temp['Metadata_Well'] == well])} site with shift more than {value} (out of {imperwell})"
    )

# %% [markdown]
# ### Spatial distribution of large shifts
#
# Plot size of shift by location, ignoring shifts >200

# %%
"""
if pos_df is not None:
    temp = (
        df_shift.loc[df_shift["value"] > value]
        .groupby(["Metadata_Plate", "Metadata_Well", "Metadata_Site"])
        .max()
        .reset_index()
        .merge(pos_df)
    )
    temp = temp.loc[temp["value"] < 200]

    if len(temp) > 0:
        g = sns.relplot(
            data=temp,
            x="x_loc",
            y="y_loc",
            hue="value",  # hue_norm=(0,200),
            col="Metadata_Well",
            col_wrap=3,
            palette="viridis",
            marker="s",
            s=150,
        )
        print(g._legend_data)
        plt.show()
    else:
        print(f"No sites with shifts >{value} and <200 pixels")
else:
    print("Skipping spatial plot - no geometry provided")
"""
# %% [markdown]
# ## Correlation Analysis - ORIGINAL NCC ALIGNMENT METHOD
#
# ### DNA correlations after alignment
#
# Need all points to be better than red line

# %%
g = sns.catplot(
    data=df_corr,
    y="value",
    x="Metadata_Well",
)
g.refline(y=corr_threshold, color="red")
g.set(ylim=(0, None))
plt.show()

# %% [markdown]
# ### Summary: Correlation statistics

# %%
print(
    f"{len(df_corr.groupby(['Metadata_Plate', 'Metadata_Well', 'Metadata_Site']))} total sites"
)
print(
    f"{len(df_corr.loc[df_corr['value'] < 0.9])} sites with correlation <.9"
)
print(
    f"{len(df_corr.loc[df_corr['value'] < 0.8])} sites with correlation <.8"
)
# Print Awful alignment scores after alignment
df_corr.loc[df_corr['value'] < 0.5].sort_values(by="value").head(20)

# %% [markdown]
# ### Summary: Large pixel shifts - ORIGINAL NCC ALIGNMENT METHOD

# %%
# Print huge pixel shifts
print(
    f"{len(df_shift.loc[df_shift['value'] > 100])} images shifted with huge pixel shifts"
)

df_shift.loc[df_shift["value"] > 100].sort_values(by="value", ascending=False).head(20)

# %% [markdown]
# ### Overlap of Thresholded Images
# #### (Handles well edge better than correlation)

# %%
# Alignment quality using thresholding
# Handles well edge much better than image correlation
if OL_cols:
    g = sns.catplot(
    data=df_image,
    y=[x for x in OL_cols if 'MI' not in x][0],
    x="Metadata_Well",
    )
    g.refline(y=.8, color="red")
    g.set(ylim=(0, 1.05))
    g.set(title='Overlap of Thresholded Images')
    plt.show()

# %% [markdown]
# ## Pixel Shifts Analysis - MI ALIGNMENT METHOD
# If NCC alignment fails
# ### Pixels shifted to align second cycle (no axis limits)

# %%
if MI_cols:
    sns.catplot(
        data=df_shift_MI,
        x="value",
        y="variable",
        orient="h",
        col="Metadata_Well",
        col_wrap=4,
    )
    plt.show()

# %% [markdown]
# ### Pixels shifted to align second cycle (x axis limited to a range)

# %%
if MI_cols:
    g = sns.catplot(
        data=df_shift_MI,
        x="value",
        y="variable",
        orient="h",
        col="Metadata_Well",
        col_wrap=4,
    )
    g.set(xlim=(-200, 200))

# %% [markdown]
# ### Summary: Sites with large shifts

# %%
if MI_cols:
    value = shift_threshold
    temp = (
        df_shift_MI.loc[df_shift_MI["value"] > value]
        .groupby(["Metadata_Plate", "Metadata_Well", "Metadata_Site"])
        .count()
        .reset_index()
    )
    for well in temp["Metadata_Well"].unique():
        print(
            f"{well} has {len(temp.loc[temp['Metadata_Well'] == well])} site with shift more than {value} (out of {imperwell})"
        )

# %% [markdown]
# ### Spatial distribution of large shifts
#
# Plot size of shift by location, ignoring shifts >200

# %%
"""
if MI_cols and pos_df is not None:
    temp = (
        df_shift_MI.loc[df_shift_MI["value"] > value]
        .groupby(["Metadata_Plate", "Metadata_Well", "Metadata_Site"])
        .max()
        .reset_index()
        .merge(pos_df)
    )
    temp = temp.loc[temp["value"] < 200]

    if len(temp) > 0:
        g = sns.relplot(
            data=temp,
            x="x_loc",
            y="y_loc",
            hue="value",  # hue_norm=(0,200),
            col="Metadata_Well",
            col_wrap=3,
            palette="viridis",
            marker="s",
            s=150,
        )
        print(g._legend_data)
        plt.show()
    else:
        print(f"No sites with shifts >{value} and <200 pixels")
else:
    print("Skipping spatial plot - no geometry provided")
"""
# %% [markdown]
# ## Correlation Analysis - MI ALIGNMENT METHOD
#
# ### DNA correlations after alignment (all pairwise comparisons)
#
# Need all points to be better than red line

# %%
if MI_cols:
    g = sns.catplot(
        data=df_corr_MI,
        y="value",
        x="Metadata_Well",
    )
    g.refline(y=corr_threshold, color="red")
    g.set(ylim=(0, 1.05))
    plt.show()

# %% [markdown]
# ### Summary: Correlation statistics

# %%
if MI_cols:
    print("For correlations to Cycle01")
    print(
        f"{len(df_corr_MI.groupby(['Metadata_Plate', 'Metadata_Well', 'Metadata_Site']))} total sites"
    )
    print(
        f"{len(df_corr_MI.loc[df_corr_MI['value'] < 0.9])} sites with correlation <.9"
    )
    print(
        f"{len(df_corr_MI.loc[df_corr_MI['value'] < 0.8])} sites with correlation <.8"
    )
    # Print Awful alignment scores after alignment
    df_corr_MI.loc[df_corr_MI['value'] < 0.8].sort_values(by="value").head(20)

# %%
# Print mediocre alignment score after alignment
if MI_cols:
    df_corr_MI.loc[df_corr_MI["value"] < 0.5].sort_values(
        by="value", ascending=False
    ).head(20)

# %% [markdown]
# ### Summary: Large pixel shifts - MI ALIGNMENT METHOD

# %%
# Print huge pixel shifts
if MI_cols:
    print(
        f"{len(df_shift_MI.loc[df_shift_MI['value'] > 100])} images shifted with huge pixel shifts"
    )

    df_shift_MI.loc[df_shift_MI["value"] > 100].sort_values(by="value", ascending=False).head(20)

# %
if OL_cols and MI_cols:
    g = sns.catplot(
        data=df_image,
        y=[x for x in OL_cols if 'MI' in x][0],
        x="Metadata_Well",
        )
    g.refline(y=.8, color="red")
    g.set(ylim=(0, 1.05))
    g.set(title='Overlap of Thresholded Images AFTER MI alignment')
    plt.show()
