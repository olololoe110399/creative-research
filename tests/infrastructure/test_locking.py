from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from creative_research.errors import ApplicationError
from creative_research.infrastructure.locking import project_writer


def test_writer_lock_rejects_other_process_and_releases_after_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"))
    code = "from creative_research.infrastructure.locking import project_writer\nwith project_writer():\n    print('acquired')\n"
    with pytest.raises(RuntimeError):
        with project_writer():
            with project_writer():
                blocked = subprocess.run(
                    [sys.executable, "-c", code],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                assert blocked.returncode == 1 and "Another writer" in blocked.stderr
            raise RuntimeError("interrupted writer")
    released = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=10
    )
    assert released.returncode == 0 and released.stdout.strip() == "acquired"


def test_writer_lock_rejects_concurrent_thread(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))

    def write():
        with project_writer():
            pytest.fail("Concurrent writer acquired lock")

    with project_writer(), ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(ApplicationError, match="Another writer"):
            pool.submit(write).result(timeout=5)


def test_writer_lock_rejects_symlink(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "outside").write_text("retained")
    (tmp_path / ".capture.lock").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="symlink"):
        with project_writer():
            pytest.fail("Symlink lock acquired")
    assert (tmp_path / "outside").read_text() == "retained"
