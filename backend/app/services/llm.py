from __future__ import annotations

from typing import Any

from openai import OpenAI

from ..stages import StageDefinition


def _client(settings: dict[str, Any]) -> OpenAI | None:
    api_key = (settings.get("api_key") or "").strip()
    if not api_key:
        return None
    base_url = (settings.get("base_url") or "https://api.openai.com/v1").strip()
    return OpenAI(api_key=api_key, base_url=base_url)


def _paper_line(paper: dict[str, Any]) -> str:
    authors = ", ".join((paper.get("authors_json") or [])[:4]) or "Unknown authors"
    year = paper.get("year") or "n/a"
    venue = paper.get("venue") or paper.get("source_provider") or paper.get("source_type")
    snippet = (paper.get("extracted_text") or paper.get("abstract") or "").strip().replace("\n", " ")
    if len(snippet) > 420:
        snippet = f"{snippet[:420]}..."
    doi = paper.get("doi") or "n/a"
    url = paper.get("url") or ""
    return (
        f"- {paper['title']} ({year}, {venue})\n"
        f"  Authors: {authors}\n"
        f"  DOI: {doi}\n"
        f"  URL: {url}\n"
        f"  Notes: {paper.get('notes', '')}\n"
        f"  Evidence snippet: {snippet or '[no extracted text]'}"
    )


def _project_context(project: dict[str, Any], papers: list[dict[str, Any]]) -> str:
    paper_block = "\n".join(_paper_line(paper) for paper in papers) if papers else "- No papers attached."
    return (
        f"Title: {project['title']}\n"
        f"Idea: {project['idea']}\n"
        f"Background: {project['background']}\n"
        f"Direction: {project['direction']}\n"
        f"Goals: {project['goals']}\n"
        f"Constraints: {project['constraints_text']}\n"
        f"Compute budget: {project['compute_budget']}\n"
        f"API budget: {project['api_budget']}\n"
        f"Attached papers:\n{paper_block}"
    )


def _artifact_shell(stage: StageDefinition, markdown: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for item in stage.artifact_schema:
        payload[item.key] = {
            "label": item.label,
            "type": item.type,
            "description": item.description,
            "status": "refer_to_markdown",
            "summary": f"Derived from the {stage.label} markdown output." if markdown else "",
        }
    return payload


def _fallback_artifacts(
    stage: StageDefinition,
    project: dict[str, Any],
    papers: list[dict[str, Any]],
    prior_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    prior_keys = [entry.get("stage_key") for entry in prior_outputs]
    if stage.key == "scope_alignment":
        return {
            "problem_statement": project["idea"],
            "non_goals": [
                "Do not expand beyond the stated scope and direction.",
                "Do not assume new datasets or baselines without evidence.",
                "Do not claim experimental outcomes before sandbox execution.",
            ],
            "evaluation_boundary": {
                "direction": project["direction"],
                "goals": project["goals"],
                "constraints": project["constraints_text"],
            },
            "approval_questions": [
                "Is the scope narrow enough to execute in the stated budget?",
                "Are any mandatory datasets, baselines, or venues still missing?",
            ],
        }
    if stage.key == "source_grounding":
        return {
            "canonical_sources": [
                {
                    "title": paper["title"],
                    "provider": paper.get("source_provider") or paper["source_type"],
                    "year": paper.get("year") or 0,
                    "venue": paper.get("venue") or "",
                    "doi": paper.get("doi") or "",
                }
                for paper in papers
            ],
            "coverage_gaps": ["Add more source coverage if critical baselines are still missing."] if not papers else [],
            "duplicate_flags": [],
        }
    if stage.key == "literature_map":
        return {
            "topic_clusters": [
                {"name": "Project-aligned evidence", "papers": [paper["title"] for paper in papers[:5]]}
            ],
            "baseline_table": [
                {"baseline": paper["title"], "why_it_matters": paper.get("notes") or "User-provided source"}
                for paper in papers[:4]
            ],
            "open_questions": ["Evidence remains incomplete where no attached paper directly answers the project claim."],
        }
    if stage.key == "synthesis":
        return {
            "hypotheses": [
                {
                    "name": "Primary hypothesis",
                    "statement": f"{project['title']} can be advanced within the current scope.",
                }
            ],
            "assumptions": [{"name": "Evidence sufficiency", "status": "pending_more_validation"}],
            "research_bets": [{"bet": project["direction"], "rationale": "Matches the user-selected focus."}],
        }
    if stage.key == "experiment_design":
        return {
            "experiment_matrix": [
                {"step": "Baseline reproduction", "goal": "Establish a grounded comparator."},
                {"step": "Targeted variant", "goal": "Test the primary hypothesis with one controlled change."},
            ],
            "metrics": [{"name": "Primary task metric", "target": "Better than baseline or justified trade-off"}],
            "ablations": [{"name": "Remove the proposed change", "purpose": "Measure contribution."}],
            "success_criteria": ["The proposed method beats or matches the baseline on the primary metric."],
        }
    if stage.key == "code_prototype":
        return {
            "module_plan": [
                {"module": "data_loading.py", "purpose": "Data access and normalization"},
                {"module": "train_or_eval.py", "purpose": "Experiment entrypoint"},
            ],
            "dependencies": ["numpy", "pandas"],
            "execution_checklist": ["Validate inputs", "Run sandbox stub", "Capture artifacts"],
        }
    if stage.key == "execution_review":
        return {
            "readiness_assessment": {"status": "prototype_only", "evidence": "Sandbox output should be reviewed before scale-up."},
            "failure_playbook": [{"risk": "Dependency drift", "repair": "Reduce the dependency surface and rerun the sandbox."}],
            "next_action": "Review the sandbox output and decide whether to revise the experiment design.",
        }
    if stage.key == "paper_outline":
        return {
            "outline": [
                {"section": "Introduction", "goal": "Frame the problem and stakes."},
                {"section": "Method", "goal": "Describe the proposed approach."},
                {"section": "Evaluation", "goal": "Explain experimental design and evidence limits."},
            ],
            "contribution_map": [{"contribution": "Scoped research contribution", "evidence_anchor": "Experiment design and sandbox artifacts"}],
            "figure_plan": [{"figure": "Workflow overview", "status": "planned"}],
        }
    if stage.key == "paper_drafting":
        return {
            "draft_sections": [{"section": "Introduction", "status": "drafted"}],
            "citation_placeholders": [{"section": "Related Work", "placeholder": "Add literature citations from grounded source list."}],
            "claim_notes": [{"claim": "Method motivation", "evidence": "Source Grounding + Literature Map"}],
        }
    if stage.key == "paper_revision":
        return {
            "revision_log": [{"change": "Softened unsupported claims", "reason": "No completed experimental evidence."}],
            "open_issues": [{"issue": "Need stronger empirical evidence", "severity": "high"}],
            "review_ready_summary": "The draft is reviewable but still evidence-constrained.",
        }
    if stage.key == "paper_export":
        return {
            "markdown_package": {"status": "ready_for_handoff"},
            "latex_package": {"status": "outline_only"},
            "pdf_handoff": {"status": "awaiting real export pipeline"},
        }
    if stage.key == "peer_review":
        return {
            "findings": [{"severity": "medium", "finding": "Claims must stay bounded by the available evidence."}],
            "fixes": [{"action": "Add caveats where sandbox evidence is synthetic or incomplete."}],
        }
    if stage.key == "delivery_package":
        return {
            "delivery_summary": f"Delivery bundle for {project['title']} with {len(prior_keys)} preceding stage outputs.",
            "bundle_manifest": [{"item": entry.get("stage_label"), "status": entry.get("status")} for entry in prior_outputs],
            "next_steps": ["Review approval gates", "Replace synthetic sandbox script with a real experiment."],
        }
    return _artifact_shell(stage)


def _fallback_stage_markdown(
    stage: StageDefinition,
    project: dict[str, Any],
    papers: list[dict[str, Any]],
    prior_outputs: list[dict[str, Any]],
    artifacts: dict[str, Any],
) -> str:
    prior_stage_labels = ", ".join(entry["stage_label"] for entry in prior_outputs[-4:]) or "None yet"
    return (
        f"# {stage.label}\n\n"
        f"Owner: {stage.owner}\n\n"
        f"## Stage Focus\n{stage.prompt_focus}\n\n"
        f"## Contract\n"
        f"- Inputs: {', '.join(stage.contract.inputs)}\n"
        f"- Must produce: {', '.join(stage.contract.must_produce)}\n"
        f"- Quality bar: {', '.join(stage.contract.quality_bar)}\n"
        f"- Disallowed: {', '.join(stage.contract.disallowed)}\n\n"
        f"## Grounded Context\n"
        f"- Project: {project['title']}\n"
        f"- Prior stages: {prior_stage_labels}\n"
        f"- Attached papers: {len(papers)}\n\n"
        f"## Output\n"
        f"- Local fallback mode is active because no OpenAI API key is configured.\n"
        f"- The stage still uses a stage-specific contract and artifact schema.\n"
        f"- Artifact snapshot: `{', '.join(artifacts.keys())}`\n"
    )


def generate_plan_markdown(
    project: dict[str, Any],
    papers: list[dict[str, Any]],
    settings: dict[str, Any],
    stage_catalog: list[dict[str, Any]],
) -> str:
    client = _client(settings)
    context = _project_context(project, papers)
    gate_lines = "\n".join(
        f"- {stage['label']}: {stage['approval_gate']['label']} -> rollback to {stage['approval_gate']['rollback_to_stage_key']}"
        for stage in stage_catalog
        if stage.get("approval_gate")
    )
    stage_lines = "\n".join(
        f"{stage['index']}. {stage['label']} - {stage['summary']}" for stage in stage_catalog
    )
    if client is None:
        return (
            f"# Research Plan\n\n"
            f"## Project Brief\n{context}\n\n"
            f"## Pipeline Stages\n{stage_lines}\n\n"
            f"## Approval Gates\n{gate_lines or '- No stage gates configured.'}\n\n"
            f"## Key Risks\n"
            f"- Missing evidence from must-read papers.\n"
            f"- Sandbox output may be synthetic if Docker is unavailable.\n"
            f"- Manuscript claims must stay bounded by grounded evidence.\n\n"
            f"## Paper Usage Strategy\n"
            f"- Prefer user-provided papers first.\n"
            f"- Expand with live scholarly retrieval only where coverage is incomplete.\n\n"
            f"## Approval Checklist\n"
            f"- Scope matches the idea and constraints.\n"
            f"- Experiment Design, Sandbox Review, and Manuscript Revision gates are acceptable.\n"
            f"- The user accepts that export packaging may remain handoff-oriented in this prototype.\n"
        )

    prompt = (
        "You are building a research execution plan for a local-first GUI research system.\n"
        "Return Markdown only.\n"
        "Include these sections in order: Project Brief, Pipeline Stages, Approval Gates, Key Risks, Paper Usage Strategy, Approval Checklist.\n"
        "Use the provided stage catalog exactly. Mention stage-specific approval gates where present.\n"
        "Do not claim experiments have been run.\n\n"
        f"Stage catalog:\n{stage_catalog}\n\n"
        f"Project context:\n{context}"
    )
    response = client.responses.create(
        model=settings.get("research_model") or "gpt-5.4",
        input=prompt,
    )
    return response.output_text.strip()


def generate_stage_result(
    stage: StageDefinition,
    project: dict[str, Any],
    plan_markdown: str,
    papers: list[dict[str, Any]],
    prior_outputs: list[dict[str, Any]],
    settings: dict[str, Any],
) -> dict[str, Any]:
    client = _client(settings)
    artifacts = _fallback_artifacts(stage, project, papers, prior_outputs)
    if client is None:
        return {
            "content_md": _fallback_stage_markdown(stage, project, papers, prior_outputs, artifacts),
            "artifacts": artifacts,
            "notes": f"{stage.label} completed in local fallback mode.",
        }

    model = settings.get("code_model") if stage.key in {"code_prototype"} else settings.get("research_model")
    context = _project_context(project, papers)
    prior_text = "\n\n".join(
        f"## {entry['stage_label']}\n{entry.get('content_md', '')}" for entry in prior_outputs if entry.get("content_md")
    )
    artifact_schema = [
        {
            "key": item.key,
            "label": item.label,
            "type": item.type,
            "description": item.description,
            "required": item.required,
        }
        for item in stage.artifact_schema
    ]
    prompt = (
        f"You are the {stage.owner} in a staged research pipeline.\n"
        "Return Markdown only.\n"
        "Ground every recommendation in the project brief, attached papers, and prior stage outputs.\n"
        "Do not fabricate results or citations. If evidence is missing, say so.\n"
        "Use the stage-specific contract and artifact schema below.\n"
        "Structure the markdown with these headings in order: Stage Focus, Inputs Used, Decisions, Output, Risks, Artifact Checklist.\n\n"
        f"Stage: {stage.label}\n"
        f"Stage focus: {stage.prompt_focus}\n"
        f"Contract: inputs={list(stage.contract.inputs)}; must_produce={list(stage.contract.must_produce)}; "
        f"quality_bar={list(stage.contract.quality_bar)}; disallowed={list(stage.contract.disallowed)}\n"
        f"Artifact schema: {artifact_schema}\n\n"
        f"Project context:\n{context}\n\n"
        f"Approved plan:\n{plan_markdown}\n\n"
        f"Previous stage outputs:\n{prior_text or 'None yet.'}\n"
    )
    response = client.responses.create(
        model=model or "gpt-5.4",
        input=prompt,
    )
    return {
        "content_md": response.output_text.strip(),
        "artifacts": _artifact_shell(stage, response.output_text),
        "notes": f"{stage.label} completed with a stage-specific contract.",
    }


def test_connection(settings: dict[str, Any]) -> dict[str, Any]:
    client = _client(settings)
    if client is None:
        return {"ok": False, "message": "Missing API key."}
    response = client.responses.create(
        model=settings.get("research_model") or "gpt-5.4",
        input="Reply with the single word: ready",
    )
    return {"ok": True, "message": response.output_text.strip() or "ready"}
