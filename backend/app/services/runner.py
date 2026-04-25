from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Literal


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _accumulate_run_cost(
    run_id: str,
    stage_index: int,
    stage_key: str,
    usage: dict[str, Any],
) -> None:
    run = get_run(run_id)
    if run is None:
        return
    metadata = dict(run.get("metadata_json") or {})
    cost_summary = dict(metadata.get("cost_summary") or {})
    totals = dict(cost_summary.get("totals") or {})
    per_stage = list(cost_summary.get("per_stage") or [])
    per_model = dict(cost_summary.get("per_model") or {})

    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    cost_usd = float(usage.get("cost_usd") or 0.0)
    model = str(usage.get("model") or "")

    totals["input_tokens"] = int(totals.get("input_tokens") or 0) + input_tokens
    totals["output_tokens"] = int(totals.get("output_tokens") or 0) + output_tokens
    totals["total_tokens"] = int(totals.get("total_tokens") or 0) + total_tokens
    totals["cost_usd"] = round(float(totals.get("cost_usd") or 0.0) + cost_usd, 6)

    per_stage.append(
        {
            "stage_index": stage_index,
            "stage_key": stage_key,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
        }
    )
    per_stage = per_stage[-200:]

    if model:
        existing = dict(per_model.get(model) or {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0})
        existing["input_tokens"] = int(existing.get("input_tokens") or 0) + input_tokens
        existing["output_tokens"] = int(existing.get("output_tokens") or 0) + output_tokens
        existing["cost_usd"] = round(float(existing.get("cost_usd") or 0.0) + cost_usd, 6)
        existing["calls"] = int(existing.get("calls") or 0) + 1
        per_model[model] = existing

    cost_summary.update(
        {
            "totals": totals,
            "per_stage": per_stage,
            "per_model": per_model,
            "last_updated": _now_iso(),
        }
    )
    metadata["cost_summary"] = cost_summary
    update_run(run_id, metadata_json=metadata)

from ..db import (
    append_run_audit_event,
    append_run_event,
    create_run,
    get_latest_run,
    get_plan,
    get_project,
    get_run,
    get_run_stage,
    list_papers,
    list_run_audit_events,
    list_run_stages,
    reset_run_from_stage,
    set_project_run_complete,
    update_project_status,
    update_run,
    update_run_status,
    update_stage,
    update_stage_gate_decision,
)
from ..stages import PIPELINE_STAGES, STAGE_COUNT, StageDefinition, stage_by_index
from .events import event_hub
from .llm import generate_stage_result
from .retrieval import search_literature_for_project
from .sandbox import run_experiment_sandbox
from .validation import validate_stage_payload
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
            "audit_events": list_run_audit_events(run_id),
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
    expected_artifacts = result.get("expected_artifacts") or []
    matched_artifacts = result.get("matched_artifacts") or []
    lines = [
        "# Experiment Sandbox",
        "",
        f"## Status\n- {result.get('status')}",
        f"- Return code: {result.get('returncode')}",
        f"- Duration seconds: {result.get('duration_seconds')}",
        "",
        "## Repository",
        f"- Source type: {result.get('repo_source_type') or 'not_configured'}",
        f"- Local path: {result.get('repo_path') or 'n/a'}",
        f"- Git URL: {result.get('repo_url') or 'n/a'}",
        f"- Git ref: {result.get('repo_ref') or 'n/a'}",
        f"- Workdir: {result.get('sandbox_workdir') or '.'}",
        "",
        "## Commands",
        f"- Setup: {result.get('setup_command') or 'none'}",
        f"- Run: {result.get('run_command') or 'none'}",
        "",
        "## Policy",
        f"- Docker image: {result.get('docker_image')}",
        f"- Base image: {result.get('base_image')}",
        f"- Timeout seconds: {result.get('timeout_seconds')}",
        f"- Allowed packages: {', '.join(result.get('allowed_packages') or []) or 'none'}",
        f"- Blocked packages: {', '.join(result.get('blocked_packages') or []) or 'none'}",
        "",
        "## Expected Artifacts",
    ]
    for item in expected_artifacts:
        lines.append(f"- {item}")
    if not expected_artifacts:
        lines.append("- none")
    lines.extend([
        "",
        "## Matched Artifacts",
    ])
    for item in matched_artifacts:
        lines.append(f"- {item}")
    if not matched_artifacts:
        lines.append("- none")
    lines.extend([
        "",
        "## Captured Artifacts",
    ])
    for item in manifest:
        url = item.get("url") or ""
        suffix = f" -> {url}" if url else ""
        lines.append(f"- {item['path']} ({item['size_bytes']} bytes){suffix}")
    stdout = result.get("stdout") or ""
    if stdout:
        lines.extend(["", "## stdout", "```text", stdout[:2400], "```"])
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
                    "repo_source_type": sandbox_result.get("repo_source_type"),
                    "repo_path": sandbox_result.get("repo_path"),
                    "repo_url": sandbox_result.get("repo_url"),
                    "repo_ref": sandbox_result.get("repo_ref"),
                    "sandbox_workdir": sandbox_result.get("sandbox_workdir"),
                    "setup_command": sandbox_result.get("setup_command"),
                    "run_command": sandbox_result.get("run_command"),
                    "expected_artifacts": sandbox_result.get("expected_artifacts") or [],
                    "requested_packages": sandbox_result.get("requested_packages") or [],
                    "allowed_packages": sandbox_result.get("allowed_packages") or [],
                    "blocked_packages": sandbox_result.get("blocked_packages") or [],
                    "timeout_seconds": sandbox_result.get("timeout_seconds"),
                },
                "sandbox_result": {
                    "status": sandbox_result.get("status"),
                    "returncode": sandbox_result.get("returncode"),
                    "duration_seconds": sandbox_result.get("duration_seconds"),
                    "docker_image": sandbox_result.get("docker_image"),
                    "base_image": sandbox_result.get("base_image"),
                    "matched_artifacts": sandbox_result.get("matched_artifacts") or [],
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
            stage_record = get_run_stage(run_id, stage.index) or {}
            decided_by = stage_record.get("gate_decided_by") or ""
            gate_comment = stage_record.get("gate_comment") or ""
            note_suffix = f" Comment: {gate_comment}" if gate_comment else ""
            update_stage(
                run_id,
                stage.index,
                gate_status="approved",
                notes=f"{stage.label} gate approved. Workflow resumed.{note_suffix}",
            )
            update_run(
                run_id,
                status="running",
                pending_gate_index=0,
                pending_gate_key="",
                pending_gate_state="",
                error="",
            )
            append_run_event(
                run_id,
                {
                    "action": "resume",
                    "stage_index": stage.index,
                    "decided_by": decided_by,
                    "comment": gate_comment,
                },
            )
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
                run_record = get_run(run_id) or run
                final_index = int(run_record.get("total_stages") or STAGE_COUNT)
                update_run(run_id, status="completed", current_stage_index=final_index, finished=True)
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

            stage_metadata = dict(stage_record.get("metadata_json") or {})
            attempts = list(stage_metadata.get("attempts") or [])
            policy = stage.retry_policy
            stage_metadata["retry_policy"] = {
                "max_attempts": policy.max_attempts,
                "base_delay_seconds": policy.base_delay_seconds,
                "backoff_factor": policy.backoff_factor,
                "retry_on_validation": policy.retry_on_validation,
                "retry_on_exception": policy.retry_on_exception,
            }

            payload: dict[str, Any] | None = None
            validation: dict[str, Any] | None = None
            failure_reason = ""
            attempt_succeeded = False

            for attempt in range(1, max(policy.max_attempts, 1) + 1):
                if attempt > 1:
                    delay = policy.delay_for(attempt)
                    if delay:
                        await asyncio.sleep(delay)
                attempt_record: dict[str, Any] = {
                    "attempt": attempt,
                    "started_at": _now_iso(),
                    "status": "running",
                }
                attempts.append(attempt_record)
                stage_metadata["attempts"] = attempts
                update_stage(
                    run_id,
                    stage.index,
                    status="running",
                    notes=(
                        f"{stage.label} is in progress (attempt {attempt}/{policy.max_attempts})."
                        if policy.max_attempts > 1
                        else f"{stage.label} is in progress."
                    ),
                    error="",
                    metadata_json=stage_metadata,
                    started=True,
                )
                update_run(run_id, status="running", current_stage_index=max(stage.index - 1, 0), error="")
                append_run_event(
                    run_id,
                    {
                        "action": "stage_start",
                        "stage_index": stage.index,
                        "stage_key": stage.key,
                        "attempt": attempt,
                        "max_attempts": policy.max_attempts,
                    },
                )
                await _emit(run_id)

                prior_outputs = _prior_outputs(run_id, stage.index)
                try:
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
                except Exception as exc:
                    attempt_record["status"] = "errored"
                    attempt_record["error"] = str(exc)
                    attempt_record["completed_at"] = _now_iso()
                    failure_reason = f"{stage.label} raised: {exc}"
                    if policy.retry_on_exception and attempt < policy.max_attempts:
                        append_run_event(
                            run_id,
                            {
                                "action": "stage_retry",
                                "stage_index": stage.index,
                                "stage_key": stage.key,
                                "attempt": attempt,
                                "reason": "exception",
                                "error": str(exc),
                            },
                        )
                        continue
                    raise

                validation = validate_stage_payload(stage, payload)
                stage_metadata["validation"] = validation
                if validation["ok"]:
                    attempt_record["status"] = "succeeded"
                    attempt_record["completed_at"] = _now_iso()
                    attempt_succeeded = True
                    break

                error_message = "Stage validation failed: " + "; ".join(validation["errors"])
                attempt_record["status"] = "validation_failed"
                attempt_record["error"] = error_message
                attempt_record["completed_at"] = _now_iso()
                failure_reason = error_message
                if policy.retry_on_validation and attempt < policy.max_attempts:
                    append_run_event(
                        run_id,
                        {
                            "action": "stage_retry",
                            "stage_index": stage.index,
                            "stage_key": stage.key,
                            "attempt": attempt,
                            "reason": "validation",
                            "errors": validation["errors"],
                        },
                    )
                    continue
                break

            stage_metadata["attempts"] = attempts

            if not attempt_succeeded:
                update_stage(
                    run_id,
                    stage.index,
                    status="failed",
                    notes=(payload or {}).get("notes") or failure_reason or "Stage failed.",
                    content_md=(payload or {}).get("content_md") or "",
                    artifact_json=(payload or {}).get("artifacts") or {},
                    metadata_json=stage_metadata,
                    error=failure_reason or "Stage failed",
                )
                update_run_status(run_id, "failed", stage.index, failure_reason or "Stage failed")
                set_project_run_complete(run["project_id"], "failed")
                append_run_event(
                    run_id,
                    {
                        "action": "stage_validation_failed" if validation and not validation["ok"] else "stage_failed",
                        "stage_index": stage.index,
                        "stage_key": stage.key,
                        "errors": (validation or {}).get("errors") or [failure_reason],
                        "attempts": len(attempts),
                    },
                )
                await _emit(run_id)
                return

            usage = (payload or {}).get("usage") or {}
            if usage:
                stage_metadata["usage"] = usage
                _accumulate_run_cost(run_id, stage.index, stage.key, usage)

            update_stage(
                run_id,
                stage.index,
                status="completed",
                notes=(payload or {}).get("notes", ""),
                content_md=(payload or {}).get("content_md", ""),
                artifact_json=(payload or {}).get("artifacts") or {},
                metadata_json=stage_metadata,
                completed=True,
                gate_status="pending" if stage.approval_gate else "",
            )
            update_run(run_id, status="running", current_stage_index=stage.index, error="")
            append_run_event(
                run_id,
                {
                    "action": "stage_complete",
                    "stage_index": stage.index,
                    "stage_key": stage.key,
                    "validation_warnings": validation.get("warnings") or [],
                },
            )
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


def retry_stage(run_id: str, stage_index: int, settings: dict[str, Any]) -> dict[str, Any] | None:
    run = get_run(run_id)
    if run is None:
        return None
    stage_record = get_run_stage(run_id, stage_index)
    if stage_record is None:
        raise LookupError(f"Run {run_id} has no stage {stage_index}")

    metadata = dict(stage_record.get("metadata_json") or {})
    attempts = list(metadata.get("attempts") or [])
    attempts.append(
        {
            "attempt": len(attempts) + 1,
            "status": "manual_retry",
            "queued_at": _now_iso(),
        }
    )
    metadata["attempts"] = attempts
    metadata["manual_retry_count"] = int(metadata.get("manual_retry_count") or 0) + 1

    update_stage(
        run_id,
        stage_index,
        status="pending",
        notes=f"Manual retry queued for stage {stage_index}.",
        content_md="",
        artifact_json={},
        gate_status="",
        error="",
        metadata_json=metadata,
        reset_timestamps=True,
    )
    update_run(
        run_id,
        status="running",
        current_stage_index=max(stage_index - 1, 0),
        pending_gate_index=0,
        pending_gate_key="",
        pending_gate_state="",
        error="",
        finished=False,
    )
    update_project_status(run["project_id"], "running")
    append_run_event(run_id, {"action": "manual_retry", "stage_index": stage_index})

    if run_id not in RUN_TASKS or RUN_TASKS[run_id].done():
        RUN_TASKS[run_id] = asyncio.create_task(execute_run(run_id, settings))
    else:
        _wake_run(run_id)
    return get_run(run_id)


def _stage_context_for_gate(run_id: str, run: dict[str, Any]) -> tuple[int, str, str]:
    pending_index = int(run.get("pending_gate_index") or 0)
    if not pending_index:
        return 0, "", ""
    stage_record = get_run_stage(run_id, pending_index) or {}
    return (
        pending_index,
        str(stage_record.get("stage_key") or run.get("pending_gate_key") or ""),
        str(stage_record.get("approval_label") or ""),
    )


def pause_run(run_id: str, *, comment: str = "", decided_by: str = "") -> dict[str, Any] | None:
    run = get_run(run_id)
    if run is None or run["status"] in {"completed", "failed"}:
        return run
    update_run(run_id, status="paused")
    update_project_status(run["project_id"], "paused")
    stage_index = int(run.get("current_stage_index") or 0)
    stage_record = get_run_stage(run_id, stage_index) if stage_index else None
    stage_key = (stage_record or {}).get("stage_key") if stage_record else ""
    append_run_event(
        run_id,
        {
            "action": "pause",
            "stage_index": stage_index,
            "decided_by": decided_by or "",
            "comment": comment or "",
        },
    )
    append_run_audit_event(
        run_id,
        action="pause",
        stage_index=stage_index,
        stage_key=stage_key or "",
        decided_by=decided_by,
        comment=comment,
    )
    _wake_run(run_id)
    return get_run(run_id)


def resume_run(run_id: str, *, comment: str = "", decided_by: str = "") -> dict[str, Any] | None:
    run = get_run(run_id)
    if run is None or run["status"] in {"completed", "failed"}:
        return run
    pending_index, gate_key, _ = _stage_context_for_gate(run_id, run)
    audit_action = "resume"
    if pending_index:
        update_stage_gate_decision(run_id, pending_index, decided_by=decided_by, comment=comment)
        update_run(run_id, status="running", pending_gate_state="approved")
        update_stage(run_id, pending_index, gate_status="approved")
        audit_action = "approve"
    else:
        update_run(run_id, status="running")
    update_project_status(run["project_id"], "running")
    stage_index = pending_index or int(run.get("current_stage_index") or 0)
    append_run_event(
        run_id,
        {
            "action": audit_action,
            "stage_index": stage_index,
            "decided_by": decided_by or "",
            "comment": comment or "",
        },
    )
    append_run_audit_event(
        run_id,
        action=audit_action,
        stage_index=stage_index,
        stage_key=gate_key,
        gate_key=gate_key if pending_index else "",
        decided_by=decided_by,
        comment=comment,
    )
    _wake_run(run_id)
    return get_run(run_id)


def reject_run(run_id: str, *, comment: str = "", decided_by: str = "") -> dict[str, Any] | None:
    run = get_run(run_id)
    if run is None or not run.get("pending_gate_index"):
        return run
    pending_index, gate_key, _ = _stage_context_for_gate(run_id, run)
    note_suffix = f" Comment: {comment}" if comment else ""
    update_stage_gate_decision(run_id, pending_index, decided_by=decided_by, comment=comment)
    update_run(run_id, status="awaiting_approval", pending_gate_state="rejected")
    update_stage(
        run_id,
        pending_index,
        gate_status="rejected",
        notes=f"Approval gate rejected. Roll back or resume after review.{note_suffix}",
    )
    update_project_status(run["project_id"], "awaiting_approval")
    append_run_event(
        run_id,
        {
            "action": "reject",
            "stage_index": pending_index,
            "decided_by": decided_by or "",
            "comment": comment or "",
        },
    )
    append_run_audit_event(
        run_id,
        action="reject",
        stage_index=pending_index,
        stage_key=gate_key,
        gate_key=gate_key,
        decided_by=decided_by,
        comment=comment,
    )
    _wake_run(run_id)
    return get_run(run_id)


def rollback_run(run_id: str, *, comment: str = "", decided_by: str = "") -> dict[str, Any] | None:
    run = get_run(run_id)
    if run is None or not run.get("pending_gate_index"):
        return run
    pending_index, gate_key, _ = _stage_context_for_gate(run_id, run)
    stage_record = get_run_stage(run_id, pending_index)
    rollback_to = int((stage_record or {}).get("rollback_target_index") or max(pending_index - 1, 1))
    update_stage_gate_decision(run_id, pending_index, decided_by=decided_by, comment=comment)
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
    append_run_event(
        run_id,
        {
            "action": "rollback",
            "from_stage_index": pending_index,
            "to_stage_index": rollback_to,
            "decided_by": decided_by or "",
            "comment": comment or "",
        },
    )
    append_run_audit_event(
        run_id,
        action="rollback",
        stage_index=pending_index,
        stage_key=gate_key,
        gate_key=gate_key,
        decided_by=decided_by,
        comment=comment,
        metadata={"rollback_to_stage_index": rollback_to},
    )
    _wake_run(run_id)
    return get_run(run_id)
