"""Shared ordered database migration runner."""
from pathlib import Path
from typing import Callable, ContextManager, Any


def run_migrations(connect: Callable[[], ContextManager[Any]]) -> None:
    directory = Path(__file__).resolve().parents[1] / "migrations"
    with connect() as conn:
        for migration in sorted(directory.glob("*.sql")):
            conn.execute(migration.read_text(encoding="utf-8"))
