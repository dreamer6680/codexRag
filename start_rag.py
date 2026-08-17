"""One-command launcher for the Python RAG API."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SERVICE_DIR = ROOT / "services" / "python-rag"
REQUIREMENTS = SERVICE_DIR / "requirements.txt"
VENV_DIR = SERVICE_DIR / ".venv"
REQUIRED_MODULES = (
    "fastapi",
    "uvicorn",
    "httpx",
    "langgraph",
    "qdrant_client",
    "multipart",
    "jwt",
    "cryptography",
)


def run(command: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def venv_python() -> Path:
    return VENV_DIR / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def ensure_dependencies(force: bool) -> Path:
    python = venv_python()
    if not python.exists():
        print("Creating isolated Python environment...")
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    probe = subprocess.run(
        [str(python), "-c", "; ".join(f"import {name}" for name in REQUIRED_MODULES)],
        cwd=SERVICE_DIR,
        capture_output=True,
    )
    if force or probe.returncode != 0:
        print("Installing Python RAG dependencies...")
        run([str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    return python


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the local RAG FastAPI service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--reload", action="store_true", help="Enable development auto-reload")
    parser.add_argument("--install", action="store_true", help="Reinstall Python dependencies")
    parser.add_argument(
        "--with-infra",
        action="store_true",
        help="Start Qdrant and MinerU through Docker Compose first (Ollama stays on the host)",
    )
    args = parser.parse_args()

    if args.with_infra:
        print("Starting RAG infrastructure...")
        run(
            [
                "docker",
                "compose",
                "--env-file",
                ".env.local",
                "up",
                "-d",
                "qdrant",
                "mineru",
                "minio",
                "postgres",
            ]
        )
    python = ensure_dependencies(args.install)

    command = [
        str(python),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        command.append("--reload")
    print(f"RAG API: http://{args.host}:{args.port}/docs")
    run(command, cwd=SERVICE_DIR)


if __name__ == "__main__":
    main()
