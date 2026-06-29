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
import re
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

# Detect channel naming convention (DNA vs DAPI) by checking first available CSV
channel_name = "DAPI"  # default
folderlist = os.listdir(csvfolder)
test_file = os.path.join(csvfolder, folderlist[0], "BarcodingApplication_Image.csv")
if os.path.isfile(test_file):
    # Read just the header to check column names
    test_df = pd.read_csv(test_file, nrows=0)
    if "Align_Xshift_Cycle02_DNA" in test_df.columns:
        channel_name = "DNA"
        print("Detected channel naming convention: DNA")
    elif "Align_Xshift_Cycle02_DAPI" in test_df.columns:
        channel_name = "DAPI"
        print("Detected channel naming convention: DAPI")
    else:
        print(f"Could not detect channel naming convention, defaulting to {channel_name}")

id_list = ["Metadata_Well", "Metadata_Plate", "Metadata_Site"]

# Load data with caching support
if use_cache and cache_file.exists():
    print(f"Loading cached data from: {cache_file}")
    df_image = pd.read_parquet(cache_file)
    print(f"Loaded {len(df_image)} rows from cache")
else:
    print(f"Loading data from: {csvfolder}")
    df_image = merge_csvs(
        csvfolder, "BarcodingApplication_Image.csv", backup_list=None, filter_string=None
    )

    # have to define column lists after load because not all image sets have all columns
    shift_list = [x for x in df_image.columns if "Align_Xshift_Cycle" in x and "MI" not in x and channel_name in x]
    shift_list.append([x for x in df_image.columns if "Align_Yshift_Cycle" in x and "MI" not in x and channel_name in x])
    corr_list = [x for x in df_image.columns if "Correlation_Correlation_Cycle" in x and "MI" not in x and x.count(channel_name) == 2]
    orig_cols = [x for x in df_image.columns if "Correlation_Correlation" in x and "Orig" in x]
    MI_cols = [x for x in df_image.columns if "MI" in x and channel_name in x]
    print (f"Detected {len(MI_cols)} MI columns for channel {channel_name}")
    debris_cols = [x for x in df_image.columns if "Count_Debris" in x]
    print (f"Detected {len(debris_cols)} debris columns")
    OL_cols = [x for x in df_image.columns if "Overlap_Recall" in x]
    print (f"Detected {len(OL_cols)} Overlap_Recall columns")
    shift_list_MI = [x for x in MI_cols if "Align_Xshift_Cycle" in x or "Align_Yshift_Cycle" in x]
    corr_list_MI = [x for x in MI_cols if "Correlation_Correlation_Cycle" in x]

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

# %%
if (df_image[orig_cols] > 0.95).any().any():
    corr = (df_image[orig_cols] > 0.95).any()
    print("Some input images are very highly correlated. Check the following for accidental duplication:")
    print(corr[corr].index.tolist())

# %% [markdown]
# ## Prepare Data for Analysis

# %%
df_shift = df_image[shift_list + id_list]
df_shift = pd.melt(df_shift, id_vars=id_list)
df_corr = df_image[corr_list + id_list]
df_corr = pd.melt(df_corr, id_vars=id_list)
df_corr_crop = df_image[[x for x in corr_list if "Correlation_Cycle01" in x] + id_list]
df_corr_crop = pd.melt(df_corr_crop, id_vars=id_list)
if MI_cols:
    df_shift_MI = df_image[shift_list_MI + id_list]
    df_shift_MI = pd.melt(df_shift_MI, id_vars=id_list)
    df_corr_MI = df_image[corr_list_MI + id_list]
    df_corr_MI = pd.melt(df_corr_MI, id_vars=id_list)
    df_corr_crop_MI = df_image[[x for x in corr_list_MI if "Correlation_Cycle01" in x] + id_list]
    df_corr_crop_MI = pd.melt(df_corr_crop_MI, id_vars=id_list)

print("Prepared data:")
print(f"  Shifts: {len(df_shift)} rows")
print(f"  All correlations: {len(df_corr)} rows")
print(f"  Cycle01 correlations: {len(df_corr_crop)} rows")

# %% [markdown]
# ## Pixel Shifts Analysis - ORIGINAL NCC ALIGNMENT METHOD
#
# ### Pixels shifted to align each cycle to Cycle01 (no axis limits)

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
    col_wrap=4,
)
g.set(xlim=(-200, 200))
for ax in g.axes.flat:
    ax.tick_params(labelbottom=True)
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
# ## Correlation Analysis - ORIGINAL NCC ALIGNMENT METHOD
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
    col_wrap=4,
)
g.refline(x=corr_threshold, color="red")
g.set(xlim=(0, None))
plt.savefig(
    Path(output_dir) / "alignment_correlations_all.png", dpi=150, bbox_inches="tight"
)
plt.show()

# %% [markdown]
# ### DAPI correlations after alignment (only correlations to Cycle01) - ORIGINAL NCC ALIGNMENT METHOD
#
# Need all points to be better than red line

# %%
g = sns.catplot(
    data=df_corr_crop,
    x="value",
    y="variable",
    orient="h",
    col="Metadata_Well",
    col_wrap=4,
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
# ### Summary: Large pixel shifts - ORIGINAL NCC ALIGNMENT METHOD

# %%
# Print huge pixel shifts
print(
    f"{len(df_shift.loc[df_shift['value'] > 100])} images shifted with huge pixel shifts"
)

df_shift.loc[df_shift["value"] > 100].sort_values(by="value", ascending=False).head(20)

# %%
# Alignment quality using thresholding
# Handles well edge much better than image correlation
def make_plot(df):
    records = []
    for col in [x for x in df.columns if 'Metadata' not in x]:
        # Extract the cycle number (e.g., 'Cycle02')
        cycle_match = re.search(r'(Cycle\d+)', col, flags=re.IGNORECASE)
        cycle_num = cycle_match.group(1) if cycle_match else "Unknown"

        # Grab just this column
        temp_df = df[[col]].copy()
        temp_df.columns = ['Overlap_Recall'] # Standardize the column name
        temp_df['Cycle'] = cycle_num.replace('Cycle','')
        temp_df['Well'] = df['Metadata_Well']

        records.append(temp_df)
    # Combine into a single long DataFrame
    plot_df = pd.concat(records, ignore_index=True)

    plt.figure(figsize=(12, 6))

    g = sns.catplot(
        data=plot_df,
        kind='strip',
        x='Cycle',
        y='Overlap_Recall',
        alpha=0.7,
        col="Well",
        col_wrap=3,
        legend=False      # Legend is redundant since the X-axis already labels the cycles
    )

    min_val = plot_df['Overlap_Recall'].min()
    for ax in g.axes.flat:
        ax.axhline(y=min_val, color='blue', linestyle='--', linewidth=1.5,
                label=f'Global Minimum ({min_val:.3f})')
        ax.axhline(y=0.8, color='red', linestyle='--', linewidth=1.5,
                label='QC Threshold (0.8)')

    # Add a single legend to the whole figure
    handles, labels = g.axes.flat[0].get_legend_handles_labels()
    g.figure.legend(handles, labels, loc='center right', bbox_to_anchor=(1.15, 0.5))

    plt.ylim(0, 1.05)

    plt.tight_layout()
    plt.show()
if OL_cols:
    make_plot(df_image[[x for x in OL_cols if 'MI' not in x]+['Metadata_Well']])

# %% [markdown]
# ## Pixel Shifts Analysis - MI ALIGNMENT METHOD
#
# ### Pixels shifted to align each cycle to Cycle01 (no axis limits)

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
    plt.savefig(
        Path(output_dir) / "alignment_shifts_no_limits_MI.png", dpi=150, bbox_inches="tight"
    )
    plt.show()

# %% [markdown]
# ### Pixels shifted to align each cycle to Cycle01 (x axis limited to a range)

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
    plt.savefig(
        Path(output_dir) / "alignment_shifts_xlim_MI.png", dpi=150, bbox_inches="tight"
    )
    plt.show()

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
# ## Correlation Analysis - MI ALIGNMENT METHOD
#
# ### DAPI correlations after alignment (all pairwise comparisons)
#
# Need all points to be better than red line

# %%
if MI_cols:
    g = sns.catplot(
        data=df_corr_MI,
        x="value",
        y="variable",
        orient="h",
        col="Metadata_Well",
        col_wrap=4,
    )
    g.refline(x=corr_threshold, color="red")
    g.set(xlim=(0, None))
    plt.savefig(
        Path(output_dir) / "alignment_correlations_all_MI.png", dpi=150, bbox_inches="tight"
    )
    plt.show()

# %% [markdown]
# ### DAPI correlations after alignment (only correlations to Cycle01) - MI ALIGNMENT METHOD
#
# Need all points to be better than red line

# %%
if MI_cols:
    g = sns.catplot(
    data=df_corr_crop_MI,
    x="value",
    y="variable",
    orient="h",
    col="Metadata_Well",
    col_wrap=4,
    )
    g.refline(x=corr_threshold, color="red")
    g.set(xlim=(0, None))
    plt.savefig(
        Path(output_dir) / "alignment_correlations_cycle01_MI.png",
        dpi=150,
        bbox_inches="tight",
    )
    plt.show()

# %% [markdown]
# ### Summary: Correlation statistics

# %%
if MI_cols:
    print("For correlations to Cycle01")
    print(
        f"{len(df_corr_crop_MI.groupby(['Metadata_Plate', 'Metadata_Well', 'Metadata_Site']))} total sites"
    )
    print(
        f"{len(df_corr_crop_MI.loc[df_corr_crop_MI['value'] < 0.9])} sites with correlation <.9"
    )
    print(
        f"{len(df_corr_crop_MI.loc[df_corr_crop_MI['value'] < 0.8])} sites with correlation <.8"
    )
    # Print Awful alignment scores after alignment
    df_corr_crop_MI.sort_values(by="value").head(20)

# %%
# Print mediocre alignment score after alignment
if MI_cols:
    df_corr_crop_MI.loc[df_corr_crop_MI["value"] < 0.5].sort_values(
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
    make_plot(df_image[[x for x in OL_cols if 'MI' in x]+['Metadata_Well']])
