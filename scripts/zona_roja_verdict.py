"""Reviewer verdicts of the ``zona-roja`` check (AC-PLT-32, design.md sec. 3.7.3 and 6.3).

The format the ``reviewer`` publishes as a PR comment (``.claude/agents/reviewer.md``), each item
on its own line, outside code blocks and not quoted:

    <!-- reviewer-verdict -->
    Veredicto del reviewer: APROBADO|RECHAZADO
    SHA: <40 hex of the PR head>

A verdict counts only if its author has ``write``/``maintain``/``admin`` permission and it cites
the head SHA; the latest one by ``updated_at`` (in UTC; RECHAZADO wins ties) decides. Split out of
``check_zona_roja.py`` (C-14). Stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

VERDICT_MARKER = "<!-- reviewer-verdict -->"
# `permission` values of GET /repos/{o}/{r}/collaborators/{u}/permission (role_name: maintain).
WRITE_PERMISSIONS = frozenset({"admin", "maintain", "write"})

Status = Literal["APROBADO", "RECHAZADO"]

# Whole lines only: a quoted (`> ...`) or decorated line is not a verdict. At most 3 spaces of
# indentation: 4 or more, or a tab, is an indented code block in Markdown.
_VERDICT_LINE_RE = re.compile(
    r"^ {0,3}Veredicto del reviewer:[ \t]*(APROBADO|RECHAZADO)[ \t]*$", re.M
)
_SHA_LINE_RE = re.compile(r"^ {0,3}SHA:[ \t]*([0-9a-fA-F]{40})[ \t]*$", re.M)
# A Markdown code fence (CommonMark): 3+ backticks or tildes, indented at most 3 spaces.
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


class UnreadableVerdictError(ValueError):
    """A writer's rejection cannot be tied to a SHA, so the check cannot be decided."""


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


def strip_code_blocks(text: str) -> str:
    """``text`` without its fenced code blocks (an unclosed fence runs to the end, as in Markdown).

    A reviewer quoting an example verdict inside a code block is not publishing one.
    """
    kept: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        match = _FENCE_RE.match(line)
        if fence is None:
            # A backtick fence cannot have backticks in its info string (that is inline code).
            if match and not (match.group(1)[0] == "`" and "`" in match.group(2)):
                fence = match.group(1)
            else:
                kept.append(line)
        elif (
            match
            and match.group(1)[0] == fence[0]
            and len(match.group(1)) >= len(fence)
            and not match.group(2).strip()
        ):
            fence = None
    return "\n".join(kept)


def _verdict_lines(body: str) -> tuple[set[str], set[str]]:
    """(statuses, lowercase SHAs) of a verdict comment; both empty if it lacks the marker.

    Lines inside code blocks are ignored, the marker's included.
    """
    text = strip_code_blocks(body.replace("\r\n", "\n").replace("\r", "\n"))
    if VERDICT_MARKER not in text:
        return set(), set()
    return set(_VERDICT_LINE_RE.findall(text)), {s.lower() for s in _SHA_LINE_RE.findall(text)}


def is_unreadable_rejection(body: str) -> bool:
    """A RECHAZADO that does not cite exactly one full SHA: it may be about the head."""
    statuses, shas = _verdict_lines(body)
    return "RECHAZADO" in statuses and len(shas) != 1


def parse_verdict(body: str) -> Verdict | None:
    """Parse a verdict comment; ``None`` if it is not one (or cites no single SHA).

    Contradictory verdict lines in one comment count as RECHAZADO (never as an approval).
    """
    statuses, shas = _verdict_lines(body)
    if not statuses or len(shas) != 1:
        return None
    status: Status = "APROBADO" if statuses == {"APROBADO"} else "RECHAZADO"
    return Verdict(status=status, sha=shas.pop())


def as_utc(moment: datetime) -> datetime:
    """Aware UTC ``datetime``; a naive one is taken as UTC (the API always answers in UTC)."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def parse_timestamp(value: str) -> datetime:
    """An API timestamp (ISO 8601, ``Z`` or offset) as aware UTC; ``ValueError`` if unreadable."""
    try:
        return as_utc(datetime.fromisoformat(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unreadable timestamp {value!r}") from exc


def latest_verdict(comments: Iterable[Comment], head_sha: str) -> CountedVerdict | None:
    """The latest verdict that counts: by a writer and citing ``head_sha`` (lowercase).

    Raises ``UnreadableVerdictError`` if a writer's unreadable rejection is not older than that
    verdict (it must not let a previous APROBADO through): the caller fails as "not verified".
    """
    counted: list[CountedVerdict] = []
    unreadable: list[datetime] = []
    for comment in comments:
        if comment.permission not in WRITE_PERMISSIONS:
            continue
        if is_unreadable_rejection(comment.body):
            unreadable.append(as_utc(comment.updated_at))
        parsed = parse_verdict(comment.body)
        if parsed is None or parsed.sha != head_sha:
            continue
        counted.append(
            CountedVerdict(comment.author, parsed.status, parsed.sha, as_utc(comment.updated_at))
        )
    # Latest first; on a tie RECHAZADO sorts before APROBADO, so a rejection is never hidden.
    latest = max(
        counted,
        key=lambda verdict: (verdict.updated_at, verdict.status == "RECHAZADO"),
        default=None,
    )
    if unreadable and (latest is None or max(unreadable) >= latest.updated_at):
        raise UnreadableVerdictError("a RECHAZADO verdict does not cite exactly one full SHA")
    return latest
