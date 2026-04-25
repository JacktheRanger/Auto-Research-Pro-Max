from __future__ import annotations

import re
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

MIN_LIST_ITEMS: dict[str, int] = {
    "string[]": 1,
    "object[]": 1,
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "with", "in", "on", "at",
    "by", "is", "are", "be", "as", "it", "this", "that", "these", "those",
    "from", "into", "any", "all", "but", "such", "which", "have", "has", "do",
    "does", "than", "then", "via", "can", "will", "should", "must", "across",
    "non", "list", "lists", "set", "sets", "items", "item", "etc",
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


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]+")


def _significant_tokens(text: str) -> set[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    return {token for token in tokens if len(token) >= 4 and token not in STOPWORDS}


def _flatten_text(value: Any, sink: list[str]) -> None:
    if isinstance(value, str):
        sink.append(value)
    elif isinstance(value, dict):
        for nested in value.values():
            _flatten_text(nested, sink)
    elif isinstance(value, list):
        for nested in value:
            _flatten_text(nested, sink)


def _haystack_for_stage(content_md: str | None, artifacts: dict[str, Any]) -> str:
    parts: list[str] = []
    if isinstance(content_md, str):
        parts.append(content_md)
    _flatten_text(artifacts, parts)
    return "\n".join(parts).lower()


def _semantic_must_produce(
    stage: StageDefinition,
    haystack: str,
    haystack_tokens: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    coverage: list[dict[str, Any]] = []
    warnings: list[str] = []
    for expectation in stage.contract.must_produce:
        expectation_tokens = _significant_tokens(expectation)
        if not expectation_tokens:
            coverage.append({"expectation": expectation, "matched_tokens": [], "covered": True})
            continue
        matched = sorted(expectation_tokens & haystack_tokens)
        threshold = max(1, len(expectation_tokens) // 3)
        covered = len(matched) >= threshold
        coverage.append(
            {
                "expectation": expectation,
                "matched_tokens": matched,
                "required_match_count": threshold,
                "covered": covered,
            }
        )
        if not covered:
            warnings.append(
                "must_produce expectation appears uncovered (no related vocabulary): "
                f"\"{expectation}\""
            )
    return coverage, warnings


def _semantic_disallowed(
    stage: StageDefinition,
    haystack: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    for clause in stage.contract.disallowed:
        clause_tokens = _significant_tokens(clause)
        if not clause_tokens:
            continue
        matched = sorted(token for token in clause_tokens if token in haystack)
        threshold = max(2, (len(clause_tokens) * 2) // 3)
        triggered = len(matched) >= threshold and len(clause_tokens) >= 3
        findings.append(
            {
                "clause": clause,
                "matched_tokens": matched,
                "trigger_threshold": threshold,
                "triggered": triggered,
            }
        )
        if triggered:
            warnings.append(
                "disallowed clause may be violated based on overlapping vocabulary: "
                f"\"{clause}\""
            )
    return findings, warnings


def _list_size_check(
    stage: StageDefinition,
    artifacts: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    for item in stage.artifact_schema:
        if item.type not in MIN_LIST_ITEMS:
            continue
        value = artifacts.get(item.key)
        if not isinstance(value, list):
            continue
        minimum = MIN_LIST_ITEMS[item.type]
        findings.append({"key": item.key, "count": len(value), "minimum": minimum})
        if len(value) < minimum and item.required:
            warnings.append(
                f"artifacts.`{item.key}` is empty (expected at least {minimum} entry)."
            )
    return findings, warnings


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

    haystack = _haystack_for_stage(content_md if isinstance(content_md, str) else "", artifacts)
    haystack_tokens = _significant_tokens(haystack)

    must_produce_coverage, must_produce_warnings = _semantic_must_produce(stage, haystack, haystack_tokens)
    warnings.extend(must_produce_warnings)

    disallowed_findings, disallowed_warnings = _semantic_disallowed(stage, haystack)
    warnings.extend(disallowed_warnings)

    list_size_findings, list_size_warnings = _list_size_check(stage, artifacts)
    warnings.extend(list_size_warnings)

    semantic_report = {
        "must_produce_coverage": must_produce_coverage,
        "disallowed_findings": disallowed_findings,
        "list_size_findings": list_size_findings,
        "uncovered_count": sum(1 for entry in must_produce_coverage if not entry["covered"]),
        "disallowed_triggered_count": sum(1 for entry in disallowed_findings if entry["triggered"]),
    }

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
        "semantic": semantic_report,
    }
