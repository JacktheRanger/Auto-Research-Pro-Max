# TODO

## High Priority

- Replace the current synthetic Docker experiment stub with repository-aware execution of real user code and benchmarks.
- Validate stage outputs against their declared contracts and artifact schemas before marking stages complete.
- Persist approval comments and gate rationale so pause, reject, and rollback decisions are auditable.

## Retrieval And Papers

- Add OCR fallback for scanned or image-only PDFs.
- Add manual metadata editing and provider refresh controls for imported papers.
- Add incremental re-indexing and larger-scale local retrieval storage for bigger paper collections.
- Add citation-graph extraction on top of normalized paper identifiers.

## Workflow

- Add optional branching to compare multiple hypotheses.
- Add stage retry policies.
- Add per-stage cost tracking and usage analytics.
- Add project templates for different research modes: survey, benchmark, implementation, ablation-heavy paper.
- Allow the user to customize the current stage count and stage list per project.

## Product

- Add authentication and multi-user workspaces.
- Add project duplication, archiving, and search.
- Add richer run history, diffs, and artifact version browsing.
- Add notifications for plan-ready, approval-needed, and run-complete events.
- Add first-class Windows support, including one-click start/stop scripts and packaging.
- Add deployment recipes for Docker and Cloudflare-hosted frontend plus API backend.
