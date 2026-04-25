from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import Any

from ..db import ROOT_DIR, SANDBOX_DIR, media_url_for_path

DEFAULT_BASE_IMAGE = "python:3.11-slim"
DEFAULT_RUNTIME_IMAGE_PREFIX = "auto-research-pro-max-sandbox"
DEFAULT_TIMEOUT_SECONDS = 300
MAX_SANDBOX_ATTEMPTS = 3
DEFAULT_CPU_LIMIT = "1.0"
DEFAULT_MEMORY_LIMIT = "2g"
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
    "torch",
    "torchvision",
    "transformers",
    "datasets",
    "accelerate",
    "scikit-image",
    "lxml",
    "rich",
    "pyyaml",
    "httpx",
    "openai",
    "anthropic",
    "tiktoken",
}
EXTENDED_PACKAGE_BUDGET = 16
RUNTIME_PACKAGES = sorted(PACKAGE_ALLOWLIST | {"pytest"})


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
    deduped: list[str] = []
    seen: set[str] = set()
    for item in requested:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped[:8]


def _normalize_workdir(value: str) -> str:
    raw = value.strip()
    if not raw or raw == ".":
        return ""
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Sandbox workdir must stay inside the repository.")
    normalized = candidate.as_posix().strip("/")
    if normalized in {"", "."}:
        return ""
    return normalized


def _normalize_expected_artifacts(values: list[Any]) -> list[str]:
    patterns: list[str] = []
    seen: set[str] = set()
    for value in values:
        pattern = str(value).strip()
        if not pattern or pattern.startswith("/") or ".." in pattern:
            continue
        normalized = pattern.replace("\\", "/")
        if normalized not in seen:
            patterns.append(normalized)
            seen.add(normalized)
    return patterns


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = (ROOT_DIR / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def _sandbox_paths(run_id: str, stage_index: int) -> dict[str, Path]:
    root = SANDBOX_DIR / run_id / f"stage-{stage_index:02d}"
    if root.exists():
        shutil.rmtree(root)
    repo = root / "repo"
    outputs = root / "outputs"
    root.mkdir(parents=True, exist_ok=True)
    repo.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)
    return {"root": root, "repo": repo, "outputs": outputs}


def _runtime_paths(image_tag: str | None = None) -> dict[str, Path]:
    suffix = re.sub(r"[^a-z0-9]+", "-", (image_tag or "").lower()).strip("-") or "default"
    root = SANDBOX_DIR / ".runtime" / suffix
    root.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "dockerfile": root / "Dockerfile",
        "build_stdout": root / "docker-build.stdout.txt",
        "build_stderr": root / "docker-build.stderr.txt",
    }


def _runtime_image_tag(base_image: str, extra_packages: tuple[str, ...], apt_packages: tuple[str, ...]) -> str:
    fingerprint_source = f"{base_image}|{','.join(extra_packages)}|{','.join(apt_packages)}"
    digest = hashlib.sha1(fingerprint_source.encode("utf-8")).hexdigest()[:10]
    return f"{DEFAULT_RUNTIME_IMAGE_PREFIX}:{digest}"


def _write_runtime_dockerfile(
    path: Path,
    *,
    base_image: str,
    pip_index_url: str,
    apt_packages: list[str],
    extra_packages: list[str],
) -> None:
    packages = sorted({*RUNTIME_PACKAGES, *extra_packages})
    apt_set = sorted({"bash", "make", "git", "curl", *apt_packages})
    pip_index_args = f"--index-url {pip_index_url} " if pip_index_url else ""
    lines = [
        f"FROM {base_image}",
        "ENV PIP_DISABLE_PIP_VERSION_CHECK=1",
        "ENV PYTHONDONTWRITEBYTECODE=1",
        "ENV PYTHONUNBUFFERED=1",
        f"RUN apt-get update && apt-get install -y --no-install-recommends {' '.join(apt_set)} && rm -rf /var/lib/apt/lists/*",
        f"RUN python -m pip install --no-cache-dir {pip_index_args}{' '.join(packages)}",
        "WORKDIR /workspace",
        "",
    ]
    path.write_text("\n".join(lines))


def _artifact_entry(stage_root: Path, file_path: Path) -> dict[str, Any]:
    return {
        "label": file_path.name,
        "kind": file_path.suffix.lstrip(".") or "file",
        "path": str(file_path.relative_to(stage_root)),
        "size_bytes": file_path.stat().st_size,
        "url": media_url_for_path(str(file_path)),
    }


def _glob_candidates(repo_root: Path, outputs_root: Path, pattern: str) -> list[Path]:
    candidates: list[Path] = []
    if pattern.startswith("outputs/"):
        candidates.extend(path for path in outputs_root.parent.glob(pattern) if path.is_file())
    else:
        candidates.extend(path for path in repo_root.glob(pattern) if path.is_file())
        candidates.extend(path for path in outputs_root.glob(pattern) if path.is_file())
    return candidates


def _collect_artifact_manifest(paths: dict[str, Path], expected_patterns: list[str]) -> list[dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    stage_root = paths["root"]

    def remember(file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            return
        relative = str(file_path.relative_to(stage_root))
        collected[relative] = _artifact_entry(stage_root, file_path)

    for control_file in (
        stage_root / "request.json",
        stage_root / "policy.json",
        stage_root / "prepare.json",
        stage_root / "entrypoint.sh",
        stage_root / "setup.command",
        stage_root / "run.command",
    ):
        remember(control_file)

    for artifact in sorted(paths["outputs"].rglob("*")):
        remember(artifact)

    for pattern in expected_patterns:
        for artifact in sorted(_glob_candidates(paths["repo"], paths["outputs"], pattern)):
            remember(artifact)

    return [collected[key] for key in sorted(collected)]


def _collect_expected_matches(paths: dict[str, Path], expected_patterns: list[str]) -> list[str]:
    matched: set[str] = set()
    for pattern in expected_patterns:
        for artifact in _glob_candidates(paths["repo"], paths["outputs"], pattern):
            if artifact.is_file():
                matched.add(str(artifact.relative_to(paths["root"])))
    return sorted(matched)


def _build_runtime_image(
    docker_path: str,
    *,
    base_image: str,
    pip_index_url: str,
    apt_packages: list[str],
    extra_packages: list[str],
) -> tuple[bool, str, str]:
    image_tag = _runtime_image_tag(base_image, tuple(extra_packages), tuple(apt_packages))
    runtime = _runtime_paths(image_tag)
    _write_runtime_dockerfile(
        runtime["dockerfile"],
        base_image=base_image,
        pip_index_url=pip_index_url,
        apt_packages=apt_packages,
        extra_packages=extra_packages,
    )

    inspect = subprocess.run(
        [docker_path, "image", "inspect", image_tag],
        capture_output=True,
        text=True,
        check=False,
    )
    if inspect.returncode == 0:
        return True, "", image_tag

    completed = subprocess.run(
        [docker_path, "build", "-t", image_tag, str(runtime["root"])],
        capture_output=True,
        text=True,
        check=False,
    )
    runtime["build_stdout"].write_text(completed.stdout or "")
    runtime["build_stderr"].write_text(completed.stderr or "")
    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout or "").strip()
        return False, error or "Failed to build the sandbox runtime image.", image_tag
    return True, "", image_tag


def _prepare_repo(paths: dict[str, Path], project: dict[str, Any]) -> dict[str, Any]:
    repo_path = str(project.get("repo_path") or "").strip()
    repo_url = str(project.get("repo_url") or "").strip()
    repo_ref = str(project.get("repo_ref") or "").strip()

    if repo_path:
        source_path = _resolve_repo_path(repo_path)
        if not source_path.exists():
            return {
                "status": "repo_missing",
                "source_type": "local_path",
                "repo_path": str(source_path),
                "stdout": "",
                "stderr": f"Repository path not found: {source_path}",
            }
        if not source_path.is_dir():
            return {
                "status": "repo_not_directory",
                "source_type": "local_path",
                "repo_path": str(source_path),
                "stdout": "",
                "stderr": f"Repository path is not a directory: {source_path}",
            }
        shutil.rmtree(paths["repo"])
        shutil.copytree(
            source_path,
            paths["repo"],
            symlinks=False,
            ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules"),
        )
        return {
            "status": "prepared",
            "source_type": "local_path",
            "repo_path": str(source_path),
            "repo_url": "",
            "repo_ref": repo_ref,
            "stdout": "",
            "stderr": "",
        }

    if not repo_url:
        return {
            "status": "configuration_missing",
            "source_type": "",
            "repo_path": "",
            "repo_url": "",
            "repo_ref": "",
            "stdout": "",
            "stderr": "No repository path or git URL was configured for sandbox execution.",
        }

    git_path = shutil.which("git")
    if not git_path:
        return {
            "status": "git_unavailable",
            "source_type": "git_url",
            "repo_path": "",
            "repo_url": repo_url,
            "repo_ref": repo_ref,
            "stdout": "",
            "stderr": "Git executable not found.",
        }

    shutil.rmtree(paths["repo"])
    clone = subprocess.run(
        [git_path, "clone", repo_url, str(paths["repo"])],
        capture_output=True,
        text=True,
        check=False,
    )
    if clone.returncode != 0:
        return {
            "status": "clone_failed",
            "source_type": "git_url",
            "repo_path": "",
            "repo_url": repo_url,
            "repo_ref": repo_ref,
            "stdout": clone.stdout.strip(),
            "stderr": clone.stderr.strip() or "Git clone failed.",
        }

    checkout_stdout = clone.stdout
    checkout_stderr = clone.stderr
    if repo_ref:
        checkout = subprocess.run(
            [git_path, "-C", str(paths["repo"]), "checkout", repo_ref],
            capture_output=True,
            text=True,
            check=False,
        )
        checkout_stdout = f"{checkout_stdout}\n{checkout.stdout}".strip()
        checkout_stderr = f"{checkout_stderr}\n{checkout.stderr}".strip()
        if checkout.returncode != 0:
            return {
                "status": "checkout_failed",
                "source_type": "git_url",
                "repo_path": "",
                "repo_url": repo_url,
                "repo_ref": repo_ref,
                "stdout": checkout_stdout.strip(),
                "stderr": checkout_stderr or f"Failed to checkout git ref: {repo_ref}",
            }

    return {
        "status": "prepared",
        "source_type": "git_url",
        "repo_path": "",
        "repo_url": repo_url,
        "repo_ref": repo_ref,
        "stdout": checkout_stdout.strip(),
        "stderr": checkout_stderr.strip(),
    }


def _write_execution_files(
    paths: dict[str, Path],
    project: dict[str, Any],
    repo_info: dict[str, Any],
    *,
    requested_packages: list[str],
    allowed_packages: list[str],
    blocked_packages: list[str],
    expected_artifacts: list[str],
    timeout_seconds: int,
    base_image: str,
    docker_image: str,
    extra_packages: list[str],
    apt_packages: list[str],
    pip_index_url: str,
    max_attempts: int,
) -> None:
    workdir = _normalize_workdir(str(project.get("sandbox_workdir") or ""))
    request_payload = {
        "project_title": project.get("title") or "",
        "repo_source_type": repo_info.get("source_type") or "",
        "repo_path": repo_info.get("repo_path") or "",
        "repo_url": repo_info.get("repo_url") or "",
        "repo_ref": repo_info.get("repo_ref") or "",
        "sandbox_workdir": workdir,
        "setup_command": str(project.get("sandbox_setup_command") or "").strip(),
        "run_command": str(project.get("sandbox_run_command") or "").strip(),
        "expected_artifacts": expected_artifacts,
        "requested_packages": requested_packages,
        "allowed_packages": allowed_packages,
        "blocked_packages": blocked_packages,
        "extra_packages": extra_packages,
        "apt_packages": apt_packages,
        "pip_index_url": pip_index_url,
        "max_attempts": max_attempts,
    }
    policy_payload = {
        "base_image": base_image,
        "docker_image": docker_image,
        "network": "disabled",
        "cpu_limit": DEFAULT_CPU_LIMIT,
        "memory_limit": DEFAULT_MEMORY_LIMIT,
        "timeout_seconds": timeout_seconds,
        "preinstalled_packages": sorted(set(RUNTIME_PACKAGES) | set(extra_packages)),
        "preinstalled_apt": sorted(set(apt_packages) | {"bash", "make", "git", "curl"}),
        "max_attempts": max_attempts,
    }
    prepare_payload = {
        "status": repo_info.get("status") or "",
        "source_type": repo_info.get("source_type") or "",
        "repo_path": repo_info.get("repo_path") or "",
        "repo_url": repo_info.get("repo_url") or "",
        "repo_ref": repo_info.get("repo_ref") or "",
    }
    entrypoint = "\n".join(
        [
            "#!/bin/sh",
            "set -eu",
            'REPO_DIR="/workspace/repo"',
            'WORK_DIR="$REPO_DIR"',
            'if [ -n "${ARPM_WORKDIR:-}" ]; then',
            '  WORK_DIR="$REPO_DIR/$ARPM_WORKDIR"',
            "fi",
            'if [ ! -d "$WORK_DIR" ]; then',
            '  echo "Sandbox workdir not found: $WORK_DIR" >&2',
            "  exit 2",
            "fi",
            'export ARPM_REPO_DIR="$REPO_DIR"',
            'export ARPM_WORK_DIR="$WORK_DIR"',
            'export ARPM_OUTPUT_DIR="/workspace/outputs"',
            'if [ -d "$REPO_DIR/.venv/bin" ]; then',
            '  export PATH="$REPO_DIR/.venv/bin:$PATH"',
            "fi",
            'cd "$WORK_DIR"',
            'if [ -s /workspace/setup.command ]; then',
            '  echo "[sandbox] setup command"',
            '  /bin/sh -lc "$(cat /workspace/setup.command)"',
            "fi",
            'if [ -d "$WORK_DIR/.venv/bin" ]; then',
            '  export PATH="$WORK_DIR/.venv/bin:$PATH"',
            "fi",
            'if [ -d "$REPO_DIR/.venv/bin" ]; then',
            '  export PATH="$REPO_DIR/.venv/bin:$PATH"',
            "fi",
            'if [ ! -s /workspace/run.command ]; then',
            '  echo "Sandbox run command is missing." >&2',
            "  exit 2",
            "fi",
            'echo "[sandbox] run command"',
            'exec /bin/sh -lc "$(cat /workspace/run.command)"',
            "",
        ]
    )

    (paths["root"] / "request.json").write_text(json.dumps(request_payload, indent=2))
    (paths["root"] / "policy.json").write_text(json.dumps(policy_payload, indent=2))
    (paths["root"] / "prepare.json").write_text(json.dumps(prepare_payload, indent=2))
    (paths["root"] / "setup.command").write_text(str(project.get("sandbox_setup_command") or "").strip())
    (paths["root"] / "run.command").write_text(str(project.get("sandbox_run_command") or "").strip())
    (paths["root"] / "entrypoint.sh").write_text(entrypoint)


def _resolve_sandbox_options(project: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    base_image = (str(project.get("sandbox_base_image") or "").strip() or DEFAULT_BASE_IMAGE)
    pip_index_url = str(project.get("sandbox_pip_index_url") or "").strip()
    extra_packages_raw = project.get("sandbox_extra_packages") or []
    if isinstance(extra_packages_raw, str):
        extra_packages_raw = re.split(r"[\n,]+", extra_packages_raw)
    extra_packages: list[str] = []
    for entry in extra_packages_raw:
        normalized = _normalize_package(str(entry))
        if normalized and normalized not in extra_packages:
            extra_packages.append(normalized)
        if len(extra_packages) >= EXTENDED_PACKAGE_BUDGET:
            break
    apt_raw = project.get("sandbox_apt_packages") or []
    if isinstance(apt_raw, str):
        apt_raw = re.split(r"[\n,]+", apt_raw)
    apt_packages: list[str] = []
    for entry in apt_raw:
        cleaned = re.sub(r"[^a-zA-Z0-9._+-]+", "", str(entry).strip().lower())
        if cleaned and cleaned not in apt_packages:
            apt_packages.append(cleaned)
        if len(apt_packages) >= EXTENDED_PACKAGE_BUDGET:
            break
    project_timeout = int(project.get("sandbox_timeout_seconds") or 0)
    effective_timeout = project_timeout if project_timeout > 0 else timeout_seconds
    project_attempts = int(project.get("sandbox_max_attempts") or 0)
    if project_attempts <= 0:
        project_attempts = 1
    project_attempts = min(project_attempts, MAX_SANDBOX_ATTEMPTS)
    return {
        "base_image": base_image,
        "pip_index_url": pip_index_url,
        "extra_packages": extra_packages,
        "apt_packages": apt_packages,
        "timeout_seconds": effective_timeout,
        "max_attempts": project_attempts,
    }


def run_experiment_sandbox(
    run_id: str,
    stage_index: int,
    project: dict[str, Any],
    prior_outputs: list[dict[str, Any]],
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    options = _resolve_sandbox_options(project, timeout_seconds)
    base_image = options["base_image"]
    extra_packages = options["extra_packages"]
    apt_packages = options["apt_packages"]
    pip_index_url = options["pip_index_url"]
    effective_timeout = options["timeout_seconds"]
    max_attempts = options["max_attempts"]

    requested_packages = _requested_packages(prior_outputs)
    allowed_packages = [
        item for item in requested_packages if item in PACKAGE_ALLOWLIST or item in extra_packages
    ]
    blocked_packages = [
        item for item in requested_packages if item not in PACKAGE_ALLOWLIST and item not in extra_packages
    ]
    expected_artifacts = _normalize_expected_artifacts(project.get("expected_artifacts") or [])
    paths = _sandbox_paths(run_id, stage_index)
    placeholder_image = _runtime_image_tag(base_image, tuple(extra_packages), tuple(apt_packages))

    try:
        workdir = _normalize_workdir(str(project.get("sandbox_workdir") or ""))
    except ValueError as exc:
        (paths["outputs"] / "configuration_error.txt").write_text(str(exc))
        return {
            "status": "configuration_error",
            "returncode": 2,
            "base_image": base_image,
            "docker_image": placeholder_image,
            "timeout_seconds": effective_timeout,
            "repo_source_type": "",
            "repo_path": str(project.get("repo_path") or ""),
            "repo_url": str(project.get("repo_url") or ""),
            "repo_ref": str(project.get("repo_ref") or ""),
            "sandbox_workdir": str(project.get("sandbox_workdir") or ""),
            "setup_command": str(project.get("sandbox_setup_command") or "").strip(),
            "run_command": str(project.get("sandbox_run_command") or "").strip(),
            "requested_packages": requested_packages,
            "allowed_packages": allowed_packages,
            "blocked_packages": blocked_packages,
            "expected_artifacts": expected_artifacts,
            "extra_packages": extra_packages,
            "apt_packages": apt_packages,
            "pip_index_url": pip_index_url,
            "max_attempts": max_attempts,
            "matched_artifacts": [],
            "artifact_manifest": _collect_artifact_manifest(paths, expected_artifacts),
            "workdir": str(paths["root"]),
            "stdout": "",
            "stderr": str(exc),
            "duration_seconds": 0.0,
            "attempts": [],
        }

    repo_info = _prepare_repo(paths, project)
    prepare_stdout = repo_info.get("stdout") or ""
    prepare_stderr = repo_info.get("stderr") or ""
    if prepare_stdout:
        (paths["outputs"] / "prepare.stdout.txt").write_text(prepare_stdout)
    if prepare_stderr:
        (paths["outputs"] / "prepare.stderr.txt").write_text(prepare_stderr)

    _write_execution_files(
        paths,
        project,
        repo_info,
        requested_packages=requested_packages,
        allowed_packages=allowed_packages,
        blocked_packages=blocked_packages,
        expected_artifacts=expected_artifacts,
        timeout_seconds=effective_timeout,
        base_image=base_image,
        docker_image=placeholder_image,
        extra_packages=extra_packages,
        apt_packages=apt_packages,
        pip_index_url=pip_index_url,
        max_attempts=max_attempts,
    )

    base_result = {
        "base_image": base_image,
        "docker_image": placeholder_image,
        "timeout_seconds": effective_timeout,
        "repo_source_type": repo_info.get("source_type") or "",
        "repo_path": repo_info.get("repo_path") or "",
        "repo_url": repo_info.get("repo_url") or "",
        "repo_ref": repo_info.get("repo_ref") or "",
        "sandbox_workdir": workdir,
        "setup_command": str(project.get("sandbox_setup_command") or "").strip(),
        "run_command": str(project.get("sandbox_run_command") or "").strip(),
        "requested_packages": requested_packages,
        "allowed_packages": allowed_packages,
        "blocked_packages": blocked_packages,
        "expected_artifacts": expected_artifacts,
        "extra_packages": extra_packages,
        "apt_packages": apt_packages,
        "pip_index_url": pip_index_url,
        "max_attempts": max_attempts,
        "workdir": str(paths["root"]),
    }

    if repo_info.get("status") != "prepared":
        return {
            **base_result,
            "status": repo_info.get("status") or "prepare_failed",
            "returncode": 2,
            "matched_artifacts": [],
            "artifact_manifest": _collect_artifact_manifest(paths, expected_artifacts),
            "stdout": prepare_stdout,
            "stderr": prepare_stderr,
            "duration_seconds": 0.0,
            "attempts": [],
        }

    docker_path = shutil.which("docker")
    if not docker_path:
        (paths["outputs"] / "docker_unavailable.txt").write_text("Docker executable not found.")
        return {
            **base_result,
            "status": "docker_unavailable",
            "returncode": 127,
            "matched_artifacts": [],
            "artifact_manifest": _collect_artifact_manifest(paths, expected_artifacts),
            "stdout": "",
            "stderr": "Docker executable not found.",
            "duration_seconds": 0.0,
            "attempts": [],
        }

    built, build_error, image_tag = _build_runtime_image(
        docker_path,
        base_image=base_image,
        pip_index_url=pip_index_url,
        apt_packages=apt_packages,
        extra_packages=extra_packages,
    )
    base_result["docker_image"] = image_tag
    if not built:
        (paths["outputs"] / "docker_build_failed.txt").write_text(build_error)
        return {
            **base_result,
            "status": "image_build_failed",
            "returncode": 125,
            "matched_artifacts": [],
            "artifact_manifest": _collect_artifact_manifest(paths, expected_artifacts),
            "stdout": "",
            "stderr": build_error,
            "duration_seconds": 0.0,
            "attempts": [],
        }

    attempts: list[dict[str, Any]] = []
    last_status: str = ""
    last_returncode: int = 0
    last_stdout: str = ""
    last_stderr: str = ""
    last_duration: float = 0.0
    for attempt in range(1, max(max_attempts, 1) + 1):
        if attempt > 1:
            time.sleep(min(2 * attempt, 6))
        attempt_record: dict[str, Any] = {
            "attempt": attempt,
            "status": "running",
            "started_at": time.time(),
        }
        start = time.monotonic()
        command = [
            docker_path,
            "run",
            "--rm",
            "--network",
            "none",
            "--cpus",
            DEFAULT_CPU_LIMIT,
            "--memory",
            DEFAULT_MEMORY_LIMIT,
            "-e",
            f"ARPM_WORKDIR={workdir}",
            "-v",
            f"{paths['root']}:/workspace",
            "-w",
            "/workspace",
            image_tag,
            "/bin/sh",
            "/workspace/entrypoint.sh",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                check=False,
            )
            duration_seconds = round(time.monotonic() - start, 3)
            stdout = (completed.stdout or "").strip()
            stderr = (completed.stderr or "").strip()
            (paths["outputs"] / f"stdout.attempt-{attempt}.txt").write_text(stdout)
            (paths["outputs"] / f"stderr.attempt-{attempt}.txt").write_text(stderr)
            attempt_record.update(
                {
                    "status": "completed" if completed.returncode == 0 else "failed",
                    "returncode": completed.returncode,
                    "duration_seconds": duration_seconds,
                }
            )
            attempts.append(attempt_record)
            last_status = attempt_record["status"]
            last_returncode = completed.returncode
            last_stdout = stdout
            last_stderr = stderr
            last_duration = duration_seconds
            if completed.returncode == 0:
                break
            continue
        except subprocess.TimeoutExpired as exc:
            duration_seconds = round(time.monotonic() - start, 3)
            stdout = (exc.stdout or "").strip()
            stderr = (exc.stderr or "").strip()
            (paths["outputs"] / f"stdout.attempt-{attempt}.txt").write_text(stdout)
            (paths["outputs"] / f"stderr.attempt-{attempt}.txt").write_text(stderr)
            attempt_record.update(
                {
                    "status": "timed_out",
                    "returncode": -1,
                    "duration_seconds": duration_seconds,
                }
            )
            attempts.append(attempt_record)
            last_status = "timed_out"
            last_returncode = -1
            last_stdout = stdout
            last_stderr = stderr
            last_duration = duration_seconds
            continue

    (paths["outputs"] / "stdout.txt").write_text(last_stdout)
    (paths["outputs"] / "stderr.txt").write_text(last_stderr)
    artifact_manifest = _collect_artifact_manifest(paths, expected_artifacts)
    return {
        **base_result,
        "status": last_status or "failed",
        "returncode": last_returncode,
        "matched_artifacts": _collect_expected_matches(paths, expected_artifacts),
        "artifact_manifest": artifact_manifest,
        "stdout": last_stdout,
        "stderr": last_stderr,
        "duration_seconds": last_duration,
        "attempts": attempts,
    }
