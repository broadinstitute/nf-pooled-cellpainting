You are tasked with filling out an nf-test file for a Nextflow component (module or subworkflow) based on nf-core specifications.

## Instructions

1. **Identify the component type and location:**
   - Check if the user has a main.nf.test file open in their IDE
   - If not, ask which module or subworkflow they want to create tests for
   - Determine if it's a module (in `modules/` directory) or subworkflow (in `subworkflows/` directory)

2. **Read the main.nf and meta.yml files:**
   - Read the corresponding `main.nf` file to understand:
     - Process/workflow name
     - Input channels and their structure
     - Output channels and their structure
     - Tool/software being used
     - Command being executed
   - Read the `meta.yml` to understand input/output specifications

3. **Search for existing test data:**
   - Look through the pipeline samplesheet at `assets/samplesheet.csv`
   - Check other nf-test files in the project to find similar test patterns
   - Look for test data in other module test directories (e.g., `modules/*/tests/`)
   - Identify S3 paths or local test files that match the input requirements

4. **Generate complete nf-test following nf-core patterns:**

   The nf-test should include:

   ```groovy
   nextflow_process {

       name "Test Process PROCESS_NAME"
       script "../main.nf"
       process "PROCESS_NAME"

       tag "module_category"
       tag "module_name"

       test("descriptive_test_name - input_format") {

           when {
               // Add params block if needed
               params {
                   param_name = value
               }
               process {
                   """
                   input[0] = [
                       [ id:'test_id', ...meta... ], // meta map
                       file("path/to/test/file.ext", checkIfExists: true)
                   ]
                   input[1] = file("path/to/config.ext", checkIfExists: true)
                   """
               }
           }

           then {
               assertAll(
                   { assert process.success },
                   { assert snapshot(process.out.output_channel).match() }
               )
           }
       }

       test("descriptive_test_name - stub") {

           options "-stub"

           when {
               process {
                   """
                   // Same inputs as above
                   """
               }
           }

           then {
               assertAll(
                   { assert process.success },
                   { assert snapshot(process.out).match() }
               )
           }
       }
   }
   ```

5. **Map inputs from main.nf to test inputs:**
   - For `tuple val(meta), path(file)` inputs:
     - Create appropriate meta map with relevant keys (id, batch, plate, etc.)
     - Reference real test files from samplesheet or existing test data
   - For `path(file)` inputs:
     - Use `file()` function with paths from project directories
     - Use `checkIfExists: true` for validation
   - For `val(param)` inputs:
     - Provide appropriate test values
   - Ensure all required inputs are provided in correct order

6. **Create multiple test cases when appropriate:**
   - Create test for different parameter combinations if the module uses params
   - Create test for different input types/formats
   - Always include a stub test with `options "-stub"`
   - Use descriptive test names that indicate data type and scenario

7. **Use appropriate assertions:**
   - Always assert `process.success`
   - Use `snapshot(process.out.channel_name).match()` for specific output channels
   - Use `snapshot(process.out).match()` for all outputs (typically in stub tests)

8. **Handle test data appropriately:**
   - **If suitable test data exists:** Reference it directly using:
     - S3 paths from samplesheet: `file("s3://bucket/path/to/file.tiff")`
     - Local test files: `file("${projectDir}/path/to/test/file.ext", checkIfExists: true)`
     - CellProfiler pipelines: `file("${projectDir}/assets/cellprofiler/pipeline.cppipe.template")`

   - **If no suitable test data exists:**
     - Add a comment block at the top explaining what test data is needed
     - Use placeholder paths with TODO comments
     - Provide guidance on what file types/structure are required
     - Still generate complete test structure so user can fill in paths

9. **Update the test file:**
   - Use the Edit tool to update the existing main.nf.test
   - Ensure proper Groovy syntax
   - Include all necessary imports if any
   - Add helpful comments

## Important Notes

- Test names should be descriptive: `"cellprofiler - segcheck - microscopy_images"`
- Use tags matching the module hierarchy: `tag "cellprofiler"`, `tag "cellprofiler/segcheck"`
- Meta maps should include realistic keys based on the pipeline's data structure
- For CellProfiler modules, check `assets/cellprofiler/` for pipeline templates
- Include both regular and stub tests for completeness
- Use `checkIfExists: true` to validate file paths exist
- Look at similar modules' tests for patterns (e.g., other cellprofiler tests)

## Test Data Search Strategy

1. First check assets/samplesheet.csv for appropriate input files
2. Look at other module tests in the same category (e.g., modules/local/cellprofiler/\*/tests/)
3. Check for test-specific files in the module's test directory
4. Search for CellProfiler pipeline files in assets/cellprofiler/
5. If module needs generated data from other processes, document this in comments

## If user provides arguments:

If the user provides a path as an argument (e.g., `/create-nftest modules/local/mymodule`), use that path to locate the main.nf, meta.yml, and tests/main.nf.test files.

## Example Test Data References:

```groovy
// From samplesheet
file("s3://nf-pooled-cellpainting-sandbox/data/test-data/fix-s1_sub25/Source1/images/Batch1/images/Plate1/20X_CP_Plate1_20240319_122800_179/WellA1_PointA1_0000_ChannelPhalloAF750,CHN2-AF488,DAPI_Seq0000.ome.tiff")

// From project assets
file("${projectDir}/assets/cellprofiler/cp_illumination_calc.cppipe.template")

// From module test directory
file("${projectDir}/modules/local/cellprofiler/illumcalc/tests/load_data.csv", checkIfExists: true)
```
