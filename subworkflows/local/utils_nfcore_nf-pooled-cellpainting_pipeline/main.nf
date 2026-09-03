//
// Subworkflow with functionality specific to the broadinstitute/nf-pooled-cellpainting pipeline
//

/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    IMPORT FUNCTIONS / MODULES / SUBWORKFLOWS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

include { UTILS_NFSCHEMA_PLUGIN } from '../../nf-core/utils_nfschema_plugin'
include { paramsSummaryMap } from 'plugin/nf-schema'
include { samplesheetToList } from 'plugin/nf-schema'
include { completionSummary } from '../../nf-core/utils_nfcore_pipeline'
include { UTILS_NFCORE_PIPELINE } from '../../nf-core/utils_nfcore_pipeline'
include { UTILS_NEXTFLOW_PIPELINE } from '../../nf-core/utils_nextflow_pipeline'

/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    SUBWORKFLOW TO INITIALISE PIPELINE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

workflow PIPELINE_INITIALISATION {
    take:
    version // boolean: Display version and exit
    validate_params // boolean: Boolean whether to validate parameters against the schema at runtime
    monochrome_logs // boolean: Do not use coloured log outputs
    nextflow_cli_args //   array: List of positional nextflow CLI args
    outdir //  string: The output directory where the results will be saved
    input //  string: Path to input samplesheet

    main:

    ch_versions = Channel.empty()

    //
    // Print version and exit if required and dump pipeline parameters to JSON file
    //
    UTILS_NEXTFLOW_PIPELINE(
        version,
        true,
        outdir,
        false,
    )

    //
    // Validate parameters and generate parameter summary to stdout
    //
    UTILS_NFSCHEMA_PLUGIN(
        workflow,
        validate_params,
        null,
        params.help ?: false,
        false,
        params.show_hidden ?: false,
        '',
        '',
        "nextflow run broadinstitute/nf-pooled-cellpainting --input samplesheet.csv --outdir results -profile docker",
        null,
    )

    //
    // Check config provided to the pipeline
    //
    UTILS_NFCORE_PIPELINE(
        nextflow_cli_args
    )

    //
    // Create channel from input file provided through params.input
    //

    Channel
        .fromList(samplesheetToList(params.input, "${projectDir}/assets/schema_input.json"))
        .set { ch_samplesheet }

    emit:
    samplesheet = ch_samplesheet
    versions = ch_versions
}

/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    SUBWORKFLOW FOR PIPELINE COMPLETION
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

workflow PIPELINE_COMPLETION {
    take:
    outdir //    path: Path to output directory where results will be published
    monochrome_logs // boolean: Disable ANSI colour codes in log output
    multiqc_report //  string: Path to MultiQC report

    main:
    summary_params = paramsSummaryMap(workflow, parameters_schema: "nextflow_schema.json")
    def multiqc_reports = multiqc_report.toList()

    //
    // Completion email and summary
    //
    workflow.onComplete {

        completionSummary(monochrome_logs)
    }

    workflow.onError {
        log.error("Pipeline failed. Please refer to troubleshooting docs: https://nf-co.re/docs/usage/troubleshooting")
    }
}

/*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    FUNCTIONS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*/

//
// Validate channels from input samplesheet
//
def validateInputSamplesheet(input) {
    def (metas, fastqs) = input[1..2]

    // Check that multiple runs of the same sample are of the same datatype i.e. single-end / paired-end
    def endedness_ok = metas.collect { meta -> meta.single_end }.unique().size == 1
    if (!endedness_ok) {
        error("Please check input samplesheet -> Multiple runs of a sample must be of the same datatype i.e. single-end or paired-end: ${metas[0].id}")
    }

    return [metas[0], fastqs]
}
//
// Generate methods description for MultiQC
//
def toolCitationText() {
    // Can use ternary operators to dynamically construct based conditions, e.g. params["run_xyz"] ? "Tool (Foo et al. 2023)" : "",
    // Uncomment function in methodsDescriptionText to render in MultiQC report
    def citation_text = [
        "Tools used in the workflow included:",
        "MultiQC (Ewels et al. 2016)",
        "CellProfiler 1.0 (Carpenter AE et al 2006)",
        "CellProfiler 2.0 (Kamentsky et al. 2011)",
        "CellProfiler 3.0 (McQuin et al. 2018)",
        "CellProfiler 4.0 (Stirling et al. 2021)",
        ".",
    ].join(' ').trim()

    return citation_text
}

def toolBibliographyText() {
    // Can use ternary operators to dynamically construct based conditions, e.g. params["run_xyz"] ? "<li>Author (2023) Pub name, Journal, DOI</li>" : "",
    // Uncomment function in methodsDescriptionText to render in MultiQC report
    def reference_text = [
        "<li>Ewels, P., Magnusson, M., Lundin, S., & Käller, M. (2016). MultiQC: summarize analysis results for multiple tools and samples in a single report. Bioinformatics , 32(19), 3047–3048. doi: /10.1093/bioinformatics/btw354</li>",
        "<li>Carpenter AE, Jones TR, Lamprecht MR, Clarke C, Kang IH, Friman O, Guertin DA, Chang JH, Lindquist RA, Moffat J, Golland P, Sabatini DM (2006) CellProfiler: image analysis software for identifying and quantifying cell phenotypes. Genome Biology 7:R100. PMID: 17076895</li>",
        "<li>Kamentsky L, Jones TR, Fraser A, Bray M, Logan D, Madden K, Ljosa V, Rueden C, Harris GB, Eliceiri K, Carpenter AE (2011). Improved structure, function, and compatibility for CellProfiler: modular high-throughput image analysis software. Bioinformatics 2011. PMID: 21349861 PMCID: PMC3072555</li>",
        "<li>McQuin C, Goodman A, Chernyshev V, Kamentsky L, Cimini BA, Karhohs KW, Doan M, Ding L, Rafelski SM, Thirstrup D, Wiegraebe W, Singh S, Becker T, Caicedo JC, Carpenter AE (2018). CellProfiler 3.0: Next-generation image processing for biology. PLoS Biol. 16(7):e2005970. PMID: 29969450</li>",
        "<li>Stirling DR, Swain-Bowden MJ, Lucas AM, Carpenter AE, Cimini BA, Goodman A (2021). CellProfiler 4: improvements in speed, utility and usability. BMC Bioinformatics, 22 (1), 433. . PMID: 34507520 PMCID: PMC8431850.</li>",
    ].join(' ').trim()

    return reference_text
}

//
// A disambiguated name to stage a raw image file under - e.g.
// "Cycle01_Plate1_A1_Site0_WellA1_..._Seq0000.ome.tiff". Different physical
// files (different cycles/acquisition rounds) can share the same basename;
// Nextflow's own "images/img?/*" staging keeps them apart on disk, but
// generate_load_data_csv.py needs each entry's `filename` to already be
// unique so it never has to reverse-engineer which staged copy is which.
//
def stagedImageName(Map meta, image) {
    def parts = []
    if (meta.cycle != null) {
        parts << "Cycle${String.format('%02d', meta.cycle as Integer)}"
    }
    parts << meta.plate
    parts << meta.well
    parts << "Site${meta.site}"
    parts << image.name
    return parts.join('_')
}

//
// Expand one samplesheet row (= one physical image file) into one metadata entry
// per (file, channel) pair, matching bin/generate_load_data_csv.py's schema.
//
// meta.channels is a comma-joined string: one row/file may hold multiple channel
// frames (a multichannel OME-TIFF, see assets/samplesheet.csv) or exactly one
// channel (Phenix single-channel, see conf/LOCAL_TEST2.config). frame_index is
// set only for multi-frame files - a single-frame file must not get a Frame_
// column downstream.
//
def expandImageChannels(Map meta, image, String column_prefix) {
    def chans = (meta.channels instanceof List)
        ? meta.channels.collect { it.toString().trim() }
        : meta.channels.toString().split(',').collect { it.trim() }
    def multiframe = chans.size() > 1
    def staged_name = stagedImageName(meta, image)
    return chans.withIndex().collect { ch, idx ->
        [
            well             : meta.well,
            site             : meta.site,
            arm              : meta.arm,
            cycle            : meta.cycle,
            channel          : ch,
            frame_index      : multiframe ? idx : null,
            column_prefix    : column_prefix,
            filename         : staged_name,
            original_path    : image.toString(),
            original_filename: image.name,
        ]
    }
}

//
// Build the top-level wrapper object every generate_load_data_csv.py caller
// serializes as its --metadata-json.
//
def buildLoadDataMetadata(Map group_meta, List image_metas) {
    def cycles = image_metas.collect { it.cycle }.findAll { it != null }.unique().sort()
    def out = [plate: group_meta.plate, image_metadata: image_metas]
    if (group_meta.batch) {
        out.batch = group_meta.batch
    }
    if (cycles) {
        out.cycles = cycles
    }
    return out
}

def methodsDescriptionText(mqc_methods_yaml) {
    // Convert  to a named map so can be used as with familiar NXF ${workflow} variable syntax in the MultiQC YML file
    def meta = [:]
    meta.workflow = workflow.toMap()
    meta["manifest_map"] = workflow.manifest.toMap()

    // Pipeline DOI
    if (meta.manifest_map.doi) {
        // Using a loop to handle multiple DOIs
        // Removing `https://doi.org/` to handle pipelines using DOIs vs DOI resolvers
        // Removing ` ` since the manifest.doi is a string and not a proper list
        def temp_doi_ref = ""
        def manifest_doi = meta.manifest_map.doi.tokenize(",")
        manifest_doi.each { doi_ref ->
            temp_doi_ref += "(doi: <a href=\'https://doi.org/${doi_ref.replace("https://doi.org/", "").replace(" ", "")}\'>${doi_ref.replace("https://doi.org/", "").replace(" ", "")}</a>), "
        }
        meta["doi_text"] = temp_doi_ref.substring(0, temp_doi_ref.length() - 2)
    }
    else {
        meta["doi_text"] = ""
    }
    meta["nodoi_text"] = meta.manifest_map.doi ? "" : "<li>If available, make sure to update the text to include the Zenodo DOI of version of the pipeline used. </li>"

    // Tool references
    meta["tool_citations"] = ""
    meta["tool_bibliography"] = ""

    meta["tool_citations"] = toolCitationText().replaceAll(", \\.", ".").replaceAll("\\. \\.", ".").replaceAll(", \\.", ".")
    meta["tool_bibliography"] = toolBibliographyText()


    def methods_text = mqc_methods_yaml.text

    def engine = new groovy.text.SimpleTemplateEngine()
    def description_html = engine.createTemplate(methods_text).make(meta)

    return description_html.toString()
}
