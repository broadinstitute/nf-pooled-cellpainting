# Developer introduction

Hi there fellow developer! You are here because you want to contribute to the nf-pooled-cellpainting pipeline. Welcome!

## Repository structure

nf-pooled cellpainting is a Nextflow pipeline for optical pooled screening processing and analysis. The repository structure is based on a reduced [nf-core](https://nf-co.re/) template that was generated using [nf-core tools](https://nf-co.re/docs/nf-core-tools):
`nf-core pipelines create`, generating the following pipeline folder structure:

```
nf-pooled-cellpainting/
├── assets/                 # CellProfiler pipelines & resources
├── bin/                    # Python scripts & tools
├── CHANGELOG.md            # Changelog
├── CITATIONS.md            # Citations
├── CLAUDE.md               # Claude
├── conf/                   # Configuration files
├── docs/                   # Documentation source
├── LICENSE                 # License
├── main.nf                 # Main pipeline
├── mkdocs.yml              # MkDocs configuration
├── modules/                # nf-core modules
├── modules.json            # nf-core modules
├── nextflow_schema.json    # Nextflow schema
├── nextflow.config         # Nextflow configuration
├── nf-test.config          # nf-test configuration
├── README.md               # README
├── subworkflows/           # Subworkflows
├── tests/                  # Tests
├── tower.yml               # Seqera Platform configuration
└── workflows/              # Workflows
```

The specific template version and features enabled and disabled can be found in the `.nf-core.yml` file in the root directory of the repository. While this pipeline is based on nf-core, it is not a nf-core pipeline and does not strictly follow the nf-core guidelines.

## Nextflow processes and subworkflows

### Subworkflows

The pipeline is split into two subworkflows, one for cell painting and one for barcoding. These subworkflows are located in the `subworkflows` directory. Each subworkflow is a Nextflow workflow file that is run independently by the main workflow. The main workflow orchestrates the two subworkflows and their inputs and outputs. Importantly, both subworkflows have quality control parameters (`qc_painting_passed` and `qc_barcoding_passed`) that will stop execution before FIJI_STITCHCROP if the parameters are set to false (default). This is a safety feature to prevent downstream analysis from running if the image quality is not sufficient after manual inspection.

### Processes / modules

The Nextflow processes in this pipeline were all instantiated using nf-core tooling via `nf-core modules create` and therefore have the standard nf-core structure:

```
modules/
    └── local/
        └── illumcalc/
            ├── main.nf
            ├── meta.yml
            └── tests/
```

!!! warning "Docker support only"
    The nf-pooled-cellpainting pipeline was developed to work with the Docker container engine and does not currently support conda, singularity or any other container engine!

## Getting Started with Development

### Prerequisites

Before contributing, make sure you have:

1. **Nextflow** (version 23.04.0 or later)
2. **Docker** (for running the pipeline)
3. **nf-test** (for running tests) - install via: `curl -fsSL https://code.askimed.com/install/nf-test | bash`
4. **Git** (for version control)

### Clone and Test

```bash
# Clone the repository
git clone https://github.com/seqera-services/nf-pooled-cellpainting.git
cd nf-pooled-cellpainting

# Run the test suite to verify your setup
nextflow run . -profile test,docker --outdir test_results

# Run nf-test for module tests
nf-test test
```

### Development Workflow

1. Create a feature branch from `dev`
2. Make your changes
3. Run tests locally
4. Submit a pull request

## Next Steps

- [Architecture](architecture.md) - Understand the pipeline structure and data flow
- [CellProfiler Integration](cellprofiler.md) - Learn how CellProfiler processes are implemented
- [Testing](testing.md) - Write and run tests for your changes
- [Python Scripts](python-scripts.md) - Understand the helper scripts
