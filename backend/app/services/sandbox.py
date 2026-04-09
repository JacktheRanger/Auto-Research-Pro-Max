from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from ..db import SANDBOX_DIR

DEFAULT_IMAGE = "python:3.11-slim"
DEFAULT_TIMEOUT_SECONDS = 45
PACKAGE_ALLOWLIST = {
    "numpy",
    "pandas",
    "scikit-learn",
    "scipy",
    "matplotlib",
    "seaborn",
    "networkx",
    "sympy",
    "statsmodels",
    "pydantic",
    "tqdm",
    "requests",
}


def _normalize_package(name: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "", name.lower().strip()).replace("_", "-")


def _requested_packages(prior_outputs: list[dict[str, Any]]) -> list[str]:
    requested: list[str] = []
    for entry in prior_outputs:
        if entry.get("stage_key") == "code_prototype":
            artifacts = entry.get("artifact_json") or {}
            for item in artifacts.get("dependencies") or []:
                normalized = _normalize_package(str(item))
                if normalized:
                    requested.append(normalized)
        content = entry.get("content_md") or ""
        for match in re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)", content, flags=re.MULTILINE):
            normalized = _normalize_package(match.split(".", 1)[0])
            if normalized:
                requested.append(normalized)
    if not requested:
        requested = ["numpy", "pandas"]
    seen: set[str] = set()
    deduped: list[str] = []
    for item in requested:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped[:8]


def _sandbox_paths(run_id: str, stage_index: int) -> dict[str, Path]:
    root = SANDBOX_DIR / run_id / f"stage-{stage_index:02d}"
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    return {"root": root, "outputs": outputs}


def _write_experiment_files(
    root: Path,
    outputs: Path,
    project: dict[str, Any],
    allowed_packages: list[str],
    blocked_packages: list[str],
    timeout_seconds: int,
) -> None:
    request_payload = {
        "project_title": project.get("title") or "",
        "idea": project.get("idea") or "",
        "direction": project.get("direction") or "",
        "allowed_packages": allowed_packages,
        "blocked_packages": blocked_packages,
        "timeout_seconds": timeout_seconds,
    }
    policy_payload = {
        "docker_image": DEFAULT_IMAGE,
        "network": "disabled",
        "timeout_seconds": timeout_seconds,
        "package_allowlist": sorted(PACKAGE_ALLOWLIST),
    }
    script = textwrap.dedent(
        """
        import hashlib
        import json
        import platform
        from pathlib import Path

        root = Path(".")
        outputs = root / "outputs"
        outputs.mkdir(exist_ok=True)

        request_payload = json.loads((root / "request.json").read_text())
        title = request_payload["project_title"]
        idea = request_payload["idea"]
        direction = request_payload["direction"]
        fingerprint = hashlib.sha256(f"{title}|{idea}|{direction}".encode("utf-8")).hexdigest()[:12]
        synthetic_score = (sum(ord(ch) for ch in f"{title}{direction}") % 1000) / 1000

        metrics = {
            "synthetic_score": synthetic_score,
            "fingerprint": fingerprint,
            "package_count": len(request_payload["allowed_packages"]),
            "blocked_package_count": len(request_payload["blocked_packages"]),
        }
        summary = {
            "status": "completed",
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "requested": request_payload,
            "metrics": metrics,
        }

        (outputs / "metrics.json").write_text(json.dumps(metrics, indent=2))
        (outputs / "summary.json").write_text(json.dumps(summary, indent=2))
        (outputs / "notes.md").write_text(
            "\\n".join(
                [
                    "# Sandbox Experiment",
                    "",
                    f"- Fingerprint: `{fingerprint}`",
                    f"- Synthetic score: `{synthetic_score}`",
                    f"- Allowed packages: {', '.join(request_payload['allowed_packages']) or 'none'}",
                    f"- Blocked packages: {', '.join(request_payload['blocked_packages']) or 'none'}",
                ]
            )
        )
        print("sandbox-experiment-fingerprint", fingerprint)
        print("sandbox-synthetic-score", synthetic_score)
        """
    ).strip()

    (root / "request.json").write_text(json.dumps(request_payload, indent=2))
    (root / "policy.json").write_text(json.dumps(policy_payload, indent=2))
    (root / "experiment.py").write_text(script)


def _artifact_manifest(root: Path) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        manifest.append(
            {
                "path": str(file_path.relative_to(root)),
                "size_bytes": file_path.stat().st_size,
            }
        )
    return manifest


def run_experiment_sandbox(
    run_id: str,
    stage_index: int,
    project: dict[str, Any],
    prior_outputs: list[dict[str, Any]],
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    requested_packages = _requested_packages(prior_outputs)
    allowed_packages = [item for item in requested_packages if item in PACKAGE_ALLOWLIST]
    blocked_packages = [item for item in requested_packages if item not in PACKAGE_ALLOWLIST]
    paths = _sandbox_paths(run_id, stage_index)
    _write_experiment_files(
        paths["root"],
        paths["outputs"],
        project,
        allowed_packages,
        blocked_packages,
        timeout_seconds,
    )

    docker_path = shutil.which("docker")
    if not docker_path:
        (paths["outputs"] / "docker_unavailable.txt").write_text("Docker executable not found.")
        return {
            "status": "docker_unavailable",
            "docker_image": DEFAULT_IMAGE,
            "timeout_seconds": timeout_seconds,
            "requested_packages": requested_packages,
            "allowed_packages": allowed_packages,
            "blocked_packages": blocked_packages,
            "artifact_manifest": _artifact_manifest(paths["root"]),
            "workdir": str(paths["root"]),
            "stdout": "",
            "stderr": "Docker executable not found.",
        }

    command = [
        docker_path,
        "run",
        "--rm",
        "--network",
        "none",
        "--cpus",
        "1.0",
        "--memory",
        "1g",
        "-v",
        f"{paths['root']}:/workspace",
        "-w",
        "/workspace",
        DEFAULT_IMAGE,
        "python",
        "experiment.py",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        (paths["outputs"] / "stdout.txt").write_text(stdout)
        (paths["outputs"] / "stderr.txt").write_text(stderr)
        status = "completed" if completed.returncode == 0 else "failed"
        return {
            "status": status,
            "returncode": completed.returncode,
            "docker_image": DEFAULT_IMAGE,
            "timeout_seconds": timeout_seconds,
            "requested_packages": requested_packages,
            "allowed_packages": allowed_packages,
            "blocked_packages": blocked_packages,
            "artifact_manifest": _artifact_manifest(paths["root"]),
            "workdir": str(paths["root"]),
            "stdout": stdout,
            "stderr": stderr,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "").strip()
        stderr = (exc.stderr or "").strip()
        (paths["outputs"] / "stdout.txt").write_text(stdout)
        (paths["outputs"] / "stderr.txt").write_text(stderr)
        return {
            "status": "timed_out",
            "returncode": -1,
            "docker_image": DEFAULT_IMAGE,
            "timeout_seconds": timeout_seconds,
            "requested_packages": requested_packages,
            "allowed_packages": allowed_packages,
            "blocked_packages": blocked_packages,
            "artifact_manifest": _artifact_manifest(paths["root"]),
            "workdir": str(paths["root"]),
            "stdout": stdout,
            "stderr": stderr,
        }
