from __future__ import annotations

import asyncio
from typing import Any

from .. import stages
from ..db import (
    approve_plan,
    create_run,
    get_latest_run,
    get_plan,
    get_project,
    get_run,
    list_papers,
    list_run_stages,
    set_project_run_complete,
    update_run_status,
    update_stage,
)
from .events import event_hub
from .llm import generate_stage_markdown


RUN_TASKS: dict[str, asyncio.Task[Any]] = {}


async def _emit(run_id: str) -> None:
    run = get_run(run_id)
    if run is None:
        return
    await event_hub.broadcast(
        run_id,
        {
            "type": "run_update",
            "run": run,
            "stages": list_run_stages(run_id),
        },
    )


async def execute_run(run_id: str, settings: dict[str, Any]) -> None:
    run = get_run(run_id)
    if run is None:
        return
    project = get_project(run["project_id"])
    plan = get_plan(run["project_id"])
    papers = list_papers(run["project_id"])
    if project is None or plan is None:
        update_run_status(run_id, "failed", 0, "Missing project or approved plan.")
        return

    update_run_status(run_id, "running", 0)
    await _emit(run_id)

    try:
        for stage in stages.V1_STAGES:
            update_stage(
                run_id,
                stage.index,
                status="running",
                notes=f"{stage.label} is in progress.",
                started=True,
            )
            update_run_status(run_id, "running", stage.index)
            await _emit(run_id)
            await asyncio.sleep(0.35)

            prior_outputs = [
                item for item in list_run_stages(run_id) if item["stage_index"] < stage.index
            ]
            content = await asyncio.to_thread(
                generate_stage_markdown,
                stage,
                project,
                plan["plan_markdown"],
                papers,
                prior_outputs,
                settings,
            )

            update_stage(
                run_id,
                stage.index,
                status="completed",
                notes=f"{stage.label} completed.",
                content_md=content,
                completed=True,
            )
            update_run_status(run_id, "running", stage.index)
            await _emit(run_id)

        update_run_status(run_id, "completed", stages.STAGE_COUNT)
        set_project_run_complete(run["project_id"], "completed")
        await _emit(run_id)
    except Exception as exc:
        update_run_status(run_id, "failed", run.get("current_stage_index", 0), str(exc))
        set_project_run_complete(run["project_id"], "failed")
        await _emit(run_id)
        raise
    finally:
        RUN_TASKS.pop(run_id, None)


def start_run(project_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    latest_run = get_latest_run(project_id)
    if latest_run and latest_run["status"] == "running":
        return latest_run
    created = create_run(project_id)
    RUN_TASKS[created["id"]] = asyncio.create_task(execute_run(created["id"], settings))
    return created

