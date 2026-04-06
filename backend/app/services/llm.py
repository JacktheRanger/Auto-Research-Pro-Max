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


def _project_context(project: dict[str, Any], papers: list[dict[str, Any]]) -> str:
    paper_lines: list[str] = []
    for paper in papers:
        snippet = (paper.get("extracted_text") or "").strip().replace("\n", " ")
        if len(snippet) > 500:
            snippet = f"{snippet[:500]}..."
        paper_lines.append(
            f"- {paper['title']} [{paper['source_type']}] {paper.get('url', '')}\n  Notes: {paper.get('notes', '')}\n  Snippet: {snippet}"
        )
    paper_block = "\n".join(paper_lines) if paper_lines else "- No papers attached."
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


def generate_plan_markdown(
    project: dict[str, Any],
    papers: list[dict[str, Any]],
    settings: dict[str, Any],
    stage_catalog: list[dict[str, Any]],
) -> str:
    client = _client(settings)
    context = _project_context(project, papers)
    if client is None:
        stage_lines = "\n".join(
            f"{stage['index']}. {stage['label']} - {stage['summary']}" for stage in stage_catalog
        )
        return (
            f"# Research Plan\n\n"
            f"## Project Brief\n{context}\n\n"
            f"## Recommended Pipeline\n{stage_lines}\n\n"
            f"## Risks\n"
            f"- Missing evidence from must-read papers.\n"
            f"- The first version should stay grounded in user-provided sources and avoid unsupported claims.\n"
            f"- Code generation should remain prototype-level until execution sandboxing is expanded.\n\n"
            f"## Approval Checklist\n"
            f"- Scope matches the idea and constraints.\n"
            f"- Attached papers cover the critical background.\n"
            f"- The user accepts a reduced-stage v1 instead of a full autonomous lab.\n"
        )

    prompt = (
        "You are building a research execution plan for a local-first GUI research system.\n"
        "Return Markdown only.\n"
        "Include these sections in order: "
        "Project Brief, Pipeline Stages, Key Risks, Paper Usage Strategy, Approval Checklist.\n"
        "Pipeline Stages must use the provided reduced-stage catalog and explain why each stage exists.\n"
        "Do not claim experiments have been run.\n\n"
        f"Stage catalog:\n{stage_catalog}\n\n"
        f"Project context:\n{context}"
    )
    response = client.responses.create(
        model=settings.get("research_model") or "gpt-5.4",
        input=prompt,
    )
    return response.output_text.strip()


def generate_stage_markdown(
    stage: StageDefinition,
    project: dict[str, Any],
    plan_markdown: str,
    papers: list[dict[str, Any]],
    prior_outputs: list[dict[str, Any]],
    settings: dict[str, Any],
) -> str:
    client = _client(settings)
    context = _project_context(project, papers)
    prior_text = "\n\n".join(
        f"## {entry['stage_label']}\n{entry.get('content_md', '')}" for entry in prior_outputs if entry.get("content_md")
    )
    if client is None:
        return (
            f"# {stage.label}\n\n"
            f"Owner: {stage.owner}\n\n"
            f"## Objective\n{stage.summary}\n\n"
            f"## Grounded Inputs\n{context}\n\n"
            f"## v1 Output\n"
            f"- This is a local fallback output because no OpenAI API key is configured.\n"
            f"- The stage is still tracked and persisted so the GUI and workflow remain usable.\n"
            f"- Expand this stage later with real retrieval, execution, and review agents.\n"
        )

    model = settings.get("code_model") if stage.key == "code_prototype" else settings.get("research_model")
    prompt = (
        f"You are the {stage.owner} in a staged research pipeline.\n"
        "Return Markdown only.\n"
        "Ground every recommendation in the project brief and attached papers.\n"
        "Do not fabricate results or citations. If evidence is missing, say so.\n"
        f"Stage: {stage.label}\n"
        f"Stage objective: {stage.summary}\n\n"
        f"Project context:\n{context}\n\n"
        f"Approved plan:\n{plan_markdown}\n\n"
        f"Previous stage outputs:\n{prior_text or 'None yet.'}\n"
    )
    response = client.responses.create(
        model=model or "gpt-5.4",
        input=prompt,
    )
    return response.output_text.strip()


def test_connection(settings: dict[str, Any]) -> dict[str, Any]:
    client = _client(settings)
    if client is None:
        return {"ok": False, "message": "Missing API key."}
    response = client.responses.create(
        model=settings.get("research_model") or "gpt-5.4",
        input="Reply with the single word: ready",
    )
    return {"ok": True, "message": response.output_text.strip() or "ready"}
