from __future__ import annotations

from pathlib import Path
from typing import Any

from ..stages import StageDefinition

GENERIC_STAGE_HEADINGS = [
    "## Stage Focus",
    "## Inputs Used",
    "## Decisions",
    "## Output",
    "## Risks",
    "## Artifact Checklist",
]

SPECIAL_STAGE_HEADINGS: dict[str, list[str]] = {
    "literature_retrieval": ["## Queries", "## Recommended Reads", "## Provider Coverage"],
    "experiment_sandbox": ["## Status", "## Repository", "## Commands", "## Captured Artifacts"],
    "paper_export": ["## Export Notes"],
    "peer_review": ["## Rubrics", "## Findings", "## Fix Suggestions"],
    "delivery_package": ["## Bundle Contents", "## Recommended Next Steps"],
}


def _expected_headings(stage: StageDefinition) -> list[str]:
    return SPECIAL_STAGE_HEADINGS.get(stage.key, GENERIC_STAGE_HEADINGS)


def _string_ok(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _matches_declared_type(declared_type: str, value: Any) -> bool:
    if declared_type in {"string", "markdown"}:
        return _string_ok(value)
    if declared_type == "object":
        return isinstance(value, dict)
    if declared_type == "string[]":
        return isinstance(value, list) and all(_string_ok(item) for item in value)
    if declared_type == "object[]":
        return isinstance(value, list) and all(isinstance(item, dict) for item in value)
    return False


def _walk_file_entries(value: Any, errors: list[str], path: str) -> None:
    if isinstance(value, dict):
        if "path" in value:
            artifact_path = value.get("path")
            if not isinstance(artifact_path, str) or not artifact_path.strip():
                errors.append(f"{path}.path must be a non-empty string when present.")
            elif artifact_path.startswith("/") and not Path(artifact_path).exists():
                errors.append(f"{path}.path points to a missing file: {artifact_path}")
        if "url" in value and not isinstance(value.get("url"), str):
            errors.append(f"{path}.url must be a string when present.")
        for key, nested in value.items():
            _walk_file_entries(nested, errors, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _walk_file_entries(nested, errors, f"{path}[{index}]")


def validate_stage_payload(stage: StageDefinition, payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    content_md = payload.get("content_md")
    artifacts = payload.get("artifacts")
    notes = payload.get("notes")

    if not _string_ok(content_md):
        errors.append("content_md must be a non-empty markdown string.")
    if not _string_ok(notes):
        errors.append("notes must be a non-empty string.")
    if not isinstance(artifacts, dict):
        errors.append("artifacts must be an object.")
        artifacts = {}

    heading_report: dict[str, Any] = {
        "required": _expected_headings(stage),
        "present": [],
        "title_heading_present": False,
    }
    if isinstance(content_md, str) and content_md.strip():
        stripped = content_md.lstrip()
        heading_report["title_heading_present"] = stripped.startswith("# ")
        if not heading_report["title_heading_present"]:
            errors.append("content_md must start with a top-level markdown heading.")
        positions: list[int] = []
        for heading in _expected_headings(stage):
            position = content_md.find(heading)
            if position < 0:
                errors.append(f"content_md is missing required heading: {heading}")
            else:
                heading_report["present"].append(heading)
                positions.append(position)
        if positions and positions != sorted(positions):
            errors.append("content_md headings are out of the expected order.")

    schema_report: dict[str, Any] = {"required_keys": [], "validated_keys": [], "unexpected_keys": []}
    declared_keys = {item.key for item in stage.artifact_schema}
    for item in stage.artifact_schema:
        if item.required:
            schema_report["required_keys"].append(item.key)
        if item.key not in artifacts:
            if item.required:
                errors.append(f"artifacts is missing required key `{item.key}`.")
            continue
        value = artifacts[item.key]
        if not _matches_declared_type(item.type, value):
            errors.append(f"artifacts.`{item.key}` must match declared type `{item.type}`.")
            continue
        schema_report["validated_keys"].append(item.key)
        _walk_file_entries(value, errors, f"artifacts.{item.key}")

    unexpected = sorted(key for key in artifacts.keys() if key not in declared_keys)
    if unexpected:
        warnings.append(f"Unexpected artifact keys present: {', '.join(unexpected)}")
        schema_report["unexpected_keys"] = unexpected

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "contract": {
            "inputs_count": len(stage.contract.inputs),
            "must_produce_count": len(stage.contract.must_produce),
            "quality_bar_count": len(stage.contract.quality_bar),
            "disallowed_count": len(stage.contract.disallowed),
            "required_headings": _expected_headings(stage),
        },
        "markdown": heading_report,
        "artifact_schema": schema_report,
    }
