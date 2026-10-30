#!/usr/bin/env nextflow
/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    broadinstitute/nf-pooled-cellpainting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Github : https://github.com/broadinstitute/nf-pooled-cellpainting
----------------------------------------------------------------------------------------
*/

/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT FUNCTIONS / MODULES / SUBWORKFLOWS / WORKFLOWS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

include { POOLED_CELLPAINTING } from './workflows/nf-pooled-cellpainting'
include { NO_STITCH_POOLED_CELLPAINTING } from './workflows/no-stitch'
include { STITCH_ALIGN_CROP_POOLED_CELLPAINTING } from './workflows/stitch-align-crop'
include { PIPELINE_INITIALISATION } from './subworkflows/local/utils_nfcore_nf-pooled-cellpainting_pipeline'
include { PIPELINE_COMPLETION } from './subworkflows/local/utils_nfcore_nf-pooled-cellpainting_pipeline'
/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    RUN MAIN WORKFLOW (select variant with --entrypoint)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

workflow {
    //
    // SUBWORKFLOW: Run initialisation tasks
    //
    PIPELINE_INITIALISATION(
        params.version,
        params.validate_params,
        params.monochrome_logs,
        args,
        params.outdir,
        params.input,
    )

    //
    // WORKFLOW: Run the pipeline variant selected with --entrypoint
    // (default POOLED_CELLPAINTING, NO_STITCH or STITCH_ALIGN_CROP)
    //
    if (params.entrypoint == 'NO_STITCH') {
        NO_STITCH_POOLED_CELLPAINTING(
            PIPELINE_INITIALISATION.out.samplesheet,
            params.barcodes,
        )
        ch_multiqc_report = NO_STITCH_POOLED_CELLPAINTING.out.multiqc_report
    }
    else if (params.entrypoint == 'STITCH_ALIGN_CROP') {
        STITCH_ALIGN_CROP_POOLED_CELLPAINTING(
            PIPELINE_INITIALISATION.out.samplesheet,
            params.barcodes,
        )
        ch_multiqc_report = STITCH_ALIGN_CROP_POOLED_CELLPAINTING.out.multiqc_report
    }
    else if (params.entrypoint == 'POOLED_CELLPAINTING') {
        POOLED_CELLPAINTING(
            PIPELINE_INITIALISATION.out.samplesheet,
            params.barcodes,
        )
        ch_multiqc_report = POOLED_CELLPAINTING.out.multiqc_report
    }
    else {
        error("Unknown --entrypoint '${params.entrypoint}'. Choose one of: POOLED_CELLPAINTING, NO_STITCH, STITCH_ALIGN_CROP")
    }

    //
    // SUBWORKFLOW: Run completion tasks
    //
    PIPELINE_COMPLETION(
        params.outdir,
        params.monochrome_logs,
        ch_multiqc_report,
    )
}
