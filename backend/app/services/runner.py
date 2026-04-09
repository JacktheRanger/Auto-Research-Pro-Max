from __future__ import annotations

import asyncio
from typing import Any, Literal

from ..db import (
    append_run_event,
    create_run,
    get_latest_run,
    get_plan,
    get_project,
    get_run,
    get_run_stage,
    list_papers,
    list_run_stages,
    reset_run_from_stage,
    set_project_run_complete,
    update_project_status,
    update_run,
    update_run_status,
    update_stage,
)
from ..stages import PIPELINE_STAGES, STAGE_COUNT, StageDefinition, stage_by_index
from .events import event_hub
from .llm import generate_stage_result
from .retrieval import search_literature_for_project
from .sandbox import run_experiment_sandbox
from .writing import (
    build_delivery_package_payload,
    build_paper_export_payload,
    build_peer_review_payload,
)


RUN_TASKS: dict[str, asyncio.Task[Any]] = {}
RUN_WAKEUPS: dict[str, asyncio.Event] = {}


def _wake_run(run_id: str) -> None:
    event = RUN_WAKEUPS.setdefault(run_id, asyncio.Event())
    event.set()


async def _wait_for_wakeup(run_id: str) -> None:
    event = RUN_WAKEUPS.setdefault(run_id, asyncio.Event())
    await event.wait()
    event.clear()


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


def _prior_outputs(run_id: str, stage_index: int) -> list[dict[str, Any]]:
    return [
        item
        for item in list_run_stages(run_id)
        if (item.get("stage_index") or 0) < stage_index and item.get("status") == "completed"
    ]


def _format_retrieval_markdown(result: dict[str, Any]) -> str:
    lines = ["# Literature Retrieval", "", "## Queries"]
    for query in result.get("queries") or []:
        lines.append(f"- {query}")
    lines.extend(["", "## Recommended Reads"])
    for item in result.get("recommended_reads") or []:
        lines.append(
            f"- {item['title']} ({item.get('year') or 'n/a'}, {item.get('provider')})"
            f" | venue: {item.get('venue') or 'n/a'} | doi: {item.get('doi') or 'n/a'}"
        )
    lines.extend(["", "## Provider Coverage"])
    for query_result in result.get("per_query") or []:
        lines.append(f"### {query_result['query']}")
        if query_result.get("errors"):
            for provider, error in query_result["errors"].items():
                lines.append(f"- {provider}: error -> {error}")
        for provider, provider_items in (query_result.get("provider_results") or {}).items():
            lines.append(f"- {provider}: {len(provider_items)} hits")
    return "\n".join(lines).strip()


def _format_sandbox_markdown(result: dict[str, Any]) -> str:
    manifest = result.get("artifact_manifest") or []
    lines = [
        "# Experiment Sandbox",
        "",
        f"## Status\n- {result.get('status')}",
        "",
        "## Policy",
        f"- Docker image: {result.get('docker_image')}",
        f"- Timeout seconds: {result.get('timeout_seconds')}",
        f"- Allowed packages: {', '.join(result.get('allowed_packages') or []) or 'none'}",
        f"- Blocked packages: {', '.join(result.get('blocked_packages') or []) or 'none'}",
        "",
        "## Captured Artifacts",
    ]
    for item in manifest:
        lines.append(f"- {item['path']} ({item['size_bytes']} bytes)")
    stderr = result.get("stderr") or ""
    if stderr:
        lines.extend(["", "## stderr", "```text", stderr[:2400], "```"])
    return "\n".join(lines).strip()


def _execute_stage_payload(
    run_id: str,
    stage: StageDefinition,
    project: dict[str, Any],
    plan_markdown: str,
    papers: list[dict[str, Any]],
    prior_outputs: list[dict[str, Any]],
    settings: dict[str, Any],
) -> dict[str, Any]:
    if stage.key == "literature_retrieval":
        retrieval = search_literature_for_project(project)
        return {
            "content_md": _format_retrieval_markdown(retrieval),
            "artifacts": {
                "queries": retrieval.get("queries") or [],
                "provider_results": retrieval.get("per_query") or [],
                "recommended_reads": retrieval.get("recommended_reads") or [],
            },
            "notes": "Completed with live literature adapters.",
        }
    if stage.key == "experiment_sandbox":
        sandbox_result = run_experiment_sandbox(run_id, stage.index, project, prior_outputs)
        return {
            "content_md": _format_sandbox_markdown(sandbox_result),
            "artifacts": {
                "sandbox_request": {
                    "requested_packages": sandbox_result.get("requested_packages") or [],
                    "timeout_seconds": sandbox_result.get("timeout_seconds"),
                },
                "sandbox_result": {
                    "status": sandbox_result.get("status"),
                    "returncode": sandbox_result.get("returncode"),
                    "stdout": sandbox_result.get("stdout", "")[:2000],
                    "stderr": sandbox_result.get("stderr", "")[:2000],
                },
                "artifact_manifest": sandbox_result.get("artifact_manifest") or [],
            },
            "notes": f"Sandbox finished with status: {sandbox_result.get('status')}.",
        }
    if stage.key == "paper_export":
        return build_paper_export_payload(run_id, project, papers, prior_outputs)
    if stage.key == "peer_review":
        return build_peer_review_payload(run_id, project, papers, prior_outputs)
    if stage.key == "delivery_package":
        return build_delivery_package_payload(run_id, project, plan_markdown, papers, prior_outputs)
    return generate_stage_result(stage, project, plan_markdown, papers, prior_outputs, settings)


async def _wait_until_runnable(run_id: str) -> Literal["continue", "missing"]:
    while True:
        run = get_run(run_id)
        if run is None:
            return "missing"
        if run["status"] != "paused":
            return "continue"
        await _emit(run_id)
        await _wait_for_wakeup(run_id)


async def _wait_for_gate_decision(run_id: str, stage: StageDefinition) -> Literal["approved", "rollback", "missing"]:
    while True:
        run = get_run(run_id)
        if run is None:
            return "missing"
        if run["status"] == "paused":
            await _wait_for_wakeup(run_id)
            continue
        gate_state = run.get("pending_gate_state") or ""
        if gate_state == "approved":
            update_stage(
                run_id,
                stage.index,
                gate_status="approved",
                notes=f"{stage.label} gate approved. Workflow resumed.",
            )
            update_run(
                run_id,
                status="running",
                pending_gate_index=0,
                pending_gate_key="",
                pending_gate_state="",
                error="",
            )
            append_run_event(run_id, {"action": "resume", "stage_index": stage.index})
            await _emit(run_id)
            return "approved"
        if run.get("current_stage_index", 0) < stage.index:
            return "rollback"
        await _wait_for_wakeup(run_id)


def _next_stage_index(run_id: str) -> int | None:
    for item in list_run_stages(run_id):
        if item.get("status") != "completed":
            return int(item["stage_index"])
    return None


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

    update_run(run_id, status="running", current_stage_index=run.get("current_stage_index", 0), error="", finished=False)
    update_project_status(run["project_id"], "running")
    await _emit(run_id)

    try:
        while True:
            state = await _wait_until_runnable(run_id)
            if state == "missing":
                return

            next_stage_index = _next_stage_index(run_id)
            if next_stage_index is None:
                update_run(run_id, status="completed", current_stage_index=STAGE_COUNT, finished=True)
                set_project_run_complete(run["project_id"], "completed")
                append_run_event(run_id, {"action": "completed"})
                await _emit(run_id)
                return

            stage = stage_by_index(next_stage_index)
            if stage is None:
                update_run_status(run_id, "failed", next_stage_index, f"Unknown stage index: {next_stage_index}")
                set_project_run_complete(run["project_id"], "failed")
                await _emit(run_id)
                return

            stage_record = get_run_stage(run_id, stage.index)
            if stage_record is None:
                update_run_status(run_id, "failed", stage.index, "Missing stage record.")
                set_project_run_complete(run["project_id"], "failed")
                await _emit(run_id)
                return
            if stage_record.get("status") == "completed":
                update_run(run_id, current_stage_index=stage.index)
                continue

            update_stage(
                run_id,
                stage.index,
                status="running",
                notes=f"{stage.label} is in progress.",
                error="",
                started=True,
            )
            update_run(run_id, status="running", current_stage_index=max(stage.index - 1, 0), error="")
            append_run_event(run_id, {"action": "stage_start", "stage_index": stage.index, "stage_key": stage.key})
            await _emit(run_id)

            prior_outputs = _prior_outputs(run_id, stage.index)
            payload = await asyncio.to_thread(
                _execute_stage_payload,
                run_id,
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
                notes=payload["notes"],
                content_md=payload["content_md"],
                artifact_json=payload.get("artifacts") or {},
                completed=True,
                gate_status="pending" if stage.approval_gate else "",
            )
            update_run(run_id, status="running", current_stage_index=stage.index, error="")
            append_run_event(run_id, {"action": "stage_complete", "stage_index": stage.index, "stage_key": stage.key})
            await _emit(run_id)

            if stage.approval_gate:
                update_stage(
                    run_id,
                    stage.index,
                    notes=f"{stage.label} completed and is waiting at {stage.approval_gate.label}.",
                    gate_status="pending",
                )
                update_run(
                    run_id,
                    status="awaiting_approval",
                    current_stage_index=stage.index,
                    pending_gate_index=stage.index,
                    pending_gate_key=stage.key,
                    pending_gate_state="pending",
                    error="",
                )
                update_project_status(run["project_id"], "awaiting_approval")
                append_run_event(
                    run_id,
                    {"action": "gate_wait", "stage_index": stage.index, "gate": stage.approval_gate.label},
                )
                await _emit(run_id)
                decision = await _wait_for_gate_decision(run_id, stage)
                if decision == "missing":
                    return
                if decision == "rollback":
                    update_project_status(run["project_id"], "paused")
                    await _emit(run_id)
                    continue
                update_project_status(run["project_id"], "running")
    except Exception as exc:
        failing_stage = get_run(run_id)
        current_index = (failing_stage or {}).get("current_stage_index", 0)
        if current_index:
            update_stage(
                run_id,
                current_index,
                status="failed",
                notes=f"Stage failed: {exc}",
                error=str(exc),
            )
        update_run_status(run_id, "failed", current_index, str(exc))
        set_project_run_complete(run["project_id"], "failed")
        append_run_event(run_id, {"action": "failed", "error": str(exc)})
        await _emit(run_id)
        raise
    finally:
        RUN_TASKS.pop(run_id, None)
        RUN_WAKEUPS.pop(run_id, None)


def start_run(project_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    latest_run = get_latest_run(project_id)
    if latest_run and latest_run["status"] in {"running", "paused", "awaiting_approval", "queued"}:
        return latest_run
    created = create_run(project_id)
    RUN_TASKS[created["id"]] = asyncio.create_task(execute_run(created["id"], settings))
    return created


def pause_run(run_id: str) -> dict[str, Any] | None:
    run = get_run(run_id)
    if run is None or run["status"] in {"completed", "failed"}:
        return run
    update_run(run_id, status="paused")
    update_project_status(run["project_id"], "paused")
    append_run_event(run_id, {"action": "pause", "stage_index": run.get("current_stage_index", 0)})
    _wake_run(run_id)
    return get_run(run_id)


def resume_run(run_id: str) -> dict[str, Any] | None:
    run = get_run(run_id)
    if run is None or run["status"] in {"completed", "failed"}:
        return run
    if run.get("pending_gate_index"):
        update_run(run_id, status="running", pending_gate_state="approved")
        stage_index = int(run["pending_gate_index"])
        update_stage(run_id, stage_index, gate_status="approved")
    else:
        update_run(run_id, status="running")
    update_project_status(run["project_id"], "running")
    append_run_event(run_id, {"action": "resume", "stage_index": run.get("current_stage_index", 0)})
    _wake_run(run_id)
    return get_run(run_id)


def reject_run(run_id: str) -> dict[str, Any] | None:
    run = get_run(run_id)
    if run is None or not run.get("pending_gate_index"):
        return run
    stage_index = int(run["pending_gate_index"])
    update_run(run_id, status="awaiting_approval", pending_gate_state="rejected")
    update_stage(
        run_id,
        stage_index,
        gate_status="rejected",
        notes="Approval gate rejected. Roll back or resume after review.",
    )
    update_project_status(run["project_id"], "awaiting_approval")
    append_run_event(run_id, {"action": "reject", "stage_index": stage_index})
    _wake_run(run_id)
    return get_run(run_id)


def rollback_run(run_id: str) -> dict[str, Any] | None:
    run = get_run(run_id)
    if run is None or not run.get("pending_gate_index"):
        return run
    stage_index = int(run["pending_gate_index"])
    stage_record = get_run_stage(run_id, stage_index)
    rollback_to = int((stage_record or {}).get("rollback_target_index") or max(stage_index - 1, 1))
    reset_run_from_stage(run_id, rollback_to)
    update_run(
        run_id,
        status="paused",
        current_stage_index=max(rollback_to - 1, 0),
        pending_gate_index=0,
        pending_gate_key="",
        pending_gate_state="",
        error="",
        finished=False,
    )
    update_project_status(run["project_id"], "paused")
    append_run_event(run_id, {"action": "rollback", "from_stage_index": stage_index, "to_stage_index": rollback_to})
    _wake_run(run_id)
    return get_run(run_id)
