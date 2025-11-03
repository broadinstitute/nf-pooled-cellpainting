#!/usr/bin/env nextflow
/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    seqera-services/nf-pooled-cellpainting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Github : https://github.com/seqera-services/nf-pooled-cellpainting
----------------------------------------------------------------------------------------
*/

/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT FUNCTIONS / MODULES / SUBWORKFLOWS / WORKFLOWS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

include { POOLED_CELLPAINTING  }    from './workflows/nf-pooled-cellpainting'
include { PIPELINE_INITIALISATION } from './subworkflows/local/utils_nfcore_nf-pooled-cellpainting_pipeline'
include { PIPELINE_COMPLETION     } from './subworkflows/local/utils_nfcore_nf-pooled-cellpainting_pipeline'
/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    NAMED WORKFLOWS FOR PIPELINE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

//
// WORKFLOW: Run main analysis pipeline depending on type of input
//
workflow NF_POOLED_CELLPAINTING {

    take:
    samplesheet // channel: samplesheet read in from --input

    main:

    cppipes = [
        'illumination_calc_cp'    : params.cp_illum_calc_pipe       ?: "${projectDir}/assets/cellprofiler/cp_illumination_calc.cppipe.template",
        'illumination_apply_cp'   : params.cp_illum_apply_pipe      ?: "${projectDir}/assets/cellprofiler/cp_illumination_apply.cppipe.template",
        'illumination_calc_sbs'   : params.sbs_illum_calc_pipe      ?: "${projectDir}/assets/cellprofiler/sbs_illumination_calc.cppipe.template",
        'illumination_apply_sbs'  : params.sbs_illum_apply_pipe     ?: "${projectDir}/assets/cellprofiler/sbs_illumination_apply.cppipe.template",
        'segcheck_cp'             : params.cp_segcheck_pipe         ?: "${projectDir}/assets/cellprofiler/cp_segcheck.cppipe",
        'preprocess_sbs'          : params.sbs_preprocess_pipe      ?: "${projectDir}/assets/cellprofiler/sbs_preprocess.cppipe",
        'combinedanalysis_cppipe' : params.combinedanalysis_cppipe  ?: "${projectDir}/assets/cellprofiler/combined_analysis.cppipe"
    ]

    //
    // WORKFLOW: Run pipeline
    //
    POOLED_CELLPAINTING (
        samplesheet,
        params.barcodes,
        cppipes,
        params.multichannel_parallel
    )
    // emit:
    // multiqc_report = POOLED_CELLPAINTING.out.multiqc_report // channel: /path/to/multiqc_report.html
}
/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    RUN MAIN WORKFLOW
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

workflow {

    main:
    //
    // SUBWORKFLOW: Run initialisation tasks
    //
    PIPELINE_INITIALISATION (
        params.version,
        params.validate_params,
        params.monochrome_logs,
        args,
        params.outdir,
        params.input
    )

    //
    // WORKFLOW: Run main workflow
    //
    NF_POOLED_CELLPAINTING (
        PIPELINE_INITIALISATION.out.samplesheet
    )
    //
    // SUBWORKFLOW: Run completion tasks
    //
    // PIPELINE_COMPLETION (
    //     params.outdir
    //     // params.monochrome_logs,
    //     // POOLED_CELLPAINTING.out.multiqc_report
    // )
}

/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    THE END
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/
