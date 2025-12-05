# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with documentation in this repository.

## Documentation Principles

### Structure

- **Consolidate over fragment**: Prefer one long comprehensive document over many small files
- **Progressive disclosure**: Overview → concepts → details within each document
- **Clear entry points**: Each document should have a clear "Start Here" section
- **Shallow hierarchy**: Keep directory structure to 2 levels max

### Content Standards

- Use consistent Markdown formatting with appropriate language tags
- Write concisely with numbered steps for complex procedures
- Include concrete examples with real commands and outputs
- Format code blocks, file paths, and commands appropriately
- Link to existing content rather than duplicating
- Use Mermaid diagrams for workflows and architecture visualization

### Terminology

- **Cell Painting**: Use full term in prose, "CP" only in diagrams if space-constrained
- **SBS**: Define as "Sequencing by Synthesis" on first use, then use abbreviation
- **Barcoding**: Preferred term for "SBS", in the context of this worflow
- **Painting**: Preferred term for "Cell Painting", when referring to terms like "painting arm" in the context of this worflow
- **OPS**: Define as "Optical Pooled Screening" on first use
- **Seqera Platform**: Current name (formerly "Nextflow Tower")
- **CellProfiler pipeline** (.cppipe): Image processing definition
- **Nextflow pipeline**: Workflow orchestration

### Document Organization

The documentation is organized into:

1. **index.md** - Landing page with overview and navigation
2. **guide.md** - Comprehensive user guide (installation → quickstart → custom data → cloud execution → FAQ)
3. **reference.md** - Technical reference (architecture, CellProfiler integration, scripts, outputs)
4. **parameters.md** - Auto-generated parameter reference (from nextflow_schema.json)

### For Maintainers

When updating documentation:

1. **Adding new content**: Add to existing consolidated documents rather than creating new files
2. **Screenshots**: Store in `docs/assets/images/` with descriptive names
3. **Code examples**: Use real commands from the repository, test them before documenting
4. **Version changes**: Update examples when pipeline parameters or behavior changes
5. **Cross-references**: Use relative links between documents

### Common Commands for Docs

```bash
# Serve docs locally
mkdocs serve

# Build docs
mkdocs build

# Deploy to GitHub Pages (usually via CI)
mkdocs gh-deploy
```

### MkDocs Configuration

The `mkdocs.yml` file controls navigation. When restructuring:

- MkDocs supports only 2 levels of nesting
- Use descriptive names that indicate content
- Match nav structure to actual file organization

## Interaction Guidelines

- **Read "For Document Contributors" sections first**: Each major document (guide.md, reference.md) contains a "For Document Contributors" section at the end with editorial guidelines. Read these before making changes to understand the document's purpose, audience, structure principles, and terminology.
- When making large restructuring changes, propose the structure first before implementing
- For moving large chunks of text, it may be easier to ask the human to do it
- Always verify links work after restructuring
