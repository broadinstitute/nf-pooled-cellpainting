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
# # Pipeline 7 QC: Barcode Preprocessing Analysis

# %%
import os
from pathlib import Path
import pandas as pd
import seaborn as sns
import datetime
import matplotlib.pyplot as plt
import matplotlib.lines as mlines

# %matplotlib inline

# %% tags=["parameters"]
# PAPERMILL PARAMETERS
# Set variables
numcycles = 12
imperwell = 320
input_dir = "../data/Source1/images/Batch1/images_corrected/barcoding/Plate1"
output_dir = "../data/Source1/workspace/qc_reports/7_preprocessing/Plate1"
barcode_library_path = "../data/Source1/workspace/metadata/Barcodes.csv"
row_widths = [
    4,
    8,
    12,
    14,
    16,
    18,
    18,
    20,
    20,
    20,
    20,
    20,
    20,
    20,
    18,
    18,
    16,
    14,
    12,
    8,
    4,
]

# Geometry override (optional - set rows/columns for square, or leave None for circular)
rows = None
columns = None

# Cache control
use_cache = True

# %%
# Process parameters and create output directory
Path(output_dir).mkdir(parents=True, exist_ok=True)

print("Configuration:")
print(f"  numcycles: {numcycles}")
print(f"  imperwell: {imperwell}")
print(f"  input_dir: {input_dir}")
print(f"  output_dir: {output_dir}")
print(f"  barcode_library_path: {barcode_library_path}")
if rows and columns:
    print(f"  geometry: square {rows}x{columns}")
elif row_widths:
    print(f"  geometry: circular with {len(row_widths)} rows")

# %% [markdown]
# ## sgRNA library

# %%
bc_df = pd.read_csv(barcode_library_path)

# Normalize gene column name to 'Gene'
if "gene_symbol" in bc_df.columns:
    bc_df = bc_df.rename(columns={"gene_symbol": "Gene"})
elif "target_symbol" in bc_df.columns:
    bc_df = bc_df.rename(columns={"target_symbol": "Gene"})
elif "Gene" not in bc_df.columns:
    raise ValueError("Barcode library must contain 'Gene', 'gene_symbol', or 'target_symbol' column")

# Normalize barcode column name to 'Barcode'
if "sgRNA" in bc_df.columns:
    bc_df = bc_df.rename(columns={"sgRNA": "Barcode"})
elif "barcode_to_call" in bc_df.columns:
    bc_df = bc_df.rename(columns={"barcode_to_call": "Barcode"})
elif "Barcode" not in bc_df.columns:
    raise ValueError("Barcode library must contain 'Barcode', 'sgRNA', or 'barcode_to_call' column")

gene_col = "Gene"
barcode_col = "Barcode"

# %%
# Describe barcodes
print(len(bc_df), "total barcodes in library")
rep5 = sum(
    [
        any(repeat in read for repeat in ["AAAAA", "CCCCC", "GGGGG", "TTTTT"])
        for read in bc_df[barcode_col]
    ]
)
rep6 = sum(
    [
        any(repeat in read for repeat in ["AAAAAA", "CCCCCC", "GGGGGG", "TTTTTT"])
        for read in bc_df[barcode_col]
    ]
)
rep7 = sum(
    [
        any(repeat in read for repeat in ["AAAAAAA", "CCCCCCC", "GGGGGGG", "TTTTTTT"])
        for read in bc_df[barcode_col]
    ]
)
print("For full read")
print(rep5, "barcodes with 5 repeats", rep5 / len(bc_df), "% 5 repeats")
print(rep6, "barcodes with 6 repeats", rep6 / len(bc_df), "% 6 repeats")
print(rep7, "barcodes with 7 repeats", rep7 / len(bc_df), "% 7 repeats")

rep5 = sum(
    [
        any(repeat in read[:10] for repeat in ["AAAAA", "CCCCC", "GGGGG", "TTTTT"])
        for read in bc_df[barcode_col]
    ]
)
rep6 = sum(
    [
        any(repeat in read[:10] for repeat in ["AAAAAA", "CCCCCC", "GGGGGG", "TTTTTT"])
        for read in bc_df[barcode_col]
    ]
)
rep7 = sum(
    [
        any(
            repeat in read[:10]
            for repeat in ["AAAAAAA", "CCCCCCC", "GGGGGGG", "TTTTTTT"]
        )
        for read in bc_df[barcode_col]
    ]
)
print("For 10 nt read")
print(rep5, "barcodes with 5 repeats", rep5 / len(bc_df), "% 5 repeats")
print(rep6, "barcodes with 6 repeats", rep6 / len(bc_df), "% 6 repeats")
print(rep7, "barcodes with 7 repeats", rep7 / len(bc_df), "% 7 repeats")

# %%
dflist = []
for cycle in range(1, numcycles + 1):
    bc_df["PerCycle"] = bc_df[barcode_col].str.slice(cycle - 1, cycle)
    BarcodeCat = bc_df["PerCycle"].str.cat()
    dflist.append(
        {
            "Cycle": int(cycle),
            "Nucleotide": "A",
            "Frequency": float(BarcodeCat.count("A")) / float(len(BarcodeCat)),
        }
    )
    dflist.append(
        {
            "Cycle": int(cycle),
            "Nucleotide": "C",
            "Frequency": float(BarcodeCat.count("C")) / float(len(BarcodeCat)),
        }
    )
    dflist.append(
        {
            "Cycle": int(cycle),
            "Nucleotide": "G",
            "Frequency": float(BarcodeCat.count("G")) / float(len(BarcodeCat)),
        }
    )
    dflist.append(
        {
            "Cycle": int(cycle),
            "Nucleotide": "T",
            "Frequency": float(BarcodeCat.count("T")) / float(len(BarcodeCat)),
        }
    )
df_parsed = pd.DataFrame(dflist)
g = sns.lineplot(x="Cycle", y="Frequency", hue="Nucleotide", data=df_parsed)
g.set_ylim([0.1, 0.5])
handles, labels = g.get_legend_handles_labels()
g.legend(handles=handles[0:], labels=labels[0:])
g.set_xticks(list(range(1, numcycles + 1)))
plt.title("Nucleotide Frequency by Cycle in Barcode Library")
plt.tight_layout()
plt.savefig(
    Path(output_dir) / "library_nucleotide_frequency.png", dpi=150, bbox_inches="tight"
)
plt.show()

# %% [markdown]
# ## Barcode Calling

# %%
# Useful function for merging CSVs contained in folders within one folder


def merge_csvs(csvfolder, filename, column_list=None):
    """csvfolder is a path to a folder
    Iterates over all of the folders inside of that CSVfolder
    Merges the CSVs that match the filename into one dataframe
    If a column list is passed, it keeps columns defined in the column list
    Prints a time stamp every 500 csvs
    Returns the merged dataframe
    """

    df_dict = {}
    count = 0
    all_items = os.listdir(csvfolder)
    # Filter for input_* folders if they exist
    input_folders = [f for f in all_items if f.startswith('input_') and os.path.isdir(os.path.join(csvfolder, f))]
    folderlist = input_folders if input_folders else all_items

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


# %%
# Merge Foci csvs
# Run if csvs are in separate folders
filename = "BarcodePreprocessing_Foci.csv"
column_list = [
    "ImageNumber",
    "ObjectNumber",
    "Metadata_Plate",
    "Metadata_Site",
    "Metadata_Well",
    "Barcode_BarcodeCalled",
    "Barcode_MatchedTo_Barcode",
    "Barcode_MatchedTo_GeneCode",
    "Barcode_MatchedTo_ID",
    "Barcode_MatchedTo_Score",
]

cache_file = Path(output_dir) / "cached_barcode_foci.parquet"
allfolders = os.listdir(input_dir)
# Filter for input_* folders if they exist
input_folders = [f for f in allfolders if f.startswith('input_') and os.path.isdir(os.path.join(input_dir, f))]
folderlist = input_folders if input_folders else allfolders
test_file = os.path.join(input_dir, folderlist[0], filename)
test_df = pd.read_csv(test_file, nrows=0)
thresh_cols = [x for x in test_df.columns if '_Threshold_' in x]
int_cols = []
median_cols = []
if thresh_cols: # used for 2/3 color
    median_cols = [x for x in thresh_cols if '_MedianIntensity_' in x]
    int_cols = [x for x in thresh_cols if '_IntegratedIntensity_' in x]
    column_list = column_list + median_cols + int_cols

# Load data with caching support
if use_cache and cache_file.exists():
    print(f"Loading cached data from: {cache_file}")
    df_foci = pd.read_parquet(cache_file)
    print(f"Loaded {len(df_foci)} barcode foci from cache")
else:
    print(f"Loading data from: {input_dir}")
    df_foci = merge_csvs(input_dir, filename, column_list)
    print(f"Loaded {len(df_foci)} barcode foci")

    # Cache for future use
    print(f"Caching data to: {cache_file}")
    df_foci.to_parquet(cache_file, compression="gzip", index=False)
    print("Cache saved")

# Detect site numbering convention (0-based or 1-based)
min_site = df_foci["Metadata_Site"].min()
max_site = df_foci["Metadata_Site"].max()
print(f"Detected site numbering: starting at {min_site} ({'0-based' if min_site == 0 else '1-based'})")
print(f"Total sites per well: {max_site - min_site + 1}")

# %%
# useful dataframe manipulations
df_foci.sort_values(by=["Metadata_Well", "Metadata_Site"], inplace=True)
df_foci["well-site"] = (
    df_foci["Metadata_Well"] + "-" + df_foci["Metadata_Site"].astype(str)
)
df_foci_well_groups = df_foci.groupby("Metadata_Well")

print(
    sum(df_foci["Barcode_MatchedTo_Score"] == 1)
    * 100.0
    / sum(df_foci["Barcode_MatchedTo_Score"] >= 0),
    " percent perfect overall",
)
print(f"{len(df_foci.loc[df_foci['Barcode_MatchedTo_Score'] == 1])} count perfect foci")
print(
    sum(df_foci["Barcode_MatchedTo_Score"] >= 1-1/numcycles)
    * 100.0
    / sum(df_foci["Barcode_MatchedTo_Score"] >= 0),
    " percent perfect and off by one",
)

# Count the matches (duplicates in list are counted individually)
matchin7_count = sum(1 for s in df_foci['Barcode_BarcodeCalled'] if s[:7] in [x[:7] for x in bc_df["Barcode"]])
print (matchin7_count/len(df_foci) *100, " percent perfect match in first 7 cycles")

# Count the matches (duplicates in list are counted individually)
matchinEND5_count = sum(1 for s in df_foci['Barcode_BarcodeCalled'] if s[-5:] in [x[-5:] for x in bc_df["Barcode"]])
print (matchinEND5_count/len(df_foci) *100, " percent perfect match in last 5 cycles")

sns.displot(df_foci["Barcode_MatchedTo_Score"], kde=False)
plt.title("Barcode Match Score Distribution")
plt.tight_layout()
plt.savefig(
    Path(output_dir) / "barcode_score_distribution.png", dpi=150, bbox_inches="tight"
)
plt.show()

# %%
sns_displot = sns.displot(
    df_foci, x="Barcode_MatchedTo_Score", col="Metadata_Well", col_wrap=3
)
plt.tight_layout()
plt.savefig(
    Path(output_dir) / "barcode_score_distribution_per_well.png",
    dpi=150,
    bbox_inches="tight",
)
plt.show()

# %%
readlist = df_foci["Barcode_BarcodeCalled"]
print("% Reads with >4 repeat nucleotide calls")
print(
    100
    * pd.Series(
        [
            any(repeat in read for repeat in ["AAAAA", "CCCCC", "GGGGG", "TTTTT"])
            for read in readlist
        ]
    ).mean()
)

print("% Reads with >4 repeat X calls")
print(100*len([x for x in readlist if 'XXXXX' in x])/len(readlist))
print("% Reads with >4 repeat A calls")
print(100*len([x for x in readlist if 'AAAAA' in x])/len(readlist))
print("% Reads with >4 repeat C calls")
print(100*len([x for x in readlist if 'CCCCC' in x])/len(readlist))
print("% Reads with >4 repeat G calls")
print(100*len([x for x in readlist if 'GGGGG' in x])/len(readlist))
print("% Reads with >4 repeat T calls")
print(100*len([x for x in readlist if 'TTTTT' in x])/len(readlist))

print("% Reads that are all unassigned (X) calls")
print(100*len([x for x in readlist if set(x)=={'X'}])/len(readlist))

print("% Reads with unassigned (X) nucleotide calls")
print(100*len([x for x in readlist if 'X' in x])/len(readlist))

# %%
dflist = []
for cycle in range(1, numcycles + 1):
    df_foci["PerCycle"] = df_foci["Barcode_BarcodeCalled"].str.slice(cycle - 1, cycle)
    BarcodeCat = df_foci["PerCycle"].str.cat()
    dflist.append(
        {
            "Cycle": int(cycle),
            "Nucleotide": "A",
            "Frequency": float(BarcodeCat.count("A")) / float(len(BarcodeCat)),
        }
    )
    dflist.append(
        {
            "Cycle": int(cycle),
            "Nucleotide": "C",
            "Frequency": float(BarcodeCat.count("C")) / float(len(BarcodeCat)),
        }
    )
    dflist.append(
        {
            "Cycle": int(cycle),
            "Nucleotide": "G",
            "Frequency": float(BarcodeCat.count("G")) / float(len(BarcodeCat)),
        }
    )
    dflist.append(
        {
            "Cycle": int(cycle),
            "Nucleotide": "T",
            "Frequency": float(BarcodeCat.count("T")) / float(len(BarcodeCat)),
        }
    )
    dflist.append(
        {
            "Cycle": int(cycle),
            "Nucleotide": "X",
            "Frequency": float(BarcodeCat.count("X")) / float(len(BarcodeCat)),
        }
    )
df_parsed = pd.DataFrame(dflist)
g = sns.lineplot(x="Cycle", y="Frequency", hue="Nucleotide", data=df_parsed)
g.set_ylim([0.1, 0.5])
handles, labels = g.get_legend_handles_labels()
g.legend(handles=handles[0:], labels=labels[0:])
g.set_xticks(list(range(1, numcycles + 1)))
plt.title("Observed Nucleotide Frequency by Cycle")
plt.tight_layout()
plt.savefig(
    Path(output_dir) / "observed_nucleotide_frequency.png", dpi=150, bbox_inches="tight"
)
plt.show()

# %%
g = sns.lineplot(x="Cycle", y="Frequency", hue="Nucleotide", data=df_parsed)
handles, labels = g.get_legend_handles_labels()
g.legend(handles=handles[0:], labels=labels[0:])
g.set_xticks(list(range(1, numcycles + 1)))
plt.title("Observed Nucleotide Frequency by Cycle")
plt.tight_layout()
plt.savefig(
    Path(output_dir) / "observed_nucleotide_frequency_noYlim.png", dpi=150, bbox_inches="tight"
)
plt.show()


# %%
def returnbadcycle(query, target):
    if pd.isna(query) or pd.isna(target):
        return None
    for x in range(len(query)):
        if query[x] != target[x]:
            return x + 1


thresh = 1 - 1 / numcycles
df_onemismatch = df_foci.query(f"1 > Barcode_MatchedTo_Score >= {thresh}").reset_index(
    drop=True
)

if len(df_onemismatch) > 0:
    df_onemismatch["BadCycle"] = df_onemismatch.apply(
        lambda x: returnbadcycle(
            x["Barcode_BarcodeCalled"], x["Barcode_MatchedTo_Barcode"]
        ),
        axis=1,
    )
    sns.catplot(
        data=df_onemismatch, col="Metadata_Well", x="BadCycle", kind="count", col_wrap=3
    )
    plt.suptitle("Distribution of Mismatch Cycles (Near-Perfect Matches)")
    plt.tight_layout()
    plt.savefig(
        Path(output_dir) / "mismatch_cycle_distribution.png",
        dpi=150,
        bbox_inches="tight",
    )
    plt.show()
else:
    print(f"No near-perfect mismatches found (all scores are either 1.0 or < {thresh})")

# %
def plot_chan_combos(df_full, cols,title, numcycles):
    channels = ['488', '568', '647']
    df = df_full.copy()
    for cycle in [f"{i:02d}" for i in range(1, numcycles+1)]:
        bool_df = df[[x for x in cols if f'Cycle{cycle}' in x]] > 0

        # We zip the boolean values with the channel names and join the True ones with an underscore
        df[f'Pattern_Cycle{cycle}'] = bool_df.apply(
            lambda row: '_'.join([ch for ch, is_positive in zip(channels, row) if is_positive]),
            axis=1
        )

        # Replace empty strings with 'None'
        df[f'Pattern_Cycle{cycle}'] = df[f'Pattern_Cycle{cycle}'].replace('', 'None')

    pattern_cols = [col for col in df.columns if 'Pattern_Cycle' in col]

    df_melted = df.melt(
        value_vars=pattern_cols,
        var_name='Cycle_Col',
        value_name='Pattern'
    )

    # Clean up the string so the x-axis just shows the cycle number (e.g., '01', '02')
    df_melted['Cycle'] = df_melted['Cycle_Col'].str.replace('Pattern_Cycle', '')

    # Calculate the counts by grouping by the Cycle and the Pattern
    df_counts = df_melted.groupby(['Cycle', 'Pattern']).size().reset_index(name='Count')

    plt.figure(figsize=(12, 6))

    ax = sns.lineplot(
        data=df_counts,
        x='Cycle',
        y='Count',
        hue='Pattern',     # This creates a separate line for each channel combination
        marker='o',        # Adds dots at each cycle point
        linewidth=2.5
    )
    plt.xlabel('Cycle', fontsize=12)
    plt.ylabel('Foci Count', fontsize=12)
    # Use legend for without adding the kit legends
    #plt.legend(title='Channel Combination', bbox_to_anchor=(1.01, 1), loc='upper left')
    plt.title(title)

    handles, labels = ax.get_legend_handles_labels()
    color_map = {label: handle.get_color() for handle, label in zip(handles, labels)}

    def get_color(pattern):
        return color_map.get(pattern, 'black')

    # Position the main legend
    main_legend = plt.legend(title='Channel Combination', bbox_to_anchor=(1.02, 1), loc='upper left')
    ax.add_artist(main_legend) # We must use add_artist() so the next legends don't overwrite this one

    nova_6000_lines = [
        mlines.Line2D([], [], color=get_color('568_647'), marker='o', lw=2, label='A = 568+647'),
        mlines.Line2D([], [], color=get_color('568'), marker='o', lw=2, label='T = 568'),
        mlines.Line2D([], [], color=get_color('647'), marker='o', lw=2, label='C = 647'),
        mlines.Line2D([], [], color=get_color('None'), marker='o', lw=2, label='G = None')
    ]
    nova_6000_legend = ax.legend(handles=nova_6000_lines, title='Novaseq 6000',
                                bbox_to_anchor=(1.02, 0.5), loc='upper left')
    ax.add_artist(nova_6000_legend)

    nova_x_lines = [
        mlines.Line2D([], [], color=get_color('488_647'), marker='o', lw=2, label='A = 488+647'),
        mlines.Line2D([], [], color=get_color('488_568'), marker='o', lw=2, label='C = 488+568'),
        mlines.Line2D([], [], color=get_color('568'), marker='o', lw=2, label='T = 568'),
        mlines.Line2D([], [], color=get_color('None'), marker='o', lw=2, label='G = None')
    ]
    ax.legend(handles=nova_x_lines, title='Novaseq X',
            bbox_to_anchor=(1.02, 0.25), loc='upper left')

    plt.tight_layout()
    plt.show()
if int_cols:
    plot_chan_combos(df_foci, int_cols, 'Integrated Intensity', numcycles)

# %%
if median_cols:
    plot_chan_combos(df_foci, median_cols,'Median Intensity', numcycles)

# %%
perfect_df = df_foci[df_foci["Barcode_MatchedTo_Score"] == 1]

print(f"The number of unique genes in the library is {len(bc_df[gene_col].unique())}")
print(
    f"Perfect barcodes are detected for {len(df_foci.loc[df_foci['Barcode_MatchedTo_Score'] == 1]['Barcode_MatchedTo_GeneCode'].unique())} genes\n"
)
print("The 10 most detected genes are:")
print(
    df_foci.loc[df_foci["Barcode_MatchedTo_Score"] == 1]
    .Barcode_MatchedTo_GeneCode.value_counts()
    .head(n=10)
)
print(
    f"\nThe number of unique barcodes in the library is {len(bc_df[barcode_col].unique())}"
)
print(
    f"Perfect barcodes are detected for {len(df_foci.loc[df_foci['Barcode_MatchedTo_Score'] == 1]['Barcode_MatchedTo_Barcode'].unique())} of them\n"
)
print("The 10 most detected barcodes are:")
print(
    df_foci.loc[df_foci["Barcode_MatchedTo_Score"] == 1]
    .Barcode_MatchedTo_Barcode.value_counts()
    .head(n=10)
)
