"""RF-PLT-02 (T-PLT-26, design.md §3.4.1): the healthcheck of the ``beat`` container.

``python -m apps.common.health.beat_alive`` exits 0 while beat keeps writing its schedule file
(in the container's own filesystem) and 1 when the file is older than 300 s or missing. Beat
syncs the file every ~3 min (Celery's ``sync_every``) and wakes up at least every 60 s
(``--max-interval 60``), so a live beat never goes past 300 s. The shelve backend may add a suffix
(``dbm.dumb`` writes ``schedule.dat``/``.dir``): the newest of them counts. No Django, no network.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from apps.common.health import beat_alive

NOW = 1_800_000_000.0
BACKEND = Path(__file__).resolve().parents[2]


def touch(path: Path, mtime: float) -> Path:
    path.write_bytes(b"schedule")
    os.utime(path, (mtime, mtime))
    return path


def test_RF_PLT_02_beat_alive_stale_schedule_is_unhealthy(tmp_path: Path) -> None:
    schedule = touch(tmp_path / "schedule", NOW - beat_alive.MAX_AGE_SECONDS - 1)

    assert not beat_alive.is_alive(schedule, beat_alive.MAX_AGE_SECONDS, now=NOW)


def test_RF_PLT_02_beat_alive_fresh_schedule_is_healthy(tmp_path: Path) -> None:
    schedule = touch(tmp_path / "schedule", NOW - 10)

    assert beat_alive.is_alive(schedule, beat_alive.MAX_AGE_SECONDS, now=NOW)


def test_RF_PLT_02_beat_alive_missing_schedule_is_unhealthy(tmp_path: Path) -> None:
    assert not beat_alive.is_alive(tmp_path / "schedule", beat_alive.MAX_AGE_SECONDS, now=NOW)


def test_RF_PLT_02_beat_alive_newest_suffixed_file_counts(tmp_path: Path) -> None:
    # dbm.dumb: no file at the bare path; .dir is old, .dat was just written.
    touch(tmp_path / "schedule.dir", NOW - 1000)
    touch(tmp_path / "schedule.dat", NOW - 5)

    assert beat_alive.schedule_age(tmp_path / "schedule", now=NOW) == pytest.approx(5)
    assert beat_alive.is_alive(tmp_path / "schedule", beat_alive.MAX_AGE_SECONDS, now=NOW)


def test_RF_PLT_02_beat_alive_unrelated_files_do_not_count(tmp_path: Path) -> None:
    touch(tmp_path / "schedule-other", NOW)

    assert beat_alive.schedule_age(tmp_path / "schedule", now=NOW) is None


def test_RF_PLT_02_beat_alive_defaults_match_compose() -> None:
    assert Path("/tmp/beat/schedule") == beat_alive.DEFAULT_SCHEDULE  # noqa: S108 - container path
    assert beat_alive.MAX_AGE_SECONDS == 300


@pytest.mark.parametrize(("age", "code"), [(10, 0), (beat_alive.MAX_AGE_SECONDS + 1, 1)])
def test_RF_PLT_02_beat_alive_main_exit_code(tmp_path: Path, age: float, code: int) -> None:
    schedule = touch(tmp_path / "schedule", time.time() - age)

    assert beat_alive.main(["--schedule", str(schedule)]) == code


def test_RF_PLT_02_beat_alive_runs_as_module(tmp_path: Path) -> None:
    """The exact healthcheck command of Compose, against a missing file: exit 1, nothing secret."""
    result = subprocess.run(  # noqa: S603 - fixed argv, test-only
        [
            sys.executable,
            "-m",
            "apps.common.health.beat_alive",
            "--schedule",
            str(tmp_path / "schedule"),
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 1
    assert "schedule" in result.stderr
