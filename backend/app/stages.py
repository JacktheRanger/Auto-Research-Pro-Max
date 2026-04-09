from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArtifactSchemaItem:
    key: str
    label: str
    type: str
    description: str
    required: bool = True


@dataclass(frozen=True)
class StageContract:
    inputs: tuple[str, ...]
    must_produce: tuple[str, ...]
    quality_bar: tuple[str, ...]
    disallowed: tuple[str, ...]


@dataclass(frozen=True)
class ApprovalGate:
    label: str
    summary: str
    rollback_to_stage_key: str


@dataclass(frozen=True)
class StageDefinition:
    index: int
    key: str
    label: str
    summary: str
    owner: str
    prompt_focus: str
    contract: StageContract
    artifact_schema: tuple[ArtifactSchemaItem, ...]
    approval_gate: ApprovalGate | None = None


PIPELINE_STAGES: tuple[StageDefinition, ...] = (
    StageDefinition(
        index=1,
        key="scope_alignment",
        label="Scope Alignment",
        summary="Bound the research problem, non-goals, and acceptance criteria before any expansion.",
        owner="Research Strategist",
        prompt_focus=(
            "Translate the raw idea into a sharply bounded research brief with explicit non-goals, "
            "target audience, evaluation boundary, and approval questions."
        ),
        contract=StageContract(
            inputs=(
                "Project brief, background, direction, goals, and constraints",
                "Any must-read papers already attached by the user",
            ),
            must_produce=(
                "One paragraph problem statement",
                "Three to five concrete non-goals",
                "Named evaluation boundary and deliverable scope",
                "Open questions that block downstream work",
            ),
            quality_bar=(
                "The scope is small enough to test within the stated compute and API budget",
                "Non-goals remove at least two plausible but out-of-scope directions",
                "No fabricated datasets, claims, or papers",
            ),
            disallowed=(
                "Do not silently expand the project into a general survey",
                "Do not assume results already exist",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("problem_statement", "Problem Statement", "markdown", "Bounded research target."),
            ArtifactSchemaItem("non_goals", "Non-goals", "string[]", "Explicit exclusions."),
            ArtifactSchemaItem("evaluation_boundary", "Evaluation Boundary", "object", "Task, datasets, and success boundary."),
            ArtifactSchemaItem("approval_questions", "Approval Questions", "string[]", "Questions the user should confirm."),
        ),
    ),
    StageDefinition(
        index=2,
        key="source_grounding",
        label="Source Grounding",
        summary="Normalize user-provided papers and turn them into reliable context with metadata and evidence snippets.",
        owner="Paper Ingestion Agent",
        prompt_focus=(
            "Organize the provided papers, identify what each source is useful for, and expose missing evidence."
        ),
        contract=StageContract(
            inputs=(
                "Attached local PDFs and remote links",
                "Recovered metadata such as DOI, venue, year, and authors when available",
            ),
            must_produce=(
                "Canonical source inventory",
                "Short evidence-oriented snippet for each source",
                "Coverage gaps and duplicated evidence flags",
            ),
            quality_bar=(
                "Each source has a stated role such as benchmark, method, or background",
                "Missing metadata is surfaced rather than guessed",
                "Evidence snippets are quoted or paraphrased from extracted text only",
            ),
            disallowed=(
                "Do not cite papers that are not in the provided source inventory",
                "Do not infer bibliographic metadata without marking it as missing",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("canonical_sources", "Canonical Sources", "object[]", "Normalized attached sources."),
            ArtifactSchemaItem("coverage_gaps", "Coverage Gaps", "string[]", "Missing evidence or must-read gaps."),
            ArtifactSchemaItem("duplicate_flags", "Duplicate Flags", "string[]", "Potential duplicates or collisions."),
        ),
    ),
    StageDefinition(
        index=3,
        key="literature_retrieval",
        label="Literature Retrieval",
        summary="Expand the evidence base through OpenAlex, Semantic Scholar, Crossref, and arXiv adapters.",
        owner="Retriever Mesh",
        prompt_focus=(
            "Use scholarly retrieval results to broaden coverage, compare overlapping hits, and rank follow-up papers."
        ),
        contract=StageContract(
            inputs=(
                "Bounded project scope from Scope Alignment",
                "Grounded user sources from Source Grounding",
                "Live retrieval results from OpenAlex, Semantic Scholar, Crossref, and arXiv",
            ),
            must_produce=(
                "Search queries used",
                "High-priority retrieved papers with provenance",
                "Conflicts or disagreements across providers",
            ),
            quality_bar=(
                "At least one query variant targets method terms and one targets task terms",
                "Each recommended paper lists its provider and why it matters",
                "Overlapping hits are deduplicated into a canonical list",
            ),
            disallowed=(
                "Do not flatten all providers into one opaque list without provenance",
                "Do not hide retrieval failures or empty results",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("queries", "Queries", "string[]", "Queries dispatched to live adapters."),
            ArtifactSchemaItem("provider_results", "Provider Results", "object[]", "Per-provider top hits."),
            ArtifactSchemaItem("recommended_reads", "Recommended Reads", "object[]", "Deduplicated high-priority papers."),
        ),
    ),
    StageDefinition(
        index=4,
        key="literature_map",
        label="Literature Map",
        summary="Turn the grounded and retrieved evidence into themes, baselines, and open questions.",
        owner="Literature Analyst",
        prompt_focus=(
            "Synthesize the paper set into a map of baselines, methodological clusters, unresolved questions, and weakly supported claims."
        ),
        contract=StageContract(
            inputs=(
                "Source Grounding artifacts",
                "Literature Retrieval artifacts",
            ),
            must_produce=(
                "Topic clusters with representative papers",
                "Baseline comparison table",
                "Explicit open questions and evidence holes",
            ),
            quality_bar=(
                "Clusters distinguish methods, tasks, and evaluation practices",
                "Every open question traces back to a source gap or disagreement",
                "Baseline table includes at least one likely comparator for the project",
            ),
            disallowed=(
                "Do not present literature coverage as exhaustive",
                "Do not convert weak evidence into strong claims",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("topic_clusters", "Topic Clusters", "object[]", "Major themes and representative papers."),
            ArtifactSchemaItem("baseline_table", "Baseline Table", "object[]", "Candidate baselines and comparison axes."),
            ArtifactSchemaItem("open_questions", "Open Questions", "string[]", "Unresolved issues and evidence holes."),
        ),
    ),
    StageDefinition(
        index=5,
        key="synthesis",
        label="Synthesis",
        summary="Extract testable hypotheses, assumptions, and research bets from the evidence map.",
        owner="Synthesis Agent",
        prompt_focus=(
            "Convert the literature map into a small number of falsifiable hypotheses and the assumptions they depend on."
        ),
        contract=StageContract(
            inputs=(
                "Literature Map outputs",
                "Scope Alignment boundary",
            ),
            must_produce=(
                "Primary hypothesis and at least one fallback hypothesis",
                "Assumption register",
                "Evidence-backed rationale for each bet",
            ),
            quality_bar=(
                "Hypotheses are falsifiable and tied to measurable outcomes",
                "Assumptions call out what evidence is still missing",
                "At least one fallback path is included if the main bet fails",
            ),
            disallowed=(
                "Do not produce generic 'improve performance' hypotheses without an axis and comparator",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("hypotheses", "Hypotheses", "object[]", "Primary and fallback hypotheses."),
            ArtifactSchemaItem("assumptions", "Assumptions", "object[]", "Assumptions and confidence levels."),
            ArtifactSchemaItem("research_bets", "Research Bets", "object[]", "Why the team should pursue these bets."),
        ),
    ),
    StageDefinition(
        index=6,
        key="experiment_design",
        label="Experiment Design",
        summary="Design datasets, metrics, ablations, and success criteria that can actually be executed.",
        owner="Experiment Designer",
        prompt_focus=(
            "Produce a concrete experimental plan with metrics, datasets, ablations, failure criteria, and a minimal viable matrix."
        ),
        contract=StageContract(
            inputs=(
                "Synthesis hypotheses",
                "Compute and API budgets",
                "Known datasets or evaluation constraints from the brief",
            ),
            must_produce=(
                "Experiment matrix",
                "Metric definitions",
                "Ablation list",
                "Go/no-go success criteria",
            ),
            quality_bar=(
                "The matrix fits the stated compute budget",
                "Metrics are measurable and clearly defined",
                "Ablations isolate the central hypothesis rather than adding noise",
            ),
            disallowed=(
                "Do not require undisclosed private resources",
                "Do not propose experiments that exceed the stated budgets without flagging it",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("experiment_matrix", "Experiment Matrix", "object[]", "Ordered experiment plan."),
            ArtifactSchemaItem("metrics", "Metrics", "object[]", "Metric definitions and targets."),
            ArtifactSchemaItem("ablations", "Ablations", "object[]", "Ablation plan."),
            ArtifactSchemaItem("success_criteria", "Success Criteria", "string[]", "Go/no-go rules."),
        ),
        approval_gate=ApprovalGate(
            label="Experiment Design Gate",
            summary="Confirm the experiment matrix before code or sandbox execution proceeds.",
            rollback_to_stage_key="literature_map",
        ),
    ),
    StageDefinition(
        index=7,
        key="code_prototype",
        label="Code Prototype",
        summary="Translate the design into an executable prototype plan, with runnable steps and dependency choices.",
        owner="Codex Builder",
        prompt_focus=(
            "Outline the implementation shape, scripts, dependencies, and execution checklist needed to run the first experiment pass."
        ),
        contract=StageContract(
            inputs=(
                "Approved experiment design",
                "Project constraints and repository context if present",
            ),
            must_produce=(
                "Prototype file or module plan",
                "Dependency list",
                "Execution checklist",
            ),
            quality_bar=(
                "Dependencies are minimal and justified",
                "The checklist is specific enough to execute inside a sandbox",
            ),
            disallowed=(
                "Do not claim code has already been run unless it is reflected in sandbox artifacts",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("module_plan", "Module Plan", "object[]", "Planned modules or scripts."),
            ArtifactSchemaItem("dependencies", "Dependencies", "string[]", "Requested runtime dependencies."),
            ArtifactSchemaItem("execution_checklist", "Execution Checklist", "string[]", "Ordered execution steps."),
        ),
    ),
    StageDefinition(
        index=8,
        key="experiment_sandbox",
        label="Experiment Sandbox",
        summary="Execute repository-aware setup and benchmark commands in Docker with timeout, allowlisted packages, and captured artifacts.",
        owner="Sandbox Runner",
        prompt_focus=(
            "Run the proposed experiment in a Docker sandbox, capture outputs, and summarize what actually happened."
        ),
        contract=StageContract(
            inputs=(
                "Code Prototype dependency request and checklist",
                "Experiment Design success criteria",
            ),
            must_produce=(
                "Sandbox execution manifest",
                "Requested versus allowlisted packages",
                "Captured stdout, stderr, and artifact files",
            ),
            quality_bar=(
                "Execution is isolated in Docker with network disabled",
                "Timeout is enforced",
                "Artifacts are written to disk and enumerated back into the run record",
            ),
            disallowed=(
                "Do not silently fall back to in-process execution",
                "Do not install packages outside the allowlist",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("sandbox_request", "Sandbox Request", "object", "Execution request and policy."),
            ArtifactSchemaItem("sandbox_result", "Sandbox Result", "object", "Execution result and metrics."),
            ArtifactSchemaItem("artifact_manifest", "Artifact Manifest", "object[]", "Files captured from the sandbox."),
        ),
        approval_gate=ApprovalGate(
            label="Sandbox Review Gate",
            summary="Review sandbox outputs before the workflow moves into manuscript preparation.",
            rollback_to_stage_key="experiment_design",
        ),
    ),
    StageDefinition(
        index=9,
        key="execution_review",
        label="Execution Review",
        summary="Assess feasibility, runtime risk, and repair paths using the actual sandbox record.",
        owner="Execution Reviewer",
        prompt_focus=(
            "Use the sandbox artifacts to judge readiness, call out failures, and define repair paths."
        ),
        contract=StageContract(
            inputs=(
                "Sandbox execution result",
                "Experiment Design success criteria",
            ),
            must_produce=(
                "Readiness assessment",
                "Failure and recovery playbook",
                "Recommended next action",
            ),
            quality_bar=(
                "Assessment refers to actual sandbox output rather than hypothetical execution",
                "Recovery playbook prioritizes the smallest change that unblocks progress",
            ),
            disallowed=(
                "Do not state the prototype is production ready without evidence",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("readiness_assessment", "Readiness Assessment", "object", "Readiness and blockers."),
            ArtifactSchemaItem("failure_playbook", "Failure Playbook", "object[]", "Repair paths and owners."),
            ArtifactSchemaItem("next_action", "Next Action", "string", "Best next execution step."),
        ),
    ),
    StageDefinition(
        index=10,
        key="paper_outline",
        label="Paper Outline",
        summary="Build a section-by-section outline grounded in the approved scope and execution record.",
        owner="Paper Architect",
        prompt_focus=(
            "Create a paper outline that mirrors the available evidence and avoids unsupported sections."
        ),
        contract=StageContract(
            inputs=(
                "Approved scope, synthesis, experiment design, and execution review",
            ),
            must_produce=(
                "Section outline",
                "Contribution-to-section map",
                "Figure and table plan",
            ),
            quality_bar=(
                "Sections only cover material with evidence support",
                "Each contribution has an explicit evidence anchor",
            ),
            disallowed=(
                "Do not invent results sections without experiment evidence",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("outline", "Outline", "object[]", "Structured paper outline."),
            ArtifactSchemaItem("contribution_map", "Contribution Map", "object[]", "Contribution to section mapping."),
            ArtifactSchemaItem("figure_plan", "Figure Plan", "object[]", "Planned figures and tables."),
        ),
    ),
    StageDefinition(
        index=11,
        key="paper_drafting",
        label="Paper Drafting",
        summary="Draft the manuscript sections from the outline and available evidence.",
        owner="Paper Drafter",
        prompt_focus=(
            "Draft the paper in sections, preserving uncertainty where evidence is incomplete."
        ),
        contract=StageContract(
            inputs=(
                "Paper Outline artifacts",
                "Execution Review findings",
                "Grounded paper evidence",
            ),
            must_produce=(
                "Drafted sections",
                "Citation placeholders",
                "Claim-to-evidence notes",
            ),
            quality_bar=(
                "Claims are matched to evidence or marked as pending",
                "The draft avoids overstating sandbox observations",
            ),
            disallowed=(
                "Do not convert placeholders into fake citations",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("draft_sections", "Draft Sections", "object[]", "Section drafts."),
            ArtifactSchemaItem("citation_placeholders", "Citation Placeholders", "object[]", "Places that need citations."),
            ArtifactSchemaItem("claim_notes", "Claim Notes", "object[]", "Claim-to-evidence notes."),
        ),
    ),
    StageDefinition(
        index=12,
        key="paper_revision",
        label="Paper Revision",
        summary="Tighten the draft, resolve weak claims, and prepare a review-ready manuscript state.",
        owner="Revision Editor",
        prompt_focus=(
            "Revise for clarity, evidentiary discipline, and review readiness; list unresolved risks explicitly."
        ),
        contract=StageContract(
            inputs=(
                "Paper Drafting output",
                "Execution Review findings",
                "Source Grounding evidence",
            ),
            must_produce=(
                "Revision log",
                "Resolved versus unresolved issues",
                "Review-ready draft summary",
            ),
            quality_bar=(
                "Weak claims are either supported, softened, or removed",
                "Open issues are explicit and actionable",
            ),
            disallowed=(
                "Do not hide unresolved evidence gaps",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("revision_log", "Revision Log", "object[]", "What changed and why."),
            ArtifactSchemaItem("open_issues", "Open Issues", "object[]", "Remaining weaknesses."),
            ArtifactSchemaItem("review_ready_summary", "Review-ready Summary", "string", "State of the manuscript."),
        ),
        approval_gate=ApprovalGate(
            label="Manuscript Revision Gate",
            summary="Approve the revised manuscript state before export and delivery.",
            rollback_to_stage_key="paper_outline",
        ),
    ),
    StageDefinition(
        index=13,
        key="paper_export",
        label="Paper Export",
        summary="Generate real manuscript assets in Markdown, LaTeX, bibliography, and compiled PDF formats.",
        owner="Export Manager",
        prompt_focus=(
            "Build final manuscript files, bibliography assets, citation checks, and claim-evidence validation outputs."
        ),
        contract=StageContract(
            inputs=(
                "Approved Paper Revision output",
            ),
            must_produce=(
                "Markdown manuscript package",
                "LaTeX manuscript package",
                "Compiled PDF package",
                "Bibliography and citation verification artifacts",
                "Claim-evidence consistency report",
            ),
            quality_bar=(
                "Markdown, LaTeX, BibTeX, and PDF files are all written to disk",
                "Citation verification and claim-evidence checks surface missing support explicitly",
                "Any missing references or figures are surfaced",
            ),
            disallowed=(
                "Do not claim a PDF was compiled unless the artifact manifest says so",
                "Do not mark unresolved citation errors as verified",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("markdown_package", "Markdown Package", "object", "Markdown export package."),
            ArtifactSchemaItem("latex_package", "LaTeX Package", "object", "LaTeX export package."),
            ArtifactSchemaItem("pdf_package", "PDF Package", "object", "Compiled PDF export package."),
            ArtifactSchemaItem("bibliography", "Bibliography", "object", "Generated references and BibTeX assets."),
            ArtifactSchemaItem(
                "citation_verification",
                "Citation Verification",
                "object",
                "Citation verification report and unresolved keys.",
            ),
            ArtifactSchemaItem(
                "claim_evidence_report",
                "Claim-Evidence Report",
                "object",
                "Claim support status across papers, experiments, and manuscript text.",
            ),
        ),
    ),
    StageDefinition(
        index=14,
        key="peer_review",
        label="Peer Review",
        summary="Pressure-test the claims and package the highest-value reviewer feedback.",
        owner="Reviewer Panel",
        prompt_focus=(
            "Review the package like an external reviewer and identify the highest-severity weaknesses."
        ),
        contract=StageContract(
            inputs=(
                "Paper Export package and verification reports",
                "Revision log and open issues",
            ),
            must_produce=(
                "Reviewer findings ordered by severity",
                "Rebuttal or fix suggestions",
                "Venue-specific peer-review rubrics",
            ),
            quality_bar=(
                "Findings are concrete and tied to a section, claim, or artifact",
                "Feedback distinguishes evidence gaps from writing issues",
                "At least one rubric profile is recommended for the current manuscript",
            ),
            disallowed=(
                "Do not produce empty praise without actionable review content",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("findings", "Findings", "object[]", "Reviewer findings."),
            ArtifactSchemaItem("fixes", "Fixes", "object[]", "Suggested fixes or rebuttals."),
            ArtifactSchemaItem("rubrics", "Rubrics", "object[]", "Venue-specific rubric evaluations."),
        ),
    ),
    StageDefinition(
        index=15,
        key="delivery_package",
        label="Delivery Package",
        summary="Assemble the final plan, evidence, manuscript state, and next steps into a deliverable bundle.",
        owner="Delivery Manager",
        prompt_focus=(
            "Prepare the final delivery bundle, summarizing approvals, artifacts, outputs, and next actions."
        ),
        contract=StageContract(
            inputs=(
                "All prior stage outputs and gate decisions",
            ),
            must_produce=(
                "Delivery summary",
                "Artifact bundle manifest",
                "Recommended next actions",
            ),
            quality_bar=(
                "The delivery package identifies what is final, provisional, and missing",
                "Gate decisions and rollback history are reflected in the summary",
            ),
            disallowed=(
                "Do not describe rejected or rolled-back stages as final outputs",
            ),
        ),
        artifact_schema=(
            ArtifactSchemaItem("delivery_summary", "Delivery Summary", "string", "What the user is receiving."),
            ArtifactSchemaItem("bundle_manifest", "Bundle Manifest", "object[]", "Files, outputs, and major artifacts."),
            ArtifactSchemaItem("next_steps", "Next Steps", "string[]", "Suggested follow-up work."),
            ArtifactSchemaItem("bundle_archive", "Bundle Archive", "object", "Downloadable archive of delivery assets."),
        ),
    ),
)

STAGE_COUNT = len(PIPELINE_STAGES)


def _artifact_schema_to_dict(items: tuple[ArtifactSchemaItem, ...]) -> list[dict[str, Any]]:
    return [
        {
            "key": item.key,
            "label": item.label,
            "type": item.type,
            "description": item.description,
            "required": item.required,
        }
        for item in items
    ]


def _contract_to_dict(contract: StageContract) -> dict[str, Any]:
    return {
        "inputs": list(contract.inputs),
        "must_produce": list(contract.must_produce),
        "quality_bar": list(contract.quality_bar),
        "disallowed": list(contract.disallowed),
    }


def stage_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for stage in PIPELINE_STAGES:
        catalog.append(
            {
                "index": stage.index,
                "key": stage.key,
                "label": stage.label,
                "summary": stage.summary,
                "owner": stage.owner,
                "prompt_focus": stage.prompt_focus,
                "contract": _contract_to_dict(stage.contract),
                "artifact_schema": _artifact_schema_to_dict(stage.artifact_schema),
                "approval_gate": (
                    {
                        "label": stage.approval_gate.label,
                        "summary": stage.approval_gate.summary,
                        "rollback_to_stage_key": stage.approval_gate.rollback_to_stage_key,
                    }
                    if stage.approval_gate
                    else None
                ),
            }
        )
    return catalog


def stage_by_key(stage_key: str) -> StageDefinition | None:
    for stage in PIPELINE_STAGES:
        if stage.key == stage_key:
            return stage
    return None


def stage_by_index(stage_index: int) -> StageDefinition | None:
    for stage in PIPELINE_STAGES:
        if stage.index == stage_index:
            return stage
    return None


def rollback_target_index(stage: StageDefinition) -> int | None:
    if stage.approval_gate is None:
        return None
    target = stage_by_key(stage.approval_gate.rollback_to_stage_key)
    return target.index if target else None
