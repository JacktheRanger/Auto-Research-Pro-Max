"""Sandbox smoke coverage backed by tiny fixture repositories.

These tests exercise ``run_experiment_sandbox`` end-to-end. Running the full
Docker round-trip requires the local daemon, so the test will skip cleanly
when Docker is missing or ``ARPM_SKIP_DOCKER_TESTS=1`` is set in the
environment. Without Docker, the request/policy/prepare manifest is still
asserted so the offline portion stays covered.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.services.sandbox import run_experiment_sandbox

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sandbox"


def _project(repo_path: Path, *, run_command: str, expected_artifacts: list[str]) -> dict[str, object]:
    return {
        "title": f"Sandbox Smoke ({repo_path.name})",
        "repo_path": str(repo_path),
        "repo_url": "",
        "repo_ref": "",
        "sandbox_workdir": "",
        "sandbox_setup_command": "",
        "sandbox_run_command": run_command,
        "expected_artifacts": expected_artifacts,
    }


def test_sandbox_minimal_bash_offline_manifest(temp_data_dir: Path) -> None:
    repo = FIXTURES / "minimal-bash"
    project = _project(repo, run_command="sh ./run.sh", expected_artifacts=["outputs/marker.json"])
    result = run_experiment_sandbox("run_smoke_offline", 1, project, prior_outputs=[])
    # Even when Docker is missing the helper writes request.json, policy.json,
    # prepare.json, and the entrypoint into the manifest; assert plumbing.
    manifest_paths = {entry["path"] for entry in result["artifact_manifest"]}
    assert {"request.json", "policy.json", "prepare.json", "entrypoint.sh"} <= manifest_paths
    request_path = Path(result["workdir"]) / "request.json"
    payload = json.loads(request_path.read_text())
    assert payload["repo_source_type"] == "local_path"
    assert payload["expected_artifacts"] == ["outputs/marker.json"]


@pytest.mark.parametrize(
    "fixture_name,run_command,expected_artifact",
    [
        ("minimal-bash", "sh ./run.sh", "outputs/marker.json"),
        ("minimal-pytest", "sh ./run_benchmark.sh", "outputs/results.json"),
    ],
)
def test_sandbox_runs_inside_docker(
    temp_data_dir: Path,
    docker_available: bool,
    fixture_name: str,
    run_command: str,
    expected_artifact: str,
) -> None:
    if not docker_available:
        pytest.skip("Docker daemon not reachable; sandbox smoke skipped.")

    repo = FIXTURES / fixture_name
    project = _project(repo, run_command=run_command, expected_artifacts=[expected_artifact])
    result = run_experiment_sandbox("run_smoke_docker", 1, project, prior_outputs=[])
    assert result["status"] in {"completed", "passed"}, result
    assert result["returncode"] == 0
    matched = result.get("matched_artifacts") or []
    assert any(item.endswith(expected_artifact.split("/")[-1]) for item in matched), result
