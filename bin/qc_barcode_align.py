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
# # Pipeline 6 QC: Barcode Alignment Analysis
#
# Analyzes alignment quality between barcoding cycles by examining pixel shifts
# and correlation scores from Pipeline 6 outputs.

# %% [markdown]
# ## Setup and Configuration

# %%
import os
from pathlib import Path
import pandas as pd
import seaborn as sns
import datetime
import matplotlib.pyplot as plt

# %matplotlib inline

# %% tags=["parameters"]
# PAPERMILL PARAMETERS
# This cell is tagged as "parameters" for Papermill injection
# When running with papermill, these values will be overridden
# When running interactively, edit these defaults directly

# Analysis parameters
numcycles = 3
imperwell = None  # Will be auto-detected from data if None
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
print(f"  numcycles: {numcycles}")
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
def merge_csvs(csvfolder, filename, column_list=None, filter_string=None):
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
                df_dict[eachfolder] = pd.read_csv(
                    os.path.join(csvfolder, eachfolder, filename),
                    index_col=False,
                    usecols=column_list,
                )
            count += 1
            if count % 500 == 0:
                print(count, datetime.datetime.ctime(datetime.datetime.now()))
    print(count, datetime.datetime.ctime(datetime.datetime.now()))
    df_merged = pd.concat(df_dict, ignore_index=True)
    print("done concatenating at", datetime.datetime.ctime(datetime.datetime.now()))

    return df_merged


# %% [markdown]
# ## Create Position Mapping for Spatial Plots
#
# This cell creates a mapping from site number to (x, y) position.
# Supports both square and circular acquisition patterns.

# %%
# Only create position mapping if geometry is provided
pos_df = None

if rows and columns:
    # Square/rectangular acquisition
    print(f"Creating square position mapping: {rows}x{columns}")
    pos_data = []
    for site in range(rows * columns):
        row = site // columns
        col = site % columns
        pos_data.append({"Metadata_Site": site, "x_loc": col, "y_loc": row})
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
                pos_dict[(int(left_pos + col), row)] = count
                count += 1
            else:
                right_pos = left_pos + row_width - 1
                pos_dict[(int(right_pos - col), row)] = count
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
    print(f"Position mapping created for {len(pos_df)} sites")

# %% [markdown]
# ## Load Alignment Data

# %%
csvfolder = input_dir
cache_file = Path(output_dir) / "cached_alignment_data.parquet"

# Build column lists
# Note: Pipeline 6 uses "DNA" channel name (not "DAPI")
shift_list = []
corr_list = []
for cycle in range(1, numcycles + 1):
    if cycle != 1:
        shift_list.append(f"Align_Xshift_Cycle{cycle:02d}_DNA")
        shift_list.append(f"Align_Yshift_Cycle{cycle:02d}_DNA")
    for cycle2 in range(cycle + 1, numcycles + 1):
        corr_list.append(
            f"Correlation_Correlation_Cycle{cycle:02d}_DNA_Cycle{cycle2:02d}_DNA"
        )
id_list = ["Metadata_Well", "Metadata_Plate", "Metadata_Site"]
column_list = id_list + shift_list + corr_list

# Load data with caching support
if use_cache and cache_file.exists():
    print(f"Loading cached data from: {cache_file}")
    df_image = pd.read_parquet(cache_file)
    print(f"Loaded {len(df_image)} rows from cache")
else:
    print(f"Loading data from: {csvfolder}")
    print(
        f"Columns to extract: {len(column_list)} ({len(shift_list)} shifts, {len(corr_list)} correlations)"
    )

    df_image = merge_csvs(
        csvfolder, "BarcodingApplication_Image.csv", column_list, filter_string=None
    )

    print(f"Loaded {len(df_image)} rows")

    # Cache for future use
    # Note: Only columns specified in column_list are loaded and cached
    print(f"Caching data to: {cache_file}")
    df_image.to_parquet(cache_file, compression="gzip", index=False)
    print("Cache saved")

# Auto-detect imperwell if not set
if imperwell is None:
    imperwell = df_image["Metadata_Site"].max() + 1
    print(f"Auto-detected imperwell: {imperwell}")

# %% [markdown]
# ## Prepare Data for Analysis

# %%
df_shift = df_image[shift_list + id_list]
df_shift = pd.melt(df_shift, id_vars=id_list)
df_corr = df_image[corr_list + id_list]
df_corr = pd.melt(df_corr, id_vars=id_list)
df_corr_crop = df_image[[x for x in corr_list if "Correlation_Cycle01" in x] + id_list]
df_corr_crop = pd.melt(df_corr_crop, id_vars=id_list)

print("Prepared data:")
print(f"  Shifts: {len(df_shift)} rows")
print(f"  All correlations: {len(df_corr)} rows")
print(f"  Cycle01 correlations: {len(df_corr_crop)} rows")

# %% [markdown]
# ## Pixel Shifts Analysis
#
# ### Pixels shifted to align each cycle to Cycle01 (no axis limits)

# %%
sns.catplot(
    data=df_shift,
    x="value",
    y="variable",
    orient="h",
    col="Metadata_Well",
    row="Metadata_Plate",
)
plt.savefig(
    Path(output_dir) / "alignment_shifts_no_limits.png", dpi=150, bbox_inches="tight"
)
plt.show()

# %% [markdown]
# ### Pixels shifted to align each cycle to Cycle01 (x axis limited to a range)

# %%
g = sns.catplot(
    data=df_shift,
    x="value",
    y="variable",
    orient="h",
    col="Metadata_Well",
    row="Metadata_Plate",
)
g.set(xlim=(-200, 200))
plt.savefig(
    Path(output_dir) / "alignment_shifts_xlim.png", dpi=150, bbox_inches="tight"
)
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
        plt.savefig(
            Path(output_dir) / "alignment_shifts_spatial.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.show()
    else:
        print(f"No sites with shifts >{value} and <200 pixels")
else:
    print("Skipping spatial plot - no geometry provided")

# %% [markdown]
# ## Correlation Analysis
#
# ### DAPI correlations after alignment (all pairwise comparisons)
#
# Need all points to be better than red line

# %%
g = sns.catplot(
    data=df_corr,
    x="value",
    y="variable",
    orient="h",
    col="Metadata_Well",
    row="Metadata_Plate",
)
g.refline(x=corr_threshold, color="red")
g.set(xlim=(0, None))
plt.savefig(
    Path(output_dir) / "alignment_correlations_all.png", dpi=150, bbox_inches="tight"
)
plt.show()

# %% [markdown]
# ### DAPI correlations after alignment (only correlations to Cycle01)
#
# Need all points to be better than red line

# %%
g = sns.catplot(
    data=df_corr_crop,
    x="value",
    y="variable",
    orient="h",
    col="Metadata_Well",
    row="Metadata_Plate",
)
g.refline(x=corr_threshold, color="red")
g.set(xlim=(0, None))
plt.savefig(
    Path(output_dir) / "alignment_correlations_cycle01.png",
    dpi=150,
    bbox_inches="tight",
)
plt.show()

# %% [markdown]
# ### Summary: Correlation statistics

# %%
print("For correlations to Cycle01")
print(
    f"{len(df_corr_crop.groupby(['Metadata_Plate', 'Metadata_Well', 'Metadata_Site']))} total sites"
)
print(
    f"{len(df_corr_crop.loc[df_corr_crop['value'] < 0.9])} sites with correlation <.9"
)
print(
    f"{len(df_corr_crop.loc[df_corr_crop['value'] < 0.8])} sites with correlation <.8"
)
# Print Awful alignment scores after alignment
df_corr_crop.sort_values(by="value").head(20)

# %%
# Print mediocre alignment score after alignment
df_corr_crop.loc[df_corr_crop["value"] < 0.5].sort_values(
    by="value", ascending=False
).head(20)

# %% [markdown]
# ### Summary: Large pixel shifts

# %%
# Print huge pixel shifts
print(
    f"{len(df_shift.loc[df_shift['value'] > 100])} images shifted with huge pixel shifts"
)

df_shift.loc[df_shift["value"] > 100].sort_values(by="value", ascending=False).head(20)
