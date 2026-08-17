from pathlib import Path
from types import SimpleNamespace

import start_rag


def test_dependency_probe_checks_jwt_before_starting(monkeypatch, tmp_path: Path):
    venv = tmp_path / ".venv"
    scripts = venv / ("Scripts" if start_rag.sys.platform == "win32" else "bin")
    scripts.mkdir(parents=True)
    python = scripts / ("python.exe" if start_rag.sys.platform == "win32" else "python")
    python.touch()
    monkeypatch.setattr(start_rag, "VENV_DIR", venv)

    def probe(command, **_kwargs):
        assert "import jwt" in command[2]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(start_rag.subprocess, "run", probe)

    assert start_rag.ensure_dependencies(force=False) == python
