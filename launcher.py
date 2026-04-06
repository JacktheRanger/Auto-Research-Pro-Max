from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
FRONTEND_DIR = ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"
RUNTIME_DIR = ROOT / ".runtime"
SERVER_LOG = RUNTIME_DIR / "server.log"
PID_FILE = RUNTIME_DIR / "server.pid"
SERVER_META_FILE = RUNTIME_DIR / "server-meta.json"
BACKEND_STAMP = RUNTIME_DIR / "backend-install.stamp"
FRONTEND_STAMP = RUNTIME_DIR / "frontend-install.stamp"
DEFAULT_PORT = 8000


def info(message: str) -> None:
    print(f"[Auto Research Pro Max] {message}")


def fail(message: str, code: int = 1) -> None:
    print(f"[Auto Research Pro Max] ERROR: {message}", file=sys.stderr)
    sys.exit(code)


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_uvicorn() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "uvicorn.exe"
    return VENV_DIR / "bin" / "uvicorn"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd or ROOT)
    if result.returncode != 0:
        fail(f"Command failed with exit code {result.returncode}: {' '.join(cmd)}", result.returncode)


def ensure_venv() -> None:
    if not venv_python().exists():
        info("Creating Python virtual environment...")
        run([sys.executable, "-m", "venv", str(VENV_DIR)])


def ensure_backend_deps() -> None:
    ensure_runtime_dir()
    backend_sources = newest_mtime([ROOT / "pyproject.toml", ROOT / "backend"])
    stamp_mtime = BACKEND_STAMP.stat().st_mtime if BACKEND_STAMP.exists() else 0.0
    if stamp_mtime >= backend_sources and venv_uvicorn().exists():
        info("Backend dependencies are up to date.")
        return
    info("Ensuring backend dependencies are installed...")
    run([str(venv_python()), "-m", "pip", "install", "-e", "."])
    BACKEND_STAMP.write_text(str(time.time()))


def ensure_frontend_deps() -> None:
    ensure_runtime_dir()
    package_sources = newest_mtime([FRONTEND_DIR / "package.json", FRONTEND_DIR / "package-lock.json"])
    stamp_mtime = FRONTEND_STAMP.stat().st_mtime if FRONTEND_STAMP.exists() else 0.0
    if (FRONTEND_DIR / "node_modules").exists() and stamp_mtime >= package_sources:
        info("Frontend dependencies are up to date.")
        return
    info("Installing frontend dependencies...")
    run(["npm", "install"], cwd=FRONTEND_DIR)
    FRONTEND_STAMP.write_text(str(time.time()))


def newest_mtime(paths: list[Path]) -> float:
    latest = 0.0
    for path in paths:
        if path.is_dir():
            for file_path in path.rglob("*"):
                if file_path.is_file():
                    latest = max(latest, file_path.stat().st_mtime)
        elif path.exists():
            latest = max(latest, path.stat().st_mtime)
    return latest


def frontend_build_required() -> bool:
    index_html = DIST_DIR / "index.html"
    if not index_html.exists():
        return True
    source_mtime = newest_mtime(
        [
            FRONTEND_DIR / "src",
            FRONTEND_DIR / "index.html",
            FRONTEND_DIR / "package.json",
            FRONTEND_DIR / "vite.config.ts",
        ]
    )
    return source_mtime > index_html.stat().st_mtime


def ensure_frontend_build() -> None:
    ensure_frontend_deps()
    if frontend_build_required():
        info("Building frontend bundle...")
        run(["npm", "run", "build"], cwd=FRONTEND_DIR)
    else:
        info("Frontend bundle is up to date.")


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def health_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body)
            return payload.get("status") == "ok"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def load_server_meta() -> dict[str, str | int] | None:
    try:
        if SERVER_META_FILE.exists():
            return json.loads(SERVER_META_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return None


def save_server_meta(host: str, port: int, mode: str) -> None:
    SERVER_META_FILE.write_text(
        json.dumps(
            {
                "host": host,
                "port": port,
                "mode": mode,
                "local_url": local_url(port),
                "lan_urls": lan_urls(port),
            },
            indent=2,
        )
    )


def remove_server_meta() -> None:
    SERVER_META_FILE.unlink(missing_ok=True)


def local_url(port: int = DEFAULT_PORT) -> str:
    return f"http://127.0.0.1:{port}"


def primary_lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        return None
    return None


def lan_ips() -> list[str]:
    ips: list[str] = []
    primary = primary_lan_ip()
    if primary:
        ips.append(primary)

    try:
        for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = result[4][0]
            if ip.startswith("127.") or ip == "0.0.0.0":
                continue
            if ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips


def lan_urls(port: int = DEFAULT_PORT) -> list[str]:
    return [f"http://{ip}:{port}" for ip in lan_ips()]


def existing_pid() -> int | None:
    try:
        if PID_FILE.exists():
            return int(PID_FILE.read_text().strip())
    except ValueError:
        return None
    return None


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def start_server(host: str, mode: str, port: int = DEFAULT_PORT) -> None:
    ensure_runtime_dir()
    current_local_url = local_url(port)
    metadata = load_server_meta()
    if health_ok(f"{current_local_url}/api/health"):
        if metadata and metadata.get("mode") == mode:
            info("Detected an already running server. Reusing it.")
            return
        info("A server is already running in a different mode. Restarting it.")
        stop_server()

    pid = existing_pid()
    if pid and process_alive(pid):
        info(f"Server process {pid} exists. Waiting for health check...")
    else:
        info("Starting backend server...")
        with SERVER_LOG.open("ab") as log_file:
            process = subprocess.Popen(
                [
                    str(venv_uvicorn()),
                    "backend.app.main:app",
                    "--host",
                    host,
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        PID_FILE.write_text(str(process.pid))
        save_server_meta(host, port, mode)

    for _ in range(40):
        if health_ok(f"{current_local_url}/api/health"):
            info("Server is ready.")
            print_access_urls(port, mode)
            return
        time.sleep(0.5)

    fail("Server did not become healthy in time. Check .runtime/server.log")


def stop_server() -> None:
    pid = existing_pid()
    if pid is None:
        info("No tracked server PID found.")
        remove_server_meta()
        return
    if not process_alive(pid):
        info("Tracked server process is not running.")
        PID_FILE.unlink(missing_ok=True)
        remove_server_meta()
        return
    info(f"Stopping server {pid}...")
    os.killpg(pid, signal.SIGTERM)
    for _ in range(20):
        if not process_alive(pid):
            PID_FILE.unlink(missing_ok=True)
            remove_server_meta()
            info("Server stopped.")
            return
        time.sleep(0.25)
    info("Server did not exit after SIGTERM. Sending SIGKILL.")
    os.killpg(pid, signal.SIGKILL)
    PID_FILE.unlink(missing_ok=True)
    remove_server_meta()


def print_access_urls(port: int, mode: str) -> None:
    info(f"Local URL: {local_url(port)}")
    if mode == "lan":
        urls = lan_urls(port)
        if urls:
            for url in urls:
                info(f"LAN URL: {url}")
        else:
            info("LAN mode is enabled, but no non-loopback IPv4 address was detected.")


def open_browser(port: int = DEFAULT_PORT) -> None:
    if os.environ.get("AUTO_RESEARCH_NO_BROWSER") == "1":
        info("Skipping browser open because AUTO_RESEARCH_NO_BROWSER=1")
        return
    info(f"Opening {local_url(port)}")
    webbrowser.open(local_url(port))


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "start"
    if action == "stop":
        stop_server()
        return
    if action not in {"start", "start-lan"}:
        fail(f"Unknown action: {action}")

    mode = "lan" if action == "start-lan" else "local"
    host = "0.0.0.0" if mode == "lan" else "127.0.0.1"

    ensure_venv()
    ensure_backend_deps()
    ensure_frontend_build()
    start_server(host, mode)
    open_browser()
    info("Ready.")


if __name__ == "__main__":
    main()
