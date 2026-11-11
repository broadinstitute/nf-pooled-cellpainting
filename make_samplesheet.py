# /// script
# dependencies = ["marimo", "pandas", "boto3"]
# ///

import marimo

__generated_with = "0.25.2"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _():
    import boto3
    import pandas as pd
    import os
    import re
    from dataclasses import dataclass

    return boto3, os, pd, re


@app.cell
def _(mo):
    ## Initial setup, including states that need to be queryable later

    well_values = {6:{'All':[f"{r}{c:02d}" for r in ['A','B'] for c in range (1,4)],'No edges':[]},
                  24:{'All':[f"{r}{c:02d}" for r in ['A','B','C','D'] for c in range (1,7)], 'No edges':[f"{r}{c:02d}" for r in ['B','C',] for c in range (2,6)],},
                  96:{'All':[f"{r}{c:02d}" for r in ['A','B','C','D','E','F','G','H'] for c in range (1,13)], 'No edges':[f"{r}{c:02d}" for r in ['B','C','D','E','F','G'] for c in range (2,12)]}}

    get_plate_type, set_plate_type = mo.state(96)
    get_pheno_round_number, set_pheno_round_number = mo.state(1)
    return (
        get_pheno_round_number,
        get_plate_type,
        set_pheno_round_number,
        set_plate_type,
        well_values,
    )


@app.cell
def _(mo, set_plate_type, well_values):
    ## Things which get or set state should live in different cells from each other

    plate_type = mo.ui.dropdown(label='Plate type', options=well_values.keys(), value=96, on_change=set_plate_type)
    return (plate_type,)


@app.cell
def _(get_plate_type, mo, well_values):
    ## Things which get or set state should live in different cells from each other

    use_wells = mo.ui.multiselect(label='Choose which specific wells to use (ignored unless using "Custom subset" above)', options=well_values[get_plate_type()]['All'])
    return (use_wells,)


@app.cell
def _(mo, set_pheno_round_number):
    ## Things which get or set state should live in different cells from each other

    phenotyping_rounds = mo.ui.number(label='Cycles of phenotyping', start=1, stop=2, step = 1, value=1,on_change=set_pheno_round_number)
    return (phenotyping_rounds,)


@app.cell
def _(mo, pd):
    ## All UI elements taht don't need to set or get state

    out_folder_explorer=mo.ui.file_browser (label="Directory to place the sample sheet",selection_mode='directory',multiple=False, restrict_navigation=False)
    bucket = mo.ui.text(label='s3 bucket',value="imaging-platform-ssf")
    batch = mo.ui.text(label='Batch name',placeholder="2026_07_14_Batch2")
    plate = mo.ui.text(label='Plate name',placeholder="BR00150248")
    wells_option = mo.ui.dropdown(label='Choose which well pattern to use', options= ['All', 'No edges', 'Custom subset'], value='All')                  
    bc_cycles = mo.ui.number(label='Cycles of barcoding', step = 1, value=12)
    save_cp = mo.ui.checkbox(label='Include phenotyping arm in samplesheet', value=True)
    save_bc = mo.ui.checkbox(label='Include barcoding arm in samplesheet', value=True)
    suffix = mo.ui.text(label='Plate suffix to use if multiple experiments map to the same plate; leave blank otherwise',placeholder="")
    bc_pre_prefix=mo.ui.text(label='On-bucket path to barcoding images folder; should include batch and end in "images/" (with trailing slash)')
    pheno_prefix1=mo.ui.text(label='On-bucket path to phenotyping cycle 1 images folder; should be through the final MeasurementN/Images" (without trailing slash)')
    pheno_prefix2=mo.ui.text(label='On-bucket path to phenotyping cycle 2 images folder; should be through the final MeasurmentN/Images" (without trailing slash)')
    pheno_channel_map1_df = mo.ui.data_editor(data=pd.DataFrame({'Channel Number':['ch1','ch2','ch3','ch4','ch6'],'Channel Name':['Brightfield','ER','WGA','DNA','Phalloidin']}), label="Edit the channel mappings for phenotyping cycle 1; omit channels you do not wish to use")
    pheno_channel_map2_df = mo.ui.data_editor(data=pd.DataFrame({'Channel Number':['ch1','ch2','ch3'],'Channel Name':['RNA','COX4','DNA2']}), label="Edit the channel mappings for phenotyping cycle 2; omit channels you do not wish to use")
    bc_channel_map_df = mo.ui.data_editor(data=pd.DataFrame({'Channel Number':['ch1','ch2','ch3','ch4'],'Channel Name':['DAPI','A568','A488','A647']}), label="Edit the channel mappings for barcoding; only change if acquisition order does")
    return (
        batch,
        bc_channel_map_df,
        bc_cycles,
        bc_pre_prefix,
        bucket,
        out_folder_explorer,
        pheno_channel_map1_df,
        pheno_channel_map2_df,
        pheno_prefix1,
        pheno_prefix2,
        plate,
        save_bc,
        save_cp,
        suffix,
        wells_option,
    )


@app.cell
def _(
    batch,
    bc_channel_map_df,
    bc_cycles,
    get_pheno_round_number,
    mo,
    pheno_channel_map1_df,
    pheno_channel_map2_df,
    phenotyping_rounds,
    plate,
    plate_type,
    suffix,
    use_wells,
    wells_option,
):
    ## Experimental details section for form

    exp_details_stacklist = [mo.hstack([batch,plate]),
            mo.hstack([plate_type, wells_option]),
            use_wells,
            mo.hstack([phenotyping_rounds, bc_cycles]),
            suffix,
            mo.md("#### Channel mapping for the barcoding cycles"),
            mo.md("Only change if the acquisition order changes"),
            bc_channel_map_df,
            mo.md("#### Channel mapping for the first/only phenotyping cycle"),
            mo.md("Omit channels you do not wish to use"),
            pheno_channel_map1_df
           ]
    if get_pheno_round_number() == 2:
        exp_details_stacklist +=  [mo.md("#### Channel mapping for the second phenotyping cycle"), mo.md("Omit channels you do not wish to use"), pheno_channel_map2_df]
    return (exp_details_stacklist,)


@app.cell
def _(
    bc_pre_prefix,
    bucket,
    get_pheno_round_number,
    pheno_prefix1,
    pheno_prefix2,
):
    ## On bucket details section for form

    storage_location_stacklist = [bucket,
                                  bc_pre_prefix,
                                  pheno_prefix1,   
    ]
    if get_pheno_round_number() == 2:
        storage_location_stacklist += [pheno_prefix2]
    return (storage_location_stacklist,)


@app.cell
def _(mo):
    mo.md("""
    ## Create the samplesheet for Nextflow runs for data stored on AWS.

    Note: this assumes run on a computer with AWS credentials saved.
    """)
    return


@app.cell
def _(exp_details_stacklist, mo, storage_location_stacklist):
    mo.accordion({
       "### Experimental details":
       mo.vstack(exp_details_stacklist
           ),
        "### Details about storage locations on S3":
           mo.vstack(
               storage_location_stacklist
           )},multiple=True)


    return


@app.cell
def _(mo, out_folder_explorer, save_bc, save_cp):
    mo.vstack([mo.hstack([save_cp, save_bc]),out_folder_explorer])
    return


@app.cell
def _(mo):
    mo.md("""
    ## Click below when you're done editing and ready to go
    """)
    return


@app.cell
def _(mo):
    run_button = mo.ui.run_button()
    run_button
    return (run_button,)


@app.cell
def _(
    bc_channel_map_df,
    bc_pre_prefix,
    out_folder_explorer,
    pheno_channel_map1_df,
    pheno_channel_map2_df,
    plate,
):
    ## Turn anything that needs to be reformatted to match original syntax into the right syntax
    out_folder = out_folder_explorer.value[0].path
    bc_prefix = f'{bc_pre_prefix.value}{plate.value}/'
    pheno_channel_map1 = {x[0]:x[1] for x in pheno_channel_map1_df.data.to_dict("split")['data']}
    pheno_channel_map2 = {x[0]:x[1] for x in pheno_channel_map2_df.data.to_dict("split")['data']}
    bc_channel_map = {x[0]:x[1] for x in bc_channel_map_df.data.to_dict("split")['data']}
    return (
        bc_channel_map,
        bc_prefix,
        out_folder,
        pheno_channel_map1,
        pheno_channel_map2,
    )


@app.cell
def _(boto3, mo, run_button):
    mo.stop(not run_button.value)
    # Initialize the S3 client
    s3_client = boto3.client('s3')
    paginator = s3_client.get_paginator('list_objects_v2')
    # Create a paginator to handle folders with >1000 objects

    def paginate_a_folder(bucket_name, folder, delimiter=None):
        if delimiter:
            pages = paginator.paginate(Bucket=bucket_name, Prefix=folder, Delimiter=delimiter)
            prefix_list = []
            for page in pages:
                prefix_list = prefix_list + [x['Prefix'] for x in page['CommonPrefixes']]
            return prefix_list
        else:
            pages = paginator.paginate(Bucket=bucket_name, Prefix=folder)
            file_list = []
            for page in pages:
                file_list = file_list + [x['Key'] for x in page['Contents']]
            return file_list

    return paginate_a_folder, s3_client


@app.cell
def _():
    # Map to common well format (e.g. A01 instead of r01c01)
    well_mapping = {}
    row_letters = "ABCDEFGH" # A 96-well plate has 8 rows
    for r in range(1, 9):
        for c in range(1, 13):
            old_format = f"r{r:02d}c{c:02d}"          # Generates 'r01c01'
            new_format = f"{row_letters[r-1]}{c:02d}" # Generates 'A01'
            well_mapping[old_format] = new_format
    return (well_mapping,)


@app.cell
def _(bucket, re, s3_client):
    def return_chans(key):
        current_output = set()
        try:
            response = s3_client.get_object(Bucket=bucket.value, Key=key)
        except:
            print(f"Error occurred while fetching {key}")
            return
        # Stream the file line-by-line
        for line in response['Body'].iter_lines():
            decoded_line = line.decode('utf-8')
            if "Channel:" in decoded_line and "ChannelName" in decoded_line:
                current_output.add(decoded_line.strip())

        results = []

        for entry in current_output:
            # Regex searches for "Channel: [digits]" and "ChannelName: [everything up to the comma]"
            match = re.search(r'Channel:\s*(\d+),\s*ChannelName:\s*([^,}]+)', entry)
            channel_num = int(match.group(1))
            channel_name = match.group(2).strip()
            results.append((channel_num, channel_name))

        # Sort the results by Channel number to make it readable
        results.sort(key=lambda x: x[0])
        return results

    return (return_chans,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Confirm Phenotyping Settings
    """)
    return


@app.cell
def _(mo, pheno_prefix1, return_chans):
    # confirm channel mapping as defined above

    _key1 = f'{pheno_prefix1.value}/Index.xml'
    mo.vstack([mo.md("This is what we found for the channel mapping for phenotyping Cycle 1 on the bucket. Does this seem sensible with what you entered above? If so, continue, if not, go back up and edit the form"),return_chans(_key1)])
    return


@app.cell
def _(mo, pheno_prefix2, phenotyping_rounds, return_chans):
    # confirm channel mapping as defined above
    if phenotyping_rounds == 2:
        _key2 = f'{pheno_prefix2.value}/Index.xml'
        mo.vstack([mo.md("This is what we found for the channel mapping for phenotyping Cycle 1 on the bucket. Does this seem sensible with what you entered above? If so, continue, if not, go back up and edit the form"),return_chans(_key2)])
    return


@app.cell
def _(mo):
    mo.md("""
    ## Click below when you're ready to start reading the bucket; note it may take a few minutes
    """)
    return


@app.cell
def _(mo):
    run_button_2 = mo.ui.run_button()
    run_button_2
    return (run_button_2,)


@app.cell
def _(
    bucket,
    mo,
    paginate_a_folder,
    pheno_prefix1,
    pheno_prefix2,
    phenotyping_rounds,
    run_button_2,
):
    mo.stop(not run_button_2.value)
    file_paths1 = paginate_a_folder(bucket.value, pheno_prefix1.value)
    file_paths1 = [f's3://{bucket.value}/{x}' for x in file_paths1 if '.tif' in x]
    if phenotyping_rounds == 2:
        file_paths2 = paginate_a_folder(bucket.value, pheno_prefix2.value)
        file_paths2 = [f's3://{bucket.value}/{x}' for x in file_paths2 if '.tif' in x]
    return file_paths1, file_paths2


@app.cell
def _(
    file_paths1,
    file_paths2,
    pd,
    pheno_channel_map1,
    pheno_channel_map2,
    phenotyping_rounds,
):
    df1 = pd.DataFrame(file_paths1, columns=['path'])
    df1['cycle'] = 1
    df1['channels'] = df1['path'].str.rsplit('/', n=1, expand=True)[1].str[13:16].map(pheno_channel_map1)

    if phenotyping_rounds.value == 2:
        df2 = pd.DataFrame(file_paths2, columns=['path'])
        df2['cycle'] = 2
        df2['channels'] = df2['path'].str.rsplit('/', n=1, expand=True)[1].str[13:16].map(pheno_channel_map2)
        df = pd.concat([df1, df2], ignore_index=True)
    else:
        df = df1.copy()
    # remove channels we don't want
    df = df[~df['channels'].isna()]
    return (df,)


@app.cell
def _(batch, df, plate, suffix, well_mapping):
    df['arm'] = 'painting'
    df['batch'] = batch.value
    if suffix.value=="":
        df['plate'] = plate.value
    else:
        df['plate'] = f"{plate.value}{suffix.value}"
    df['n_frames'] = 1
    df['well'] = df['path'].str.rsplit('/', n=1, expand=True)[1].str[:6]
    df['site'] = df['path'].str.rsplit('/', n=1, expand=True)[1].str[7:9].astype(int)
    df['well'] = df['well'].map(well_mapping)
    return


@app.cell
def _(
    df,
    phenotyping_rounds,
    plate_type,
    use_wells,
    well_values,
    wells_option,
):
    # Filter to just the wells we want to use, do quality checks

    if "Custom" not in wells_option.value:
        wells_we_want = well_values[plate_type.value][wells_option.value]
    else:
        wells_we_want = use_wells.value

    df_1 = df.loc[df['well'].isin(wells_we_want), :]

    phen_error_message = ""

    if df_1.groupby('well').count().iloc[:, 0].nunique() != 1:
        phen_error_message+='Not all wells have the same image count!\n'

    if phenotyping_rounds.value == 2:
        if df_1.loc[df_1['cycle'] == 1, 'site'].max() != df_1.loc[df_1['cycle'] == 2, 'site'].max():
            phen_error_message+='Max site values differ between cycles!\n'


    return df_1, phen_error_message, wells_we_want


@app.cell
def _(df, df_1, mo, phen_error_message):
    phen_message = f"{len(df)} images were found in the phenotyping folder(s) you asked for; aftering filtering to just wells you said you want, it's {len(df_1)} images\n." 
    if phen_error_message != "":
        phen_message += "The following errors were found; check your bucket for incomplete syncs or check your metadata:\n"
    else:
        phen_message += "No obvious errors were detected.\n"
    phen_message += "The images found are shown below; click the button below the data explorer when you're ready to continue."
    mo.md(phen_message)
    return


@app.cell
def _(df_1):
    df_1
    return


@app.cell
def _(mo):
    mo.md("""
    ## Click below when you've confirmed this looks good; if you're doing phenotyping only, we'll save the sample sheet to your requested location, otherwise we'll move onto barcoding checks
    """)
    return


@app.cell
def _(mo):
    run_button_3 = mo.ui.run_button()
    run_button_3
    return (run_button_3,)


@app.cell
def _(mo, os, out_folder, run_button_3):
    mo.stop(not run_button_3.value)
    if not os.path.exists(out_folder):
        os.makedirs(out_folder, exist_ok=True)
    return


@app.cell
def _(df_1, os, out_folder, plate, save_bc, save_cp, suffix):
    if save_cp.value and not save_bc.value:
        if not suffix.value:
            df_1.to_csv(os.path.join(out_folder, f'{plate.value}_pheno_samplesheet.csv'), index=False)
        else:
            df_1.to_csv(os.path.join(out_folder, f'{plate.value}{suffix.value}_pheno_samplesheet.csv'), index=False)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Barcoding
    """)
    return


@app.cell
def _(bc_prefix, bucket, paginate_a_folder, return_chans):
    # confirm channel mapping the same for all cycles
    non_matching_keys = []
    reference_output = None
    all_match = True
    prefix_list = paginate_a_folder(bucket.value, bc_prefix, delimiter='/')
    prefix_list = [x for x in prefix_list if '20X' not in x]
    for _prefix in prefix_list:
        _key = f'{_prefix}Images/Index.xml'
        current_output = return_chans(_key)
        if reference_output is None:
            reference_output = current_output
        elif current_output != reference_output:
            all_match = False  # Set the first file's output as the baseline
            non_matching_keys.append(_key)
    return all_match, non_matching_keys, prefix_list


@app.cell
def _(batch, bucket, paginate_a_folder, pd, plate, prefix_list, re, suffix):
    df_bc = pd.DataFrame()
    for n, _prefix in enumerate(sorted(prefix_list, key=lambda x: int(re.findall('\\d+', x)[-1]))):  #sort prefixes by Measurement number
        file_paths = paginate_a_folder(bucket.value, _prefix)
        file_paths = [f's3://{bucket.value}/{x}' for x in file_paths if '.tif' in x]
        dftemp = pd.DataFrame(file_paths, columns=['path'])
        dftemp['cycle'] = n + 1  # Start cycle count from 1
        df_bc = pd.concat([df_bc, dftemp], ignore_index=True)
    df_bc['arm'] = 'barcoding'
    df_bc['batch'] = batch.value
    if not suffix.value:
        df_bc['plate'] = plate.value
    else:
        df_bc['plate'] = f'{plate.value}{suffix.value}'
    return (df_bc,)


@app.cell
def _(bc_channel_map, df_bc, well_mapping):
    df_bc['n_frames'] = 1
    df_bc['well'] = df_bc['path'].str.rsplit('/', n=1, expand=True)[1].str[:6]
    df_bc['site'] = df_bc['path'].str.rsplit('/', n=1, expand=True)[1].str[7:9].astype(int)
    df_bc['channels'] = df_bc['path'].str.rsplit('/', n=1, expand=True)[1].str[13:16].map(bc_channel_map)
    df_bc['well'] = df_bc['well'].map(well_mapping)
    return


@app.cell
def _(
    all_match,
    bc_cycles,
    df_bc,
    non_matching_keys,
    prefix_list,
    wells_we_want,
):
    df_bc_1 = df_bc.loc[df_bc['well'].isin(wells_we_want), :]

    bc_error_message = ""

    if len(prefix_list) != bc_cycles.value:
        bc_error_message += f'Expected {bc_cycles.value} cycles, but found {len(prefix_list)} cycles in S3.\n'

    if not all_match:
        bc_error_message += f"Not all cycles have matching channel name outputs; check {non_matching_keys} for issues compared to the reference.\n"

    if df_bc_1.groupby(['well', 'cycle']).count().iloc[:, 0].nunique() != 1:
        bc_error_message+='Not all wells have the same image count!\n'
    return bc_error_message, df_bc_1


@app.cell
def _(bc_error_message, df_bc, df_bc_1, mo):
    bc_message = f"{len(df_bc)} images were found in the barcoding folder(s) you asked for; aftering filtering to just wells you said you want, it's {len(df_bc_1)} images\n." 
    if bc_error_message != "":
        bc_message += "The following errors were found; check your bucket for incomplete syncs or check your metadata entered above:\n"
    else:
        bc_message += "No obvious errors were detected.\n"
    bc_message += "The images found are shown below; click the button below the data explorer when you're ready to continue. We're just about done!"
    mo.md(bc_message)
    return


@app.cell
def _(df_bc_1):
    df_bc_1
    return


@app.cell
def _(mo):
    mo.md("""
    ## Click below when you've confirmed this looks good; if you're doing barcoding only, we'll save the sample sheet to your requested location, otherwise we'll merge it with the phenotyping data and then save the merged file
    """)
    return


@app.cell
def _(mo):
    run_button_4 = mo.ui.run_button()
    run_button_4
    return (run_button_4,)


@app.cell
def _(
    df_bc_1,
    mo,
    os,
    out_folder,
    plate,
    run_button_4,
    save_bc,
    save_cp,
    suffix,
):
    mo.stop(not run_button_4.value)
    if save_bc.value and not save_cp.value:
        if not suffix.value:
            df_bc_1.to_csv(os.path.join(out_folder, f'{plate.value}_bc_samplesheet.csv'), index=False)
        else:
            df_bc_1.to_csv(os.path.join(out_folder, f'{plate.value}{suffix.value}_bc_samplesheet.csv'), index=False)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Join
    """)
    return


@app.cell
def _(
    df_1,
    df_bc_1,
    mo,
    os,
    out_folder,
    pd,
    plate,
    run_button_4,
    save_bc,
    save_cp,
    suffix,
):
    mo.stop(not run_button_4.value)
    if save_bc.value and save_cp.value:
        df_2 = pd.concat([df_1, df_bc_1], ignore_index=True)
        if not suffix.value:
            df_2.to_csv(os.path.join(out_folder, f'{plate.value}_samplesheet.csv'), index=False)
        else:
            df_2.to_csv(os.path.join(out_folder, f'{plate.value}{suffix.value}_samplesheet.csv'), index=False)
    return (df_2,)


@app.cell
def _(df_2, mo, plate):
    mo.md(f"""
    Done with plate {plate.value}.\n Maximum sites found per arm: {df_2[df_2['arm'] == 'barcoding']['site'].max()} for barcoding, and {df_2[df_2['arm'] == 'painting']['site'].max()} for painting"
    """)
    return


if __name__ == "__main__":
    app.run()
