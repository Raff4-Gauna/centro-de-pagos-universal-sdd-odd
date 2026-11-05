"""Healthcheck of the ``beat`` container (T-PLT-26, design.md §3.4.1, RF-PLT-02).

``python -m apps.common.health.beat_alive [--schedule PATH] [--max-age SECONDS]`` exits 0 when the
schedule file of ``celery beat --schedule PATH`` was written less than ``--max-age`` seconds ago,
and 1 otherwise (missing or stale). Beat runs with ``--max-interval 60`` (it wakes up at least
every 60 s) and syncs its shelve to disk every ~3 min (Celery's ``Scheduler.sync_every``), so a
live beat keeps the file younger than 300 s; a hung or dead one does not.

The shelve backend decides the file names: ``dbm.gnu``/``dbm.ndbm`` write ``PATH`` itself,
``dbm.dumb`` writes ``PATH.dat``/``PATH.dir``/``PATH.bak``. The newest of the names Celery knows
(``PersistentScheduler.known_suffixes``) counts.

Standard library only, on purpose: no Django settings, no broker, no environment read; it runs
every 60 s and must not fail because of anything but beat itself. Its only output is one line on
stderr when unhealthy (Docker keeps it in ``docker inspect``); the path is not a secret.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

# The schedule of the beat service in infra/docker-compose.yml: in the container's own filesystem,
# never persisted nor shared (not a tmpfs: dbm.gnu writes through mmap, and on a tmpfs those writes
# never update the mtime read here).
DEFAULT_SCHEDULE = Path("/tmp/beat/schedule")  # noqa: S108 - container-private path
MAX_AGE_SECONDS = 300
SCHEDULE_SUFFIXES = ("", ".db", ".dat", ".bak", ".dir")


def schedule_age(schedule: Path, *, now: float) -> float | None:
    """Seconds since the newest schedule file was written; ``None`` when there is none."""
    mtimes = []
    for suffix in SCHEDULE_SUFFIXES:
        candidate = schedule.with_name(schedule.name + suffix)
        try:
            mtimes.append(candidate.stat().st_mtime)
        except OSError:
            continue
    if not mtimes:
        return None
    return now - max(mtimes)


def is_alive(schedule: Path, max_age: float, *, now: float) -> bool:
    age = schedule_age(schedule, now=now)
    return age is not None and age < max_age


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exit 0 while celery beat writes its schedule.")
    parser.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE)
    parser.add_argument("--max-age", type=float, default=MAX_AGE_SECONDS)
    args = parser.parse_args(argv)
    now = time.time()
    if is_alive(args.schedule, args.max_age, now=now):
        return 0
    age = schedule_age(args.schedule, now=now)
    reason = "missing" if age is None else f"stale ({age:.0f} s >= {args.max_age:.0f} s)"
    sys.stderr.write(f"beat_alive: schedule {args.schedule} {reason}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
