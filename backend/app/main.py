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
    get_latest_run,
    get_plan,
    get_project,
    get_run,
    init_db,
    list_papers,
    list_projects,
    list_run_stages,
    save_plan,
    save_settings,
    create_project,
    get_settings,
    update_project_execution_config,
)
from .services.events import event_hub
from .services.grounding import retrieve_grounded_snippets
from .services.llm import generate_plan_markdown, test_connection
from .services.papers import save_literature_result, save_remote_paper, save_uploaded_paper
from .services.retrieval import search_literature
from .services.runner import pause_run, reject_run, resume_run, rollback_run, start_run
from .stages import STAGE_COUNT, stage_catalog


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
async def projects_list() -> dict[str, Any]:
    return {"projects": list_projects()}


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
    return {"run": run, "stages": list_run_stages(run_id)}


def _controlled_run_response(run_id: str, updated_run: dict[str, Any] | None) -> dict[str, Any]:
    if updated_run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run": updated_run, "stages": list_run_stages(run_id)}


@app.post("/api/runs/{run_id}/control/pause")
async def run_pause(run_id: str) -> dict[str, Any]:
    return _controlled_run_response(run_id, pause_run(run_id))


@app.post("/api/runs/{run_id}/control/resume")
async def run_resume(run_id: str) -> dict[str, Any]:
    return _controlled_run_response(run_id, resume_run(run_id))


@app.post("/api/runs/{run_id}/control/reject")
async def run_reject(run_id: str) -> dict[str, Any]:
    return _controlled_run_response(run_id, reject_run(run_id))


@app.post("/api/runs/{run_id}/control/rollback")
async def run_rollback(run_id: str) -> dict[str, Any]:
    return _controlled_run_response(run_id, rollback_run(run_id))


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
