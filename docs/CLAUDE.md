# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with documentation in this repository.

## Documentation Principles

### Structure

- **Consolidate over fragment**: Prefer one long comprehensive document over many small files
- **Progressive disclosure**: Overview → concepts → details within each document
- **Shallow hierarchy**: Keep directory structure to 2 levels max

### Content Standards

- **Parsimony over completeness**: Avoid redundant navigation aids (manual TOCs, "Quick Links" sections, feature lists that duplicate content elsewhere). Let MkDocs handle navigation. Landing pages should be minimal - link to docs, not summarize them.
- **Diagrams where they teach**: Use Mermaid diagrams only in guide.md/reference.md where they explain concepts. Avoid decorative diagrams on landing pages.
- Write concisely with numbered steps for complex procedures
- Include concrete examples with real commands and outputs
- Format code blocks, file paths, and commands appropriately
- Link to existing content rather than duplicating

### Terminology

- **Cell Painting**: Use full term in prose, "CP" only in diagrams if space-constrained
- **SBS**: Define as "Sequencing by Synthesis" on first use, then use abbreviation
- **Barcoding**: Preferred term for "SBS", in the context of this workflow
- **Painting**: Preferred term for "Cell Painting", when referring to terms like "painting arm" in the context of this workflow
- **OPS**: Define as "Optical Pooled Screening" on first use
- **Seqera Platform**: Current name (formerly "Nextflow Tower")
- **CellProfiler pipeline** (.cppipe): Image processing definition
- **Nextflow pipeline**: Workflow orchestration

### Document Organization

The documentation is organized into:

1. **index.md** - Minimal landing page (brief description, doc links, citation)
2. **guide.md** - Comprehensive user guide (installation → quickstart → custom data → cloud execution → FAQ)
3. **reference.md** - Technical reference (architecture, channels, QC gates, testing/CI)
4. **parameters.md** - Auto-generated parameter reference (from nextflow_schema.json)

### For Maintainers

When updating documentation:

1. **Adding new content**: Add to existing consolidated documents rather than creating new files
2. **Screenshots**: Store in `docs/assets/images/` with descriptive names
3. **Code examples**: Use real commands from the repository, test them before documenting
4. **Version changes**: Update examples when pipeline parameters or behavior changes
5. **Cross-references**: Use relative links between documents

### Local Docs Setup

```bash
pixi run serve-docs    # Serve documentation locally
pixi run build-docs    # Build documentation
```

Deploy to GitHub Pages is handled via CI.

### MkDocs Configuration

The `mkdocs.yml` file controls navigation. When restructuring:

- MkDocs supports only 2 levels of nesting
- Use descriptive names that indicate content
- Match nav structure to actual file organization

## Session Transcripts

- **Location**: `resources/` folder (git-ignored) stores meeting transcripts and screenshots
- **Naming**: `YYYY-MM-DD-transcript.txt` for transcripts, `YYYY-MM-DD-screenshots/` for images
- **Usage**: Reference transcripts to identify documentation gaps and cross-check with guide.md/reference.md

## Interaction Guidelines

- **Read "For Document Contributors" sections first**: Each major document (guide.md, reference.md) contains a "For Document Contributors" section at the end with editorial guidelines. Read these before making changes to understand the document's purpose, audience, structure principles, and terminology.
- When making large restructuring changes, propose the structure first before implementing
- For moving large chunks of text, it may be easier to ask the human to do it
- Always verify links work after restructuring
