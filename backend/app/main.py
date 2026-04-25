from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .db import (
    DATA_DIR,
    approve_plan,
    delete_paper,
    delete_project,
    duplicate_project,
    get_latest_run,
    get_paper,
    get_plan,
    get_project,
    get_run,
    init_db,
    list_papers,
    list_project_runs,
    list_projects,
    list_run_audit_events,
    list_run_stages,
    save_plan,
    save_settings,
    create_project,
    get_settings,
    set_project_archived,
    update_project_disabled_stages,
    update_project_execution_config,
)
from .services.citation_graph import build_citation_graph
from .services.diffing import diff_runs
from .services.events import event_hub
from .services.grounding import reindex_project_papers, retrieve_grounded_snippets
from .services.llm import generate_plan_markdown, test_connection
from .services.papers import (
    refresh_paper_metadata,
    reocr_paper,
    save_literature_result,
    save_remote_paper,
    save_uploaded_paper,
    update_paper_metadata,
)
from .services.retrieval import search_literature
from .services.runner import pause_run, reject_run, resume_run, retry_stage, rollback_run, start_run
from .stages import STAGE_COUNT, stage_catalog
from .templates import list_project_templates


class SettingsPayload(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    research_model: str = "gpt-5.4"
    code_model: str = "gpt-5.4"
    embedding_model: str = ""
    notes: str = ""


class ProjectPayload(BaseModel):
    title: str = Field(min_length=3)
    idea: str = Field(min_length=10)
    background: str = Field(min_length=10)
    direction: str = Field(min_length=5)
    goals: str = Field(min_length=5)
    constraints_text: str = ""
    compute_budget: str = ""
    api_budget: str = ""
    repo_path: str = ""
    repo_url: str = ""
    repo_ref: str = ""
    sandbox_workdir: str = ""
    sandbox_setup_command: str = ""
    sandbox_run_command: str = ""
    expected_artifacts: list[str] = Field(default_factory=list)


class ProjectExecutionPayload(BaseModel):
    repo_path: str = ""
    repo_url: str = ""
    repo_ref: str = ""
    sandbox_workdir: str = ""
    sandbox_setup_command: str = ""
    sandbox_run_command: str = ""
    expected_artifacts: list[str] = Field(default_factory=list)
    sandbox_base_image: str = ""
    sandbox_extra_packages: list[str] = Field(default_factory=list)
    sandbox_apt_packages: list[str] = Field(default_factory=list)
    sandbox_pip_index_url: str = ""
    sandbox_timeout_seconds: int = 0
    sandbox_max_attempts: int = 0


class RemotePaperPayload(BaseModel):
    url: str
    title: str = ""
    notes: str = ""


class LiteratureSearchPayload(BaseModel):
    query: str = Field(min_length=3)
    limit_per_provider: int = Field(default=3, ge=1, le=8)


class LiteratureImportPayload(BaseModel):
    provider: str
    title: str
    abstract: str = ""
    year: int = 0
    venue: str = ""
    authors: list[str] = Field(default_factory=list)
    doi: str = ""
    url: str = ""
    pdf_url: str = ""
    external_id: str = ""
    citation_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class GroundedSearchPayload(BaseModel):
    query: str = Field(min_length=2)
    limit: int = Field(default=6, ge=1, le=12)


class RunControlPayload(BaseModel):
    comment: str = ""
    decided_by: str = ""


class PaperMetadataPayload(BaseModel):
    title: str | None = None
    url: str | None = None
    notes: str | None = None
    abstract: str | None = None
    doi: str | None = None
    venue: str | None = None
    year: int | None = None
    authors_json: list[str] | str | None = None
    citation_key: str | None = None
    source_provider: str | None = None
    external_id: str | None = None
    actor: str = ""


app = FastAPI(title="Auto Research Pro Max", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    init_db()


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "stage_count": STAGE_COUNT}


@app.get("/api/runtime")
async def runtime_info() -> dict[str, Any]:
    runtime_meta = Path(__file__).resolve().parents[2] / ".runtime" / "server-meta.json"
    if runtime_meta.exists():
        try:
            with runtime_meta.open() as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "host": "127.0.0.1",
        "port": 8000,
        "mode": "local",
        "local_url": "http://127.0.0.1:8000",
        "lan_urls": [],
    }


@app.get("/api/stages")
async def stages_endpoint() -> dict[str, Any]:
    return {"planning_gate": True, "stages": stage_catalog()}


@app.get("/api/project-templates")
async def project_templates() -> dict[str, Any]:
    return {"templates": list_project_templates()}


@app.get("/api/settings")
async def settings_get() -> dict[str, Any]:
    return get_settings()


@app.put("/api/settings")
async def settings_put(payload: SettingsPayload) -> dict[str, Any]:
    return save_settings(payload.model_dump())


@app.post("/api/settings/test")
async def settings_test(payload: SettingsPayload) -> dict[str, Any]:
    try:
        return test_connection(payload.model_dump())
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


@app.get("/api/projects")
async def projects_list(
    search: str = "",
    include_archived: bool = True,
) -> dict[str, Any]:
    projects = list_projects(search=search, include_archived=include_archived)
    return {"projects": projects, "total": len(projects), "search": search}


@app.post("/api/projects")
async def projects_create(payload: ProjectPayload) -> dict[str, Any]:
    project = create_project(payload.model_dump())
    return {"project": project}


@app.get("/api/projects/{project_id}")
async def projects_get(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "project": project,
        "papers": list_papers(project_id),
        "plan": get_plan(project_id),
        "latest_run": get_latest_run(project_id),
    }


@app.put("/api/projects/{project_id}/execution-config")
async def projects_update_execution_config(project_id: str, payload: ProjectExecutionPayload) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    updated = update_project_execution_config(project_id, payload.model_dump())
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": updated}


class ProjectDuplicatePayload(BaseModel):
    title: str = ""


class StageConfigPayload(BaseModel):
    disabled_stage_keys: list[str] = Field(default_factory=list)


@app.put("/api/projects/{project_id}/stage-config")
async def projects_update_stage_config(project_id: str, payload: StageConfigPayload) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    updated = update_project_disabled_stages(project_id, payload.disabled_stage_keys)
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": updated}


@app.post("/api/projects/{project_id}/duplicate")
async def projects_duplicate(project_id: str, payload: ProjectDuplicatePayload | None = None) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    duplicated = duplicate_project(project_id, (payload or ProjectDuplicatePayload()).title)
    if duplicated is None:
        raise HTTPException(status_code=500, detail="Failed to duplicate project")
    return {"project": duplicated, "projects": list_projects()}


@app.post("/api/projects/{project_id}/archive")
async def projects_archive(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    updated = set_project_archived(project_id, True)
    return {"project": updated, "projects": list_projects()}


@app.post("/api/projects/{project_id}/unarchive")
async def projects_unarchive(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    updated = set_project_archived(project_id, False)
    return {"project": updated, "projects": list_projects()}


@app.delete("/api/projects/{project_id}")
async def projects_delete(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    deleted = delete_project(project_id)
    return {"deleted": deleted, "projects": list_projects()}


@app.post("/api/projects/{project_id}/papers/upload")
async def papers_upload(
    project_id: str,
    file: UploadFile = File(...),
    notes: str = Form(default=""),
) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    paper = await save_uploaded_paper(project_id, file, notes, get_settings())
    return {"paper": paper, "papers": list_papers(project_id)}


@app.post("/api/projects/{project_id}/papers/url")
async def papers_url(project_id: str, payload: RemotePaperPayload) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    paper = await save_remote_paper(project_id, payload.url, payload.title, payload.notes, get_settings())
    return {"paper": paper, "papers": list_papers(project_id)}


class ReindexPayload(BaseModel):
    force: bool = False


@app.post("/api/projects/{project_id}/reindex")
async def projects_reindex(project_id: str, payload: ReindexPayload | None = None) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    options = (payload or ReindexPayload()).model_dump()
    return reindex_project_papers(project_id, get_settings(), force=options.get("force", False))


@app.get("/api/projects/{project_id}/citation-graph")
async def projects_citation_graph(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    papers = list_papers(project_id)
    return build_citation_graph(papers)


@app.post("/api/projects/{project_id}/papers/retrieve")
async def papers_retrieve(project_id: str, payload: GroundedSearchPayload) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return retrieve_grounded_snippets(project_id, payload.query, get_settings(), limit=payload.limit)


@app.post("/api/projects/{project_id}/literature/search")
async def literature_search(project_id: str, payload: LiteratureSearchPayload) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return search_literature(payload.query, limit_per_provider=payload.limit_per_provider)


@app.put("/api/projects/{project_id}/papers/{paper_id}")
async def papers_update_metadata(
    project_id: str,
    paper_id: str,
    payload: PaperMetadataPayload,
) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    paper = get_paper(paper_id)
    if paper is None or paper.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="Paper not found in project")
    body = payload.model_dump(exclude_unset=True, exclude_none=True)
    try:
        updated = update_paper_metadata(project_id, paper_id, body, get_settings())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"paper": updated, "papers": list_papers(project_id)}


@app.post("/api/projects/{project_id}/papers/{paper_id}/refresh")
async def papers_refresh_metadata(project_id: str, paper_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    paper = get_paper(paper_id)
    if paper is None or paper.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="Paper not found in project")
    try:
        refreshed = await refresh_paper_metadata(project_id, paper_id, get_settings())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"paper": refreshed, "papers": list_papers(project_id)}


@app.post("/api/projects/{project_id}/papers/{paper_id}/ocr")
async def papers_run_ocr(project_id: str, paper_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    paper = get_paper(paper_id)
    if paper is None or paper.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="Paper not found in project")
    try:
        refreshed = reocr_paper(project_id, paper_id, get_settings())
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"paper": refreshed, "papers": list_papers(project_id)}


@app.delete("/api/projects/{project_id}/papers/{paper_id}")
async def papers_delete(project_id: str, paper_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    paper = get_paper(paper_id)
    if paper is None or paper.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="Paper not found in project")
    deleted = delete_paper(paper_id)
    return {"deleted": deleted, "papers": list_papers(project_id)}


@app.post("/api/projects/{project_id}/papers/import")
async def papers_import(project_id: str, payload: LiteratureImportPayload) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    paper = await save_literature_result(
        project_id,
        {
            "provider": payload.provider,
            "title": payload.title,
            "abstract": payload.abstract,
            "year": payload.year,
            "venue": payload.venue,
            "authors": payload.authors,
            "doi": payload.doi,
            "url": payload.url,
            "pdf_url": payload.pdf_url,
            "external_id": payload.external_id,
            "citation_count": payload.citation_count,
            "metadata": payload.metadata,
        },
        payload.notes,
        get_settings(),
    )
    return {"paper": paper, "papers": list_papers(project_id)}


@app.post("/api/projects/{project_id}/plan/generate")
async def plan_generate(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    papers = list_papers(project_id)
    catalog = stage_catalog()
    plan_markdown = generate_plan_markdown(project, papers, get_settings(), catalog)
    plan = save_plan(
        project_id,
        plan_markdown,
        "ready",
        metadata_json={"stage_count": len(catalog), "approval_gates": [item["key"] for item in catalog if item.get("approval_gate")]},
    )
    return {"plan": plan}


@app.post("/api/projects/{project_id}/plan/approve")
async def plan_approve(project_id: str) -> dict[str, Any]:
    plan = approve_plan(project_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"plan": plan}


@app.get("/api/projects/{project_id}/runs")
async def projects_runs(project_id: str, limit: int = 50) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    runs = list_project_runs(project_id, limit=limit)
    return {"runs": runs}


@app.get("/api/runs/{run_id}/diff")
async def run_diff(run_id: str, against: str) -> dict[str, Any]:
    run_a = get_run(run_id)
    run_b = get_run(against)
    if run_a is None or run_b is None:
        raise HTTPException(status_code=404, detail="Run(s) not found")
    if run_a["project_id"] != run_b["project_id"]:
        raise HTTPException(status_code=400, detail="Runs belong to different projects")
    diffs = diff_runs(list_run_stages(run_a["id"]), list_run_stages(run_b["id"]))
    return {"run_a": run_a, "run_b": run_b, "stage_diffs": diffs}


@app.post("/api/projects/{project_id}/runs/start")
async def run_start(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    plan = get_plan(project_id)
    if plan is None or plan["status"] != "approved":
        raise HTTPException(status_code=400, detail="Plan must be approved before starting a run")
    run = start_run(project_id, get_settings())
    return {"run": run, "stages": list_run_stages(run["id"])}


@app.get("/api/runs/{run_id}")
async def run_get(run_id: str) -> dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run": run,
        "stages": list_run_stages(run_id),
        "audit_events": list_run_audit_events(run_id),
    }


@app.get("/api/runs/{run_id}/audit")
async def run_audit(run_id: str) -> dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "audit_events": list_run_audit_events(run_id)}


def _controlled_run_response(run_id: str, updated_run: dict[str, Any] | None) -> dict[str, Any]:
    if updated_run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run": updated_run,
        "stages": list_run_stages(run_id),
        "audit_events": list_run_audit_events(run_id),
    }


@app.post("/api/runs/{run_id}/control/pause")
async def run_pause(run_id: str, payload: RunControlPayload | None = None) -> dict[str, Any]:
    args = (payload or RunControlPayload()).model_dump()
    return _controlled_run_response(run_id, pause_run(run_id, **args))


@app.post("/api/runs/{run_id}/control/resume")
async def run_resume(run_id: str, payload: RunControlPayload | None = None) -> dict[str, Any]:
    args = (payload or RunControlPayload()).model_dump()
    return _controlled_run_response(run_id, resume_run(run_id, **args))


@app.post("/api/runs/{run_id}/control/reject")
async def run_reject(run_id: str, payload: RunControlPayload | None = None) -> dict[str, Any]:
    args = (payload or RunControlPayload()).model_dump()
    return _controlled_run_response(run_id, reject_run(run_id, **args))


@app.post("/api/runs/{run_id}/control/rollback")
async def run_rollback(run_id: str, payload: RunControlPayload | None = None) -> dict[str, Any]:
    args = (payload or RunControlPayload()).model_dump()
    return _controlled_run_response(run_id, rollback_run(run_id, **args))


@app.post("/api/runs/{run_id}/stages/{stage_index}/retry")
async def run_retry_stage(run_id: str, stage_index: int) -> dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        updated = retry_stage(run_id, stage_index, get_settings())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _controlled_run_response(run_id, updated)


@app.websocket("/ws/runs/{run_id}")
async def run_events(run_id: str, websocket: WebSocket) -> None:
    await event_hub.connect(run_id, websocket)
    try:
        run = get_run(run_id)
        if run is not None:
            await websocket.send_json(
                {
                    "type": "run_update",
                    "run": run,
                    "stages": list_run_stages(run_id),
                    "audit_events": list_run_audit_events(run_id),
                }
            )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_hub.disconnect(run_id, websocket)


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
app.mount("/media", StaticFiles(directory=str(DATA_DIR)), name="media")
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
