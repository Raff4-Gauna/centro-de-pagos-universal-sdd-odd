"""``manage.py export_openapi [--check]``: the one way to produce the API contract (ADR-0005).

Wraps drf-spectacular's ``spectacular`` with fixed parameters: the public URLconf (never the
dev-only routes, Q-056), ``--validate --fail-on-warn``, YAML, the language of the settings. Without
``--check`` it writes ``specs/_contracts/openapi.yaml``; with ``--check`` (CI ``typecheck``,
AC-PLT-23) it writes nothing: it generates into a temporary directory, compares byte for byte and,
if they differ, prints the unified diff and exits with code 1. YAML with LF line endings, no
timestamp nor local path: the same bytes on every OS.
"""

from __future__ import annotations

import difflib
import tempfile
from argparse import ArgumentParser
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.common.api.schema import PUBLIC_URLCONF

CONTRACT_LABEL = "specs/_contracts/openapi.yaml"


def contract_path() -> Path:
    return Path(settings.BASE_DIR).parent / CONTRACT_LABEL


class Command(BaseCommand):
    help = "Generate specs/_contracts/openapi.yaml; --check fails with the diff if it is stale."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Write nothing; exit 1 and print the diff if the committed contract is stale.",
        )

    def handle(self, *args: object, check: bool, **options: object) -> None:
        target = contract_path()
        generated = self._generate()
        if not check:
            target.write_bytes(generated)
            self.stdout.write(f"Wrote {CONTRACT_LABEL}")
            return
        committed = target.read_bytes() if target.is_file() else b""
        if committed == generated:
            self.stdout.write(f"{CONTRACT_LABEL} is up to date")
            return
        diff = difflib.unified_diff(
            committed.decode("utf-8").splitlines(keepends=True),
            generated.decode("utf-8").splitlines(keepends=True),
            fromfile=f"{CONTRACT_LABEL} (committed)",
            tofile=f"{CONTRACT_LABEL} (generated)",
        )
        self.stdout.write("".join(diff), ending="")
        raise CommandError(
            f"{CONTRACT_LABEL} is out of date: run `python manage.py export_openapi` and commit it"
        )

    def _generate(self) -> bytes:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "openapi.yaml"
            call_command(
                "spectacular",
                urlconf=PUBLIC_URLCONF,
                validate=True,
                fail_on_warn=True,
                format="openapi",
                lang=settings.LANGUAGE_CODE,
                file=str(output),
                stdout=self.stdout,
                stderr=self.stderr,
            )
            return output.read_bytes()
