from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StageDefinition:
    index: int
    key: str
    label: str
    summary: str
    owner: str


V1_STAGES: tuple[StageDefinition, ...] = (
    StageDefinition(
        index=1,
        key="scope_alignment",
        label="Scope Alignment",
        summary="Turn the raw idea, background, and constraints into a bounded research target.",
        owner="Research Strategist",
    ),
    StageDefinition(
        index=2,
        key="source_grounding",
        label="Source Grounding",
        summary="Normalize user-specified papers and turn them into usable context snippets.",
        owner="Paper Ingestion Agent",
    ),
    StageDefinition(
        index=3,
        key="literature_map",
        label="Literature Map",
        summary="Produce a structured map of themes, baselines, and open questions.",
        owner="Literature Analyst",
    ),
    StageDefinition(
        index=4,
        key="synthesis",
        label="Synthesis",
        summary="Extract hypotheses, assumptions, and research bets worth testing.",
        owner="Synthesis Agent",
    ),
    StageDefinition(
        index=5,
        key="experiment_design",
        label="Experiment Design",
        summary="Define datasets, evaluation metrics, ablations, and success criteria.",
        owner="Experiment Designer",
    ),
    StageDefinition(
        index=6,
        key="code_prototype",
        label="Code Prototype",
        summary="Generate a first implementation sketch and runtime checklist.",
        owner="Codex Builder",
    ),
    StageDefinition(
        index=7,
        key="execution_review",
        label="Execution Review",
        summary="Review feasibility, expected runtime, failure modes, and repair steps.",
        owner="Execution Reviewer",
    ),
    StageDefinition(
        index=8,
        key="paper_draft",
        label="Paper Draft",
        summary="Assemble an abstract, outline, contributions, and first-pass manuscript.",
        owner="Paper Writer",
    ),
    StageDefinition(
        index=9,
        key="peer_review",
        label="Peer Review",
        summary="Stress-test claims, identify gaps, and propose revision tasks.",
        owner="Reviewer Panel",
    ),
    StageDefinition(
        index=10,
        key="delivery_package",
        label="Delivery Package",
        summary="Bundle the approved plan, stage outputs, and next steps into final deliverables.",
        owner="Delivery Manager",
    ),
)

STAGE_COUNT = len(V1_STAGES)


def stage_catalog() -> list[dict[str, str | int]]:
    return [asdict(stage) for stage in V1_STAGES]

