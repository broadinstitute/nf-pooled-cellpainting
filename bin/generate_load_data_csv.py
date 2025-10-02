#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "pandas",
# ]
# ///
"""
LoadData CSV generator for PCPIP CellProfiler pipelines.

Generates LoadData CSVs by predicting output filenames from patterns, eliminating
the need for filesystem scanning. Each pipeline's outputs are deterministic based
on the input samplesheet metadata.

Key concepts:
- Pipelines 1,5: Read raw images, output illumination functions
- Pipelines 2,6: Apply illumination using outputs from 1,5
- Pipelines 3,7: Use corrected images from 2,6 (no scanning needed - we predict the names)
- Pipeline 9: Uses stitched tiles from pipelines 4,8 (FIJI-based, not implemented here)

Nextflow handles file staging into img1/, img2/ subdirectories at runtime.
LoadData CSVs specify the actual input file paths.

Reference LoadData CSV files for validation:
  https://nf-pooled-cellpainting-sandbox.s3.amazonaws.com/data/test-data/fix-s1/Source1/workspace/load_data_csv/Batch1/Plate1_trimmed/load_data_pipeline{1-9}_revised.csv

Usage:
  python scripts/load_data_generate.py data/Source1/workspace/samplesheets/samplesheet1.csv
"""

import pandas as pd
from pathlib import Path

# Default base path used in load_data CSVs (can be overridden via CLI)
DEFAULT_BASE_PATH = "/app/data/Source1/images/Batch1"

def pipeline1(samplesheet_df, base_path=None):
    """
    Pipeline 1: Cell Painting Illumination Calculation
    Input: Raw painting images
    Output: {Plate}_Illum{Channel}.npy
    Groups by: plate
    """
    base_path = base_path or DEFAULT_BASE_PATH
    df = samplesheet_df[samplesheet_df.arm == "painting"]
    rows = []

    for _, row in df.iterrows():
        channels = row["channels"].split(",")
        filename = Path(row["path"]).name
        # Extract parent directory (acquisition folder) from the full path
        # E.g., .../Plate1/20X_CP_Plate1_20240319_122800_179/WellA1_Point...
        # We need the acquisition folder name (parent of the image file)
        acq_folder = Path(row["path"]).parent.name
        plate_dir = (
            f"{base_path}/images/{row['plate']}/{acq_folder}/"  # Add trailing slash
        )

        data = {
            "Metadata_Plate": row["plate"],
            "Metadata_Site": row["site"],
            "Metadata_Well": row["well"],
        }

        # Add all data naturally without worrying about column order
        for ch in channels:
            data[f"PathName_Orig{ch}"] = plate_dir
            data[f"FileName_Orig{ch}"] = filename
            data[f"Frame_Orig{ch}"] = channels.index(ch)

        rows.append(data)

    return pd.DataFrame(rows)


def pipeline2(samplesheet_df, base_path=None):
    """
    Pipeline 2: Cell Painting Apply Illumination
    Input: Raw images + illumination functions
    Output: Plate_{Plate}_Well_{Well}_Site_{Site}_Corr{Channel}.tiff
    Groups by: plate, well
    """
    base_path = base_path or DEFAULT_BASE_PATH
    df = samplesheet_df[samplesheet_df.arm == "painting"]
    rows = []

    for _, row in df.iterrows():
        channels = row["channels"].split(",")
        filename = Path(row["path"]).name
        acq_folder = Path(row["path"]).parent.name
        plate_dir = (
            f"{base_path}/images/{row['plate']}/{acq_folder}/"  # Add trailing slash
        )
        illum_dir = f"{base_path}/illum/{row['plate']}"  # No trailing slash for illum

        data = {
            "Metadata_Plate": row["plate"],
            "Metadata_Site": row["site"],
            "Metadata_Well": row["well"],
        }

        # Add all data naturally without worrying about column order
        for ch in channels:
            data[f"PathName_Orig{ch}"] = plate_dir
            data[f"FileName_Orig{ch}"] = filename
            data[f"Frame_Orig{ch}"] = channels.index(ch)
            data[f"PathName_Illum{ch}"] = illum_dir
            data[f"FileName_Illum{ch}"] = f"{row['plate']}_Illum{ch}.npy"

        rows.append(data)

    return pd.DataFrame(rows)


def pipeline3(samplesheet_df, base_path=None, range_skip=None):
    """
    Pipeline 3: Cell Painting Segmentation Check
    Input: Corrected images from Pipeline 2
    Output: QC metrics (no new images)
    """
    base_path = base_path or DEFAULT_BASE_PATH
    df = samplesheet_df[samplesheet_df.arm == "painting"]
    rows = []

    # Sample subset for QC using range_skip
    if range_skip is None:
        range_skip = 2  # Default: use every 2nd site (0, 2, 4, ...)

    # Select sites based on range_skip (starting from 0)
    unique_sites = sorted(df.site.unique())
    selected_sites = [site for i, site in enumerate(unique_sites) if i % range_skip == 0]

    for _, row in df[df.site.isin(selected_sites)].iterrows():
        channels = row["channels"].split(",")
        output_dir = f"{base_path}/images_corrected/painting/{row['plate']}/{row['plate']}-{row['well']}-{row['site']}/"  # Add trailing slash

        data = {
            "Metadata_Plate": row["plate"],
            "Metadata_Site": row["site"],
            "Metadata_Well": row["well"],
            "Metadata_Well_Value": row["well"],
        }

        # Add all data naturally without worrying about column order
        for ch in channels:
            data[f"PathName_{ch}"] = output_dir
            data[f"FileName_{ch}"] = (
                f"Plate_{row['plate']}_Well_{row['well']}_Site_{row['site']}_Corr{ch}.tiff"
            )

        rows.append(data)

    return pd.DataFrame(rows)


def pipeline4(samplesheet_df):
    """
    Pipeline 4: Cell Painting Stitching (FIJI)
    Input: Corrected images from Pipeline 2
    Output: Stitched whole-well images and cropped tiles
    Note: Not CellProfiler - this would be metadata for FIJI
    """
    # Pipeline 4 uses FIJI, not CellProfiler, so no load_data.csv
    # But we can predict outputs for Pipeline 9
    pass


def pipeline5(samplesheet_df, base_path=None):
    """
    Pipeline 5: Barcoding Illumination Calculation
    Input: Raw barcoding images
    Output: {Plate}_Cycle{N}_Illum{Channel}.npy
    Groups by: plate, cycle
    """
    base_path = base_path or DEFAULT_BASE_PATH
    df = samplesheet_df[samplesheet_df.arm == "barcoding"]
    rows = []

    for _, row in df.iterrows():
        channels = row["channels"].split(",")
        filename = Path(row["path"]).name
        # Extract actual acquisition folder from path instead of hardcoding
        acq_folder = Path(row["path"]).parent.name
        cycle_dir = (
            f"{base_path}/images/{row['plate']}/{acq_folder}/"  # Add trailing slash
        )

        data = {
            "Metadata_Plate": row["plate"],
            "Metadata_Site": row["site"],
            "Metadata_Cycle": row["cycle"],
            "Metadata_Well": row["well"],
        }

        # Add all data naturally without worrying about column order
        for ch in channels:
            data[f"PathName_Orig{ch}"] = cycle_dir
            data[f"FileName_Orig{ch}"] = filename
            data[f"Frame_Orig{ch}"] = channels.index(ch)

        rows.append(data)

    return pd.DataFrame(rows)


def pipeline6(samplesheet_df, base_path=None):
    """
    Pipeline 6: Barcoding Apply Illumination + Alignment

    Complex cycle-based format where columns are Cycle{NN}_{Channel}_{Orig|Illum}.
    Groups across cycles to align multi-cycle barcoding sequences.
    """
    base_path = base_path or DEFAULT_BASE_PATH
    df = samplesheet_df[samplesheet_df.arm == "barcoding"]
    rows = []

    for (well, site), group in df.groupby(["well", "site"]):
        plate = group.iloc[0]["plate"]
        channels = group.iloc[0]["channels"].split(",")

        data = {
            "Metadata_Plate": plate,
            "Metadata_Site": site,
            "Metadata_Well": well,
            "Metadata_Well_Value": well,
        }

        # Build paths for each cycle
        for cycle in sorted(group["cycle"].unique()):
            cycle_row = group[group["cycle"] == cycle].iloc[0]
            # Extract actual acquisition folder from path instead of hardcoding
            acq_folder = Path(cycle_row["path"]).parent.name
            cycle_dir = (
                f"{base_path}/images/{plate}/{acq_folder}/"  # Add trailing slash
            )
            illum_dir = f"{base_path}/illum/{plate}"  # No trailing slash for illum

            for ch in channels:
                # Use different naming convention for pipeline 6
                # Original images
                data[f"PathName_Cycle{cycle:02d}_Orig{ch}"] = cycle_dir
                data[f"FileName_Cycle{cycle:02d}_Orig{ch}"] = Path(
                    cycle_row["path"]
                ).name
                data[f"Frame_Cycle{cycle:02d}_Orig{ch}"] = channels.index(ch)

                # Illumination files
                data[f"PathName_Cycle{cycle:02d}_Illum{ch}"] = illum_dir
                data[f"FileName_Cycle{cycle:02d}_Illum{ch}"] = (
                    f"{plate}_Cycle{cycle}_Illum{ch}.npy"
                )
                # Add Frame column for illumination (even though .npy files don't have frames)
                data[f"Frame_Cycle{cycle:02d}_Illum{ch}"] = 0

        rows.append(data)

    return pd.DataFrame(rows)


def pipeline7(samplesheet_df, base_path=None):
    """
    Pipeline 7: Barcode Preprocessing
    Input: Aligned images from Pipeline 6
    Output: Preprocessed images for barcode calling
    """
    base_path = base_path or DEFAULT_BASE_PATH
    df = samplesheet_df[samplesheet_df.arm == "barcoding"]
    rows = []

    for (well, site), group in df.groupby(["well", "site"]):
        plate = group.iloc[0]["plate"]
        channels = group.iloc[0]["channels"].split(",")
        output_dir = f"{base_path}/images_aligned/barcoding/{plate}/{plate}-{well}-{site}/"  # Add trailing slash

        data = {
            "Metadata_Plate": plate,
            "Metadata_Site": site,
            "Metadata_Well": well,
            "Metadata_Well_Value": well,
        }

        # Predict Pipeline 6 outputs for each cycle/channel
        for cycle in sorted(group["cycle"].unique()):
            for ch in channels:
                if ch == "DNA":
                    # DNA only from cycle 1
                    if cycle == 1:
                        col = f"Cycle{cycle:02d}_DNA"
                        data[f"PathName_{col}"] = output_dir
                        data[f"FileName_{col}"] = (
                            f"Plate_{plate}_Well_{well}_Site_{site}_{col}.tiff"
                        )
                else:
                    col = f"Cycle{cycle:02d}_{ch}"
                    data[f"PathName_{col}"] = output_dir
                    data[f"FileName_{col}"] = (
                        f"Plate_{plate}_Well_{well}_Site_{site}_{col}.tiff"
                    )

        rows.append(data)

    return pd.DataFrame(rows)


def pipeline8(samplesheet_df):
    """
    Pipeline 8: Barcoding Stitching (FIJI)
    Input: Preprocessed barcoding images
    Output: Stitched and cropped tiles
    Note: Not CellProfiler - this would be metadata for FIJI
    """
    # Pipeline 8 uses FIJI, not CellProfiler
    pass


def pipeline9(samplesheet_df, base_path=None, tiles_per_well=None):
    """
    Pipeline 9: Combined Analysis
    Input: Cropped tiles from Pipelines 4 & 8
    Output: Final measurements
    Groups by: well, tile
    """
    base_path = base_path or DEFAULT_BASE_PATH
    df = samplesheet_df[samplesheet_df.arm == "barcoding"]
    rows = []

    # Tiles created by stitching - predict based on grid
    if tiles_per_well is None:
        tiles_per_well = 4  # 2x2 grid for this dataset

    for well in df["well"].unique():
        plate = df.iloc[0]["plate"]
        channels_bc = ["A", "C", "T", "G"]
        channels_cp = ["DNA", "CHN2", "Phalloidin"]

        for tile in range(1, tiles_per_well + 1):
            data = {
                "Metadata_Plate": plate,
                "Metadata_Site": tile,  # Tile number as site
                "Metadata_Well": well,
                "Metadata_Well_Value": well,
            }

            # Barcoding channels from all cycles
            for cycle in [1, 2, 3]:
                for ch in channels_bc:
                    col = f"Cycle{cycle:02d}_{ch}"
                    path = f"{base_path}/images_corrected_cropped/barcoding/{plate}/{plate}-{well}/{col}/"  # Add trailing slash
                    data[f"PathName_{col}"] = path
                    data[f"FileName_{col}"] = (
                        f"{col}_Site_{tile}.tiff"  # Use Site naming
                    )

            # Add Cycle01_DNA separately (special case for pipeline 9)
            data["PathName_Cycle01_DNA"] = (
                f"{base_path}/images_corrected_cropped/barcoding/{plate}/{plate}-{well}/Cycle01_DNA/"
            )
            data["FileName_Cycle01_DNA"] = (
                f"Cycle01_DNA_Site_{tile}.tiff"  # Use Site naming
            )

            # Cell Painting channels (with Corr prefix)
            for ch in channels_cp:
                path = f"{base_path}/images_corrected_cropped/painting/{plate}/{plate}-{well}/Corr{ch}/"  # Add Corr to path too!
                data[f"PathName_Corr{ch}"] = path
                data[f"FileName_Corr{ch}"] = (
                    f"Corr{ch}_Site_{tile}.tiff"  # Use Site naming
                )

            rows.append(data)

    return pd.DataFrame(rows)


def generate_all(samplesheet_path, base_path=None, range_skip=None, tiles_per_well=None):
    """Generate LoadData CSVs for all pipelines with configurable parameters"""
    df = pd.read_csv(samplesheet_path)

    return {
        1: pipeline1(df, base_path),
        2: pipeline2(df, base_path),
        3: pipeline3(df, base_path, range_skip),
        # 4 is FIJI stitching - no CSV
        5: pipeline5(df, base_path),
        6: pipeline6(df, base_path),
        7: pipeline7(df, base_path),
        # 8 is FIJI stitching - no CSV
        9: pipeline9(df, base_path, tiles_per_well),
    }


def normalize_paths_in_df(df):
    """Normalize all paths by removing trailing slashes."""
    for col in df.columns:
        if "PathName" in col and col in df.columns:
            # Remove trailing slashes from paths
            df[col] = df[col].str.rstrip("/")
    return df


def compare_csvs(ref_file, gen_df):
    """Compare generated CSV against reference CSV with strict equivalence checking."""
    try:
        ref_df = pd.read_csv(ref_file)

        # Normalize paths
        ref_df = normalize_paths_in_df(ref_df)
        gen_df = normalize_paths_in_df(gen_df)

        # Check for exact same shape (no filtering, must be identical row count)
        if ref_df.shape != gen_df.shape:
            return (
                False,
                f"✗ DIFFER - Shape mismatch: ref={ref_df.shape}, gen={gen_df.shape}",
            )

        # Check for exact same columns
        ref_cols = set(ref_df.columns)
        gen_cols = set(gen_df.columns)
        if ref_cols != gen_cols:
            missing = ref_cols - gen_cols
            extra = gen_cols - ref_cols
            msg = "✗ DIFFER - Column mismatch"
            if missing:
                msg += f", missing: {missing}"
            if extra:
                msg += f", extra: {extra}"
            return False, msg

        # Sort columns and rows for comparison (allow different ordering)
        ref_df = (
            ref_df.sort_index(axis=1)
            .sort_values(by=list(ref_df.columns))
            .reset_index(drop=True)
        )
        gen_df = (
            gen_df.sort_index(axis=1)
            .sort_values(by=list(gen_df.columns))
            .reset_index(drop=True)
        )

        # Compare with strict equality
        pd.testing.assert_frame_equal(ref_df, gen_df, check_like=True)
        return True, "✓ MATCH (exact equivalence)"
    except AssertionError as e:
        error_msg = str(e)
        return False, f"✗ DIFFER - {error_msg[:150]}..."
    except FileNotFoundError:
        return False, "✗ Reference file not found"


def validate_all(
    csvs, ref_base_path="data/Source1/workspace/load_data_csv/Batch1/Plate1_trimmed"
):
    """Validate all generated CSVs against reference files."""
    results = {}
    for pipeline_num, gen_df in csvs.items():
        ref_file = f"{ref_base_path}/load_data_pipeline{pipeline_num}_revised.csv"
        success, message = compare_csvs(ref_file, gen_df.copy())
        results[pipeline_num] = (success, message)
        print(f"Pipeline {pipeline_num}: {message}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate LoadData CSVs for PCPIP CellProfiler pipelines"
    )
    parser.add_argument("samplesheet", help="Path to samplesheet CSV")
    parser.add_argument(
        "--pipeline",
        type=str,
        default=None,
        help="Comma-separated list of pipeline numbers to generate (e.g., '1,2,3' or '1-3'). If not specified, all pipelines are generated.",
    )
    parser.add_argument(
        "--split-by",
        type=str,
        default=None,
        help="Column name(s) to split samplesheet by. Single column (e.g., 'well') or comma-separated for combinations (e.g., 'plate,well'). Generates separate CSV files for each unique value/combination.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Compare generated CSVs against reference files",
    )
    parser.add_argument(
        "--ref-path",
        default="data/Source1/workspace/load_data_csv/Batch1/Plate1_trimmed",
        help="Path to reference CSV files for validation",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to save generated CSV files (default: current directory)",
    )
    parser.add_argument(
        "--base-path",
        default=None,
        help=f"Base path for LoadData CSVs (default: {DEFAULT_BASE_PATH})",
    )
    parser.add_argument(
        "--range-skip",
        type=int,
        default=None,
        help="Subsampling interval for pipeline 3 QC sites. Uses every Nth site (default: 2, which selects sites 0, 2, 4, ...)",
    )
    parser.add_argument(
        "--tiles-per-well",
        type=int,
        default=None,
        help="Number of tiles per well for pipeline 9 (default: 4)",
    )

    args = parser.parse_args()

    # Parse pipeline numbers
    pipeline_numbers = None
    if args.pipeline:
        pipeline_numbers = []
        for part in args.pipeline.split(","):
            part = part.strip()
            if "-" in part:
                # Handle range like "1-3"
                start, end = map(int, part.split("-"))
                pipeline_numbers.extend(range(start, end + 1))
            else:
                pipeline_numbers.append(int(part))
        # Remove duplicates and sort
        pipeline_numbers = sorted(set(pipeline_numbers))

    # Load samplesheet to check for split-by column
    samplesheet_df = pd.read_csv(args.samplesheet)

    # Parse and validate split-by columns
    split_columns = None
    if args.split_by:
        split_columns = [col.strip() for col in args.split_by.split(",")]
        # Validate all columns exist
        missing_cols = [col for col in split_columns if col not in samplesheet_df.columns]
        if missing_cols:
            raise ValueError(f"Column(s) {missing_cols} not found in samplesheet. Available columns: {', '.join(samplesheet_df.columns)}")

    # Determine split groups
    if split_columns:
        # Get unique combinations of split columns
        split_groups = samplesheet_df.groupby(split_columns).groups
        split_values = sorted(split_groups.keys())
        print(f"Splitting by {split_columns} - found {len(split_values)} unique combinations")
    else:
        split_values = [None]

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process each split group
    for split_value in split_values:
        # Filter samplesheet if splitting
        if split_value is not None:
            # Handle single column vs multiple columns
            if len(split_columns) == 1:
                filtered_df = samplesheet_df[samplesheet_df[split_columns[0]] == split_value]
                split_suffix = f"_{split_value}"
            else:
                # Multiple columns - build filter for each column
                mask = True
                for col, val in zip(split_columns, split_value):
                    mask = mask & (samplesheet_df[col] == val)
                filtered_df = samplesheet_df[mask]
                # Create suffix from all values, joined with underscore
                split_suffix = "_" + "_".join(str(v) for v in split_value)

            # Create temporary samplesheet file for this split
            temp_samplesheet = output_dir / f"temp_samplesheet{split_suffix}.csv"
            filtered_df.to_csv(temp_samplesheet, index=False)
            current_samplesheet = temp_samplesheet
        else:
            current_samplesheet = args.samplesheet
            split_suffix = ""

        # Generate CSVs with configurable parameters
        csvs = generate_all(
            current_samplesheet,
            base_path=args.base_path,
            range_skip=args.range_skip,
            tiles_per_well=args.tiles_per_well,
        )

        # Filter pipelines if specified
        if pipeline_numbers:
            csvs = {num: df for num, df in csvs.items() if num in pipeline_numbers}

        # Save to files
        for num, df in csvs.items():
            # Remove all PathName columns
            df_filtered = df[[col for col in df.columns if not col.startswith("PathName_")]]
            output = output_dir / f"load_data_pipeline{num}{split_suffix}_generated.csv"
            df_filtered.to_csv(output, index=False)

            # Output metadata in a parseable format for Nextflow
            if split_value is not None:
                # Build metadata string
                meta_parts = []
                for col, val in zip(split_columns, split_value if isinstance(split_value, tuple) else [split_value]):
                    meta_parts.append(f"{col}={val}")
                meta_parts.append(f"pipeline={num}")
                meta_str = ",".join(meta_parts)
                print(f"META:{meta_str}:FILE:{output.name}")
            else:
                print(f"Generated {output} with {len(df_filtered)} rows")

        # Clean up temporary samplesheet
        if split_value is not None:
            temp_samplesheet.unlink()

        # Validate if requested (only for non-split runs)
        if args.validate and split_value is None:
            print("\n=== Validation Results ===")
            results = validate_all(csvs, args.ref_path)

            # Summary
            successes = sum(1 for success, _ in results.values() if success)
            print(f"\nSummary: {successes}/{len(results)} pipelines match reference")
