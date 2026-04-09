# TODO

## High Priority

- Replace the current synthetic Docker experiment stub with repository-aware execution of real user code and benchmarks.
- Validate stage outputs against their declared contracts and artifact schemas before marking stages complete.
- Persist approval comments and gate rationale so pause, reject, and rollback decisions are auditable.

## Recently Completed

- Added live literature retrieval adapters for `OpenAlex`, `Semantic Scholar`, `Crossref`, and `arXiv`.
- Replaced generic stage generation with stage-specific prompts, contracts, artifact schemas, and approval gates.
- Added Docker-based sandbox execution with timeouts, package allowlists, and artifact capture.
- Split the manuscript flow into outline, drafting, revision, export, peer review, and delivery stages.
- Added pause, resume, reject, and rollback controls at selected approval gates.
- Added richer paper metadata extraction, PDF previews, chunking, deduplication, citation-key normalization, and paper-grounded retrieval.

## Retrieval And Papers

- Add OCR fallback for scanned or image-only PDFs.
- Add manual metadata editing and provider refresh controls for imported papers.
- Add incremental re-indexing and larger-scale local retrieval storage for bigger paper collections.
- Add citation-graph extraction and bibliography-ready reference exports on top of normalized paper identifiers.

## Workflow

- Add optional branching to compare multiple hypotheses.
- Add stage retry policies and failure recovery playbooks.
- Add per-stage cost tracking and usage analytics.
- Add project templates for different research modes: survey, benchmark, implementation, ablation-heavy paper.
- Allow the user to customize the current stage count and stage list per project.

## Writing And Delivery

- Export real final packages as `Markdown`, `LaTeX`, and compiled `PDF`, not just handoff plans.
- Add bibliography generation and citation verification.
- Add claim-evidence consistency checks between papers, experiments, and manuscript text.
- Add peer-review rubrics for different venues.

## Product

- Add authentication and multi-user workspaces.
- Add project duplication, archiving, and search.
- Add richer run history, diffs, and artifact version browsing.
- Add notifications for plan-ready, approval-needed, and run-complete events.
- Add first-class Windows support, including one-click start/stop scripts and packaging.
- Add deployment recipes for Docker and Cloudflare-hosted frontend plus API backend.
