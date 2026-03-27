import os
import signal
import subprocess
import sys
import time
import re
from pathlib import Path



BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "saas-backend"
FRONTEND_DIR = BASE_DIR / "saas-frontend"
BACKEND_PORT = 8001
FRONTEND_PORT = 5174


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    if os.name == "nt":
        path_value = env.get("Path") or env.get("PATH")
        if path_value is not None:
            env["Path"] = path_value
        env.pop("PATH", None)
    return env


def _creationflags() -> int:
    if os.name == "nt":
        return subprocess.CREATE_NEW_PROCESS_GROUP
    return 0


def _resolve_backend_python() -> str:
    venv_python = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _resolve_npm() -> str:
    if os.name != "nt":
        return "npm"

    candidate_paths = [
        Path(os.environ.get("ProgramFiles", "")) / "nodejs" / "npm.cmd",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "nodejs" / "npm.cmd",
    ]
    for candidate in candidate_paths:
        if candidate.exists():
            return str(candidate)
    return "npm.cmd"


def _kill_process_on_port(port: int):
    """Kills any process currently listening on the specified port (Windows only)."""
    if os.name != "nt":
        return

    try:
        output = subprocess.check_output(["netstat", "-ano"], text=True)
        # Look for lines with :PORT and LISTENING
        pattern = rf"TCP\s+(?:0\.0\.0\.0|127\.0\.0\.1|\[::\]):{port}\s+.*\s+LISTENING\s+(\d+)"
        matches = re.finditer(pattern, output)
        pids = {m.group(1) for m in matches}
        
        for pid in pids:
            if int(pid) > 0:
                print(f"Killing process {pid} using port {port}...")
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                time.sleep(0.5)
    except Exception as e:
        print(f"Warning: Could not clear port {port}: {e}")


def run_backend() -> subprocess.Popen[bytes]:
    print(f"Starting Backend on port {BACKEND_PORT}...")
    _kill_process_on_port(BACKEND_PORT)
    cmd = [
        _resolve_backend_python(),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(BACKEND_PORT),
        "--reload",
        "--reload-dir",
        str(BACKEND_DIR),
    ]
    return subprocess.Popen(
        cmd,
        cwd=str(BACKEND_DIR),
        env=_clean_env(),
        creationflags=_creationflags(),
    )


def run_frontend() -> subprocess.Popen[bytes]:
    print(f"Starting Frontend on port {FRONTEND_PORT}...")
    _kill_process_on_port(FRONTEND_PORT)
    cmd = [_resolve_npm(), "run", "dev"]
    return subprocess.Popen(
        cmd,
        cwd=str(FRONTEND_DIR),
        env=_clean_env(),
        creationflags=_creationflags(),
    )


def _terminate_process(proc: subprocess.Popen[bytes] | None, name: str) -> None:
    if proc is None or proc.poll() is not None:
        return

    try:
        if os.name == "nt":
            # Send CTRL_BREAK_EVENT to the process group
            os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
            time.sleep(1)
        else:
            proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            print(f"Failed to stop {name} cleanly.")


if __name__ == "__main__":
    print("=== AICCEL STARTUP SCRIPT ===")
    print(f"Backend: http://localhost:{BACKEND_PORT}")
    print(f"Frontend: http://localhost:{FRONTEND_PORT}")
    print("Clean startup: existing processes on ports will be cleared.")
    print("Press Ctrl+C to stop both processes.")
    print("==============================")

    backend_proc: subprocess.Popen[bytes] | None = None
    frontend_proc: subprocess.Popen[bytes] | None = None

    try:
        backend_proc = run_backend()
        time.sleep(3)
        if backend_proc.poll() is not None:
            raise RuntimeError("Backend failed to start.")

        frontend_proc = run_frontend()
        time.sleep(2)
        if frontend_proc.poll() is not None:
            raise RuntimeError("Frontend failed to start.")

        print("\nAll systems GO! Monitoring...")
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None:
                raise RuntimeError("Backend stopped unexpectedly.")
            if frontend_proc.poll() is not None:
                raise RuntimeError("Frontend stopped unexpectedly.")

    except KeyboardInterrupt:
        print("\nStopping processes...")
    except Exception as exc:
        print(f"\nStartup error: {exc}")
    finally:
        _terminate_process(frontend_proc, "frontend")
        _terminate_process(backend_proc, "backend")
        print("Done.")
        sys.exit(0)
