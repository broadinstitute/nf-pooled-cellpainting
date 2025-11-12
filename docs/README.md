# Documentation

This directory contains the MkDocs Material documentation for the nf-pooled-cellpainting pipeline.

## Building Locally

### Install Dependencies

```bash
pip install -r docs-requirements.txt
```

### Serve Documentation

```bash
mkdocs serve
```

Then open http://127.0.0.1:8000 in your browser.

### Build Documentation

```bash
mkdocs build
```

Output will be in `site/` directory.

## Deploying to GitHub Pages

### Manual Deployment

```bash
mkdocs gh-deploy
```

This will:

1. Build the documentation
2. Push to `gh-pages` branch
3. Documentation will be available at `https://<username>.github.io/<repo>/`

### Automated Deployment

Add GitHub Actions workflow (`.github/workflows/docs.yml`):

```yaml
name: Deploy Documentation

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: 3.x
      - run: pip install -r docs-requirements.txt
      - run: mkdocs gh-deploy --force
```

## Structure

```
docs/
├── index.md                    # Homepage
├── getting-started/
│   ├── overview.md
│   ├── installation.md
│   └── quickstart.md
├── usage/
│   ├── parameters.md
│   ├── running-locally.md
│   └── seqera-platform.md
├── developer/
│   ├── architecture.md
│   ├── cellprofiler.md
│   ├── python-scripts.md
│   └── testing.md
└── reference/
    ├── outputs.md
    └── troubleshooting.md
```

## Contributing

To add or modify documentation:

1. Edit markdown files in `docs/`
2. Test locally with `mkdocs serve`
3. Commit changes
4. Documentation will auto-deploy (if GitHub Actions configured)

## Configuration

Documentation is configured in `mkdocs.yml` at the repository root.

Key features:

- Material theme with dark/light mode toggle
- Code syntax highlighting
- Search functionality
- Navigation tabs
- Mobile responsive design
