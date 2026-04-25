from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def temp_data_dir(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect db.DATA_DIR / SANDBOX_DIR / EXPORT_DIR / DB_PATH to a temp tree."""
    tmp = Path(tempfile.mkdtemp(prefix="arpm-test-"))
    from backend.app import db as db_module
    from backend.app.services import sandbox as sandbox_module

    monkeypatch.setattr(db_module, "DATA_DIR", tmp, raising=False)
    monkeypatch.setattr(db_module, "UPLOAD_DIR", tmp / "uploads", raising=False)
    monkeypatch.setattr(db_module, "SANDBOX_DIR", tmp / "sandboxes", raising=False)
    monkeypatch.setattr(db_module, "EXPORT_DIR", tmp / "exports", raising=False)
    monkeypatch.setattr(db_module, "DB_PATH", tmp / "test.db", raising=False)
    monkeypatch.setattr(sandbox_module, "SANDBOX_DIR", tmp / "sandboxes", raising=False)
    monkeypatch.setattr(sandbox_module, "ROOT_DIR", ROOT, raising=False)

    db_module.init_db()
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def _docker_available() -> bool:
    if os.environ.get("ARPM_SKIP_DOCKER_TESTS") == "1":
        return False
    docker = shutil.which("docker")
    if not docker:
        return False
    try:
        import subprocess

        result = subprocess.run(
            [docker, "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


@pytest.fixture(scope="session")
def docker_available() -> bool:
    return _docker_available()
