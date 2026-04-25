"""Lightweight cross-run diff helpers for the run history UI."""
from __future__ import annotations

import difflib
import json
from typing import Any


def _stable_json(value: Any) -> str:
    return json.dumps(value or {}, indent=2, sort_keys=True, ensure_ascii=False)


def _line_diff(left: str, right: str, *, context: int = 3) -> list[str]:
    return list(
        difflib.unified_diff(
            (left or "").splitlines(),
            (right or "").splitlines(),
            fromfile="run_a",
            tofile="run_b",
            n=context,
            lineterm="",
        )
    )


def diff_run_stages(
    stage_a: dict[str, Any] | None,
    stage_b: dict[str, Any] | None,
) -> dict[str, Any]:
    if stage_a is None and stage_b is None:
        return {"missing": True, "content_diff": [], "artifact_diff": []}
    if stage_a is None:
        stage_a = {}
    if stage_b is None:
        stage_b = {}
    content_a = stage_a.get("content_md") or ""
    content_b = stage_b.get("content_md") or ""
    artifact_a = _stable_json(stage_a.get("artifact_json"))
    artifact_b = _stable_json(stage_b.get("artifact_json"))
    return {
        "missing": False,
        "stage_key": stage_a.get("stage_key") or stage_b.get("stage_key") or "",
        "stage_label": stage_a.get("stage_label") or stage_b.get("stage_label") or "",
        "stage_index": stage_a.get("stage_index") or stage_b.get("stage_index") or 0,
        "status_a": stage_a.get("status") or "",
        "status_b": stage_b.get("status") or "",
        "content_diff": _line_diff(content_a, content_b),
        "artifact_diff": _line_diff(artifact_a, artifact_b),
        "content_changed": content_a != content_b,
        "artifact_changed": artifact_a != artifact_b,
    }


def diff_runs(stages_a: list[dict[str, Any]], stages_b: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key_a = {item["stage_key"]: item for item in stages_a}
    by_key_b = {item["stage_key"]: item for item in stages_b}
    keys = sorted(set(by_key_a) | set(by_key_b))
    return [diff_run_stages(by_key_a.get(key), by_key_b.get(key)) for key in keys]
