"""Decision of the ``zona-roja`` check (AC-PLT-32, RN-PLT-12, design.md sec. 3.7.3).

Pure logic, no network (T-PLT-06). The GitHub API calls, ``main()`` and the workflow come in
T-PLT-07: they collect the PR data (changed files with old and new names, labels, comments and each
author's permission) and hand it to ``evaluate``.

Rules:

- No red-zone path and no ``zona-roja`` label: passes.
- Red-zone paths without the label: fails.
- With the label (red paths or not): needs a reviewer verdict. Only comments that carry the marker
  ``<!-- reviewer-verdict -->``, a line ``Veredicto del reviewer: APROBADO|RECHAZADO`` and a line
  ``SHA: <40 hex>`` are verdicts; the ones whose author lacks ``write``/``maintain``/``admin``
  permission, or that do not cite the head SHA, are discarded. The latest remaining one (by
  ``updated_at``; on a tie RECHAZADO wins) must be APROBADO.

The red-zone paths live in ``.github/zona-roja-paths.txt`` (syntax documented in that file), with
globs from ``glob_paths``. Stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from glob_paths import compile_glob, matches

LABEL = "zona-roja"
VERDICT_MARKER = "<!-- reviewer-verdict -->"
# `permission` values of GET /repos/{o}/{r}/collaborators/{u}/permission (role_name: maintain).
WRITE_PERMISSIONS = frozenset({"admin", "maintain", "write"})
DEFAULT_RULES_FILE = Path(__file__).resolve().parent.parent / ".github" / "zona-roja-paths.txt"

Status = Literal["APROBADO", "RECHAZADO"]

_SHA_RE = re.compile(r"[0-9a-f]{40}")
# Whole lines only: a quoted (`> ...`) or decorated line is not a verdict.
_VERDICT_LINE_RE = re.compile(
    r"^[ \t]*Veredicto del reviewer:[ \t]*(APROBADO|RECHAZADO)[ \t]*$", re.M
)
_SHA_LINE_RE = re.compile(r"^[ \t]*SHA:[ \t]*([0-9a-fA-F]{40})[ \t]*$", re.M)


@dataclass(frozen=True)
class RedRule:
    """One line of the paths file: a glob plus optional exceptions (``!glob``) of that line.

    Matching ignores case (path and globs are lowercased): marking too much is cheap, and on a
    case-insensitive checkout (Windows, macOS) ``Scripts/x.py`` is ``scripts/x.py``.
    """

    pattern: str
    exceptions: tuple[str, ...] = ()

    def matches(self, path: str) -> bool:
        folded = path.lower()
        if not matches(folded, self.pattern.lower()):
            return False
        return not any(matches(folded, exception.lower()) for exception in self.exceptions)


@dataclass(frozen=True)
class ChangedFile:
    """A file of the PR; ``previous_path`` is the old name of a rename (it counts too)."""

    path: str
    previous_path: str | None = None


@dataclass(frozen=True)
class Comment:
    """A PR comment, with its author's repository permission as the API reports it."""

    author: str
    permission: str
    body: str
    updated_at: datetime


@dataclass(frozen=True)
class Verdict:
    """A parsed reviewer verdict. ``sha`` is lowercase."""

    status: Status
    sha: str


@dataclass(frozen=True)
class CountedVerdict:
    """The verdict that decided the check, and who published it."""

    author: str
    status: Status
    sha: str
    updated_at: datetime


@dataclass(frozen=True)
class Result:
    passed: bool
    reason: str
    red_paths: tuple[str, ...]
    has_label: bool
    verdict: CountedVerdict | None


def parse_rules(text: str) -> tuple[RedRule, ...]:
    """Parse the paths file. Raises ``ValueError`` naming the line on any malformed entry."""
    rules: list[RedRule] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pattern, *rest = line.split()
        try:
            if pattern.startswith("!"):
                raise ValueError("a line must start with a glob, not with an exception")
            exceptions: list[str] = []
            for token in rest:
                if not token.startswith("!") or len(token) == 1:
                    raise ValueError(f"expected '!<glob>' after the glob, got {token!r}")
                exceptions.append(token[1:])
            for glob in (pattern, *exceptions):
                compile_glob(glob)
        except ValueError as exc:
            raise ValueError(f"line {number}: {exc}") from exc
        rules.append(RedRule(pattern, tuple(exceptions)))
    return tuple(rules)


def load_rules(path: Path = DEFAULT_RULES_FILE) -> tuple[RedRule, ...]:
    """Read and parse the paths file; an empty list is an error (it would disable the check)."""
    rules = parse_rules(path.read_text(encoding="utf-8"))
    if not rules:
        raise ValueError(f"{path}: no rules")
    return rules


def changed_paths(files: Iterable[ChangedFile]) -> list[str]:
    """Every path a PR touches: new names and, for renames, old names too."""
    paths: list[str] = []
    for changed in files:
        paths.append(changed.path)
        if changed.previous_path is not None:
            paths.append(changed.previous_path)
    return paths


def red_paths(paths: Iterable[str], rules: Sequence[RedRule]) -> tuple[str, ...]:
    """The red-zone paths among ``paths``, sorted and without duplicates."""
    return tuple(sorted({path for path in paths if any(rule.matches(path) for rule in rules)}))


def parse_verdict(body: str) -> Verdict | None:
    """Parse a verdict comment; ``None`` if it is not one (or cites no single SHA).

    Contradictory verdict lines in one comment count as RECHAZADO (never as an approval).
    """
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    if VERDICT_MARKER not in text:
        return None
    statuses = set(_VERDICT_LINE_RE.findall(text))
    shas = {sha.lower() for sha in _SHA_LINE_RE.findall(text)}
    if not statuses or len(shas) != 1:
        return None
    status: Status = "APROBADO" if statuses == {"APROBADO"} else "RECHAZADO"
    return Verdict(status=status, sha=shas.pop())


def latest_verdict(comments: Iterable[Comment], head_sha: str) -> CountedVerdict | None:
    """The latest verdict that counts: by a writer and citing ``head_sha`` (lowercase)."""
    counted: list[CountedVerdict] = []
    for comment in comments:
        if comment.permission not in WRITE_PERMISSIONS:
            continue
        parsed = parse_verdict(comment.body)
        if parsed is None or parsed.sha != head_sha:
            continue
        counted.append(
            CountedVerdict(comment.author, parsed.status, parsed.sha, comment.updated_at)
        )
    if not counted:
        return None
    # Latest first; on a tie RECHAZADO sorts before APROBADO, so a rejection is never hidden.
    return max(counted, key=lambda verdict: (verdict.updated_at, verdict.status == "RECHAZADO"))


def evaluate(
    changed_paths: Iterable[str],
    labels: Iterable[str],
    verdicts: Iterable[Comment],
    head_sha: str,
    *,
    rules: Sequence[RedRule] | None = None,
) -> Result:
    """Decide the ``zona-roja`` check. ``verdicts`` are all the PR comments (non-verdicts ignored).

    ``rules`` defaults to ``.github/zona-roja-paths.txt``. Raises ``ValueError`` if ``head_sha`` is
    not 40 hex characters (the caller must fail as "not verified").
    """
    head = head_sha.lower()
    if _SHA_RE.fullmatch(head) is None:
        raise ValueError(f"head SHA must be 40 hex characters, got {head_sha!r}")
    active_rules = load_rules() if rules is None else rules
    red = red_paths(changed_paths, active_rules)
    has_label = LABEL in set(labels)

    if not red and not has_label:
        return Result(True, "no red-zone paths and no label", red, has_label, None)
    if not has_label:
        reason = f"{len(red)} red-zone path(s) touched and the PR lacks the '{LABEL}' label"
        return Result(False, reason, red, has_label, None)

    verdict = latest_verdict(verdicts, head)
    if verdict is None:
        reason = f"no reviewer verdict by an account with write access citing SHA {head}"
        return Result(False, reason, red, has_label, None)
    if verdict.status != "APROBADO":
        reason = f"latest reviewer verdict on {head} is {verdict.status} (by {verdict.author})"
        return Result(False, reason, red, has_label, verdict)
    reason = f"reviewer verdict APROBADO on {head} (by {verdict.author})"
    return Result(True, reason, red, has_label, verdict)
