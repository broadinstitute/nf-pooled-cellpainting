<!--
Remember that PRs should be made against the dev branch, unless you're preparing a pipeline release.

Learn more about contributing: [CONTRIBUTING.md](https://github.com/broadinstitute/nf-pooled-cellpainting/tree/master/.github/CONTRIBUTING.md)
-->

## PR checklist

- [ ] This comment contains a description of changes (with reason).
- [ ] If you've fixed a bug or added code that should be tested, add tests!
- [ ] Make sure your code lints (`pixi run nextflow lint . -format` and `pixi run pre-commit run --all-files`).
- [ ] Ensure the test suite passes (`pixi run nf-test test tests --profile test,docker` (you may need to run with `--update-snapshot` and commit the snapshot updates).
- [ ] Check for unexpected warnings in debug mode (`nextflow run . -profile debug,test,docker --outdir <OUTDIR> --qc_painting_passed --qc_barcoding_passed`).
- [ ] Any relevant docs updated.
