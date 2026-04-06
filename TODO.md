# TODO

## High Priority

- Add true literature retrieval adapters for `OpenAlex`, `Semantic Scholar`, `Crossref`, and `arXiv`.
- Replace generic stage generation with stage-specific prompts, contracts, and artifact schemas.
- Add a real experiment sandbox with `Docker`, timeouts, package allowlists, and artifact capture.
- Split the current `paper_draft` stage into outline, drafting, revision, and export sub-pipelines.
- Support pause, resume, reject, and rollback at selected approval gates.

## Retrieval And Papers

- Extract richer metadata from remote paper URLs, including DOI, venue, year, and author list.
- Add PDF preview thumbnails and first-page rendering for uploaded papers.
- Add chunking and embeddings for paper-grounded retrieval.
- Add paper deduplication and citation-key normalization.

## Workflow

- Expand the current 10-stage pipeline with more stages as the product matures.
- Add optional branching to compare multiple hypotheses.
- Add stage retry policies and failure recovery playbooks.
- Add per-stage cost tracking and usage analytics.
- Add project templates for different research modes: survey, benchmark, implementation, ablation-heavy paper.
- Allow the user to customize the stage count and stage list per project.

## Writing And Delivery

- Export final packages as `Markdown`, `LaTeX`, and compiled `PDF`.
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
