import os
import sqlite3
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_demo_command_runs_offline(tmp_path, monkeypatch):
    db = tmp_path / "demo.db"
    monkeypatch.setenv("DB_PATH", str(db))
    monkeypatch.setenv("PROFILE_DATA_DIR", "./data/sample")
    monkeypatch.setenv("PRIMARY_LLM_PROVIDER", "mock")
    monkeypatch.setenv("CHECKPOINTER_DRIVER", "sqlite")
    monkeypatch.setenv("POSTGRES_CHECKPOINTER_URL", "")

    from src.core.config import get_settings
    get_settings.cache_clear()

    from src.interface.cli.main import build_parser, cmd_demo
    parser = build_parser()
    args = parser.parse_args(["demo", "--jobs", "3"])
    rc = cmd_demo(args)
    assert rc == 0

    con = sqlite3.connect(str(db))
    jobs = con.execute("SELECT COUNT(*) FROM jobs WHERE id LIKE 'demo_%'").fetchone()[0]
    evals = con.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
    con.close()
    assert jobs == 20
    assert evals >= 1
