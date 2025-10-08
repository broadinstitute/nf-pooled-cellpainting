---
description: Fill out meta.yml for Nextflow module/subworkflow
---

You are tasked with filling out a `meta.yml` file for a Nextflow component (module or subworkflow) based on nf-core specifications.

## Instructions

1. **Identify the component type and location:**
   - Check if the user has a meta.yml file open in their IDE
   - If not, ask which module or subworkflow they want to document
   - Determine if it's a module (in `modules/` directory) or subworkflow (in `subworkflows/` directory)

2. **Read the main.nf file:**
   - Read the corresponding `main.nf` file in the same directory as the `meta.yml`
   - Analyze the process/workflow definition to extract:
     - Input channels and their structure
     - Output channels and their structure
     - Tool/software being used
     - Process labels and directives

3. **Generate complete meta.yml following nf-core schema:**

   The meta.yml should include:

   ```yaml
   # yaml-language-server: $schema=https://raw.githubusercontent.com/nf-core/modules/master/modules/meta-schema.json
   name: "module_name"
   description: Clear description of what the module does
   keywords:
     - relevant
     - keywords
     - here
   tools:
     - "tool_name":
         description: "Tool description"
         homepage: "https://tool.homepage"
         documentation: "https://tool.docs"
         tool_dev_url: "https://github.com/tool/repo"
         doi: "10.xxxx/xxxxx"
         licence: ["MIT", "BSD-3-clause", etc.]
         identifier: biotools:ToolName

   input:
     - meta:
         type: map
         description: |
           Groovy Map containing sample information
           e.g. `[ id:'sample1', single_end:false ]`
     - input_file:
         type: file
         description: Description of input file
         pattern: "*.{ext}"
         ontologies:
           - edam: http://edamontology.org/format_XXXX

   output:
     - meta:
         type: map
         description: |
           Groovy Map containing sample information
           e.g. `[ id:'sample1', single_end:false ]`
     - output_name:
         type: file
         description: Description of output file
         pattern: "*.{ext}"
         ontologies:
           - edam: http://edamontology.org/format_XXXX
     - versions:
         type: file
         description: File containing software versions
         pattern: "versions.yml"
         ontologies:
           - edam: http://edamontology.org/format_3750

   authors:
     - "@github_username"
   maintainers:
     - "@github_username"
   ```

4. **Parse inputs from main.nf:**
   - Extract each input channel
   - For `tuple val(meta), path(file)` → document both meta and file separately
   - For `path(file)` → document the file with appropriate pattern
   - For `val(param)` → document as a value input
   - Add appropriate EDAM ontology terms for file types

5. **Parse outputs from main.nf:**
   - Extract each output channel with its emit name
   - Document pattern matching (e.g., "*.bam", "*.csv")
   - Add EDAM ontology terms
   - Always include versions.yml in outputs

6. **Fill in tool information:**
   - Use the container/conda information to identify the tool and version
   - Search online if needed for homepage, documentation, DOI, and licence
   - Add biotools identifier if available

7. **Write clear descriptions:**
   - Module description: What biological/computational task does it perform?
   - Input descriptions: What is each input used for?
   - Output descriptions: What does each output contain?
   - Use relevant keywords related to the biological/computational domain

8. **Update the meta.yml file:**
   - Use the Edit tool to update the existing meta.yml
   - Ensure proper YAML formatting
   - Validate against nf-core schema standards

## Important Notes

- Follow nf-core naming conventions (lowercase with underscores)
- Include EDAM ontology terms where applicable (http://edamontology.org)
- Ensure all inputs and outputs from main.nf are documented
- Keep descriptions clear and concise
- Use appropriate file patterns (*.bam, *.csv, etc.)
- Always include the yaml-language-server schema comment at the top

## If user provides arguments:

If the user provides a path as an argument (e.g., `/fill-meta modules/local/mymodule`), use that path to locate the main.nf and meta.yml files.
