"""Decision of the ``zona-roja`` check (AC-PLT-32, RN-PLT-12, design.md sec. 3.7.3).

Usage (CI, ``.github/workflows/zona-roja.yml``, from a checkout of the PR's base SHA, D-09):
    python3 scripts/check_zona_roja.py [--rules PATH]

``evaluate`` is the pure decision (T-PLT-06). ``main()`` (T-PLT-07) reads the PR number and head SHA
from ``$GITHUB_EVENT_PATH``, collects the PR data from the GitHub API (``github_api.py``: changed
files with old and new names, labels, comments, each verdict author's permission), hands it to
``evaluate`` and writes the result to stdout and ``$GITHUB_STEP_SUMMARY``. Exit 0 passed, 1 failed,
2 not verified (any API error or unexpected data: the check fails closed).

Rules:

- No red-zone path and no ``zona-roja`` label: passes.
- Red-zone paths without the label: fails.
- With the label (red paths or not): needs a reviewer verdict. Only comments that carry the marker
  ``<!-- reviewer-verdict -->``, a line ``Veredicto del reviewer: APROBADO|RECHAZADO`` and a line
  ``SHA: <40 hex>`` are verdicts (lines inside fenced or indented code blocks do not count); the
  ones whose author lacks ``write``/``maintain``/``admin`` permission, or that do not cite the head
  SHA, are discarded. The latest remaining one (by ``updated_at``, compared in UTC; on a tie
  RECHAZADO wins) must be APROBADO. The verdict format lives in ``zona_roja_verdict.py``.

The red-zone paths live in ``.github/zona-roja-paths.txt`` (syntax documented in that file), with
globs from ``glob_paths``. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from github_api import DEFAULT_API_URL, GitHubAPIError, GitHubClient, Transport, urllib_transport
from glob_paths import compile_glob, matches
from zona_roja_verdict import (
    Comment,
    CountedVerdict,
    is_unreadable_rejection,
    latest_verdict,
    parse_timestamp,
    parse_verdict,
)

LABEL = "zona-roja"
DEFAULT_RULES_FILE = Path(__file__).resolve().parent.parent / ".github" / "zona-roja-paths.txt"
EXIT_PASSED, EXIT_FAILED, EXIT_NOT_VERIFIED = 0, 1, 2
SUMMARY_MAX_PATHS = 100

_SHA_RE = re.compile(r"[0-9a-f]{40}")
_REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


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


# --- CLI (T-PLT-07): PR data from the GitHub API, result to stdout and the step summary ---


def _str(obj: object, *keys: str) -> str:
    """``obj[k1][k2]...`` as a non-empty string; anything else raises ``GitHubAPIError``."""
    for key in keys:
        obj = obj.get(key) if isinstance(obj, dict) else None
    if not isinstance(obj, str) or not obj:
        raise GitHubAPIError(f"unexpected API data: no string at {'.'.join(keys)}")
    return obj


def read_event(environ: Mapping[str, str]) -> tuple[str, int, str]:
    """(``owner/repo``, PR number, head SHA) of the ``pull_request`` event that started the run."""
    repo = environ.get("GITHUB_REPOSITORY", "")
    if _REPO_RE.fullmatch(repo) is None:
        raise ValueError(f"GITHUB_REPOSITORY is not owner/repo: {repo!r}")
    event = json.loads(Path(environ.get("GITHUB_EVENT_PATH", "")).read_text(encoding="utf-8"))
    pull = event.get("pull_request") if isinstance(event, dict) else None
    number = pull.get("number") if isinstance(pull, dict) else None
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise ValueError("the event has no pull_request.number")
    return repo, number, _str(pull, "head", "sha").lower()


def fetch_pull_request(
    api: GitHubClient, repo: str, number: int, head: str
) -> tuple[list[str], list[ChangedFile], list[Comment]]:
    """Labels, files (old and new names) and, with the label, the verdicts that cite ``head``."""
    base = f"/repos/{repo}"
    pull = api.get_object(f"{base}/pulls/{number}")
    if _str(pull, "head", "sha").lower() != head:
        raise GitHubAPIError("the PR head moved since this run started (a newer run decides)")
    raw_labels = pull.get("labels")
    if not isinstance(raw_labels, list):
        raise GitHubAPIError("unexpected API data: labels is not a list")
    labels = [_str(label, "name") for label in raw_labels]
    files = []
    for raw in api.get_list(f"{base}/pulls/{number}/files"):
        old = _str(raw, "previous_filename") if "previous_filename" in raw else None
        files.append(ChangedFile(_str(raw, "filename"), old))
    expected = pull.get("changed_files")
    # The files endpoint lists at most 3000 files: a truncated list could hide a red path.
    if not isinstance(expected, int) or isinstance(expected, bool) or len(files) != expected:
        raise GitHubAPIError(f"the API listed {len(files)} of {expected!r} changed files")
    comments: list[Comment] = []
    permissions: dict[str, str] = {}
    for raw in api.get_list(f"{base}/issues/{number}/comments") if LABEL in labels else []:
        body = str(raw.get("body") or "")
        parsed = parse_verdict(body)
        cites_head = parsed is not None and parsed.sha == head
        if not cites_head and not is_unreadable_rejection(body):
            continue  # only what can decide about the head costs a permission lookup
        author = _str(raw, "user", "login")
        if author not in permissions:
            login = urllib.parse.quote(author, safe="")
            answer = api.get_object(f"{base}/collaborators/{login}/permission")
            permissions[author] = _str(answer, "permission")
        updated_at = parse_timestamp(_str(raw, "updated_at"))
        comments.append(Comment(author, permissions[author], body, updated_at))
    return labels, files, comments


def _code(text: str) -> str:
    return "`" + re.sub(r"[`\r\n]", "'", text) + "`"


def render_summary(result: Result, head: str) -> str:
    lines = [
        f"## zona-roja\n\n**{'PASSED' if result.passed else 'FAILED'}**: {result.reason}\n",
        f"- Head SHA: {_code(head)}",
        f"- Label `{LABEL}`: {'yes' if result.has_label else 'no'}",
    ]
    if (counted := result.verdict) is not None:
        when = counted.updated_at.isoformat()
        lines.append(f"- Verdict: {counted.status} by {_code(counted.author)} at {when}")
    lines.append(f"- Red-zone paths: {len(result.red_paths)}")
    lines += [f"  - {_code(path)}" for path in result.red_paths[:SUMMARY_MAX_PATHS]]
    if len(result.red_paths) > SUMMARY_MAX_PATHS:
        lines.append(f"  - ... and {len(result.red_paths) - SUMMARY_MAX_PATHS} more")
    return "\n".join(lines) + "\n"


def _emit(text: str, summary_path: str | None) -> None:
    print(text, end="")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write(text)


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport = urllib_transport,
) -> int:
    parser = argparse.ArgumentParser(description="zona-roja check (AC-PLT-32).")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_FILE)
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ
    summary_path = env.get("GITHUB_STEP_SUMMARY")
    try:
        rules = load_rules(args.rules)
        repo, number, head = read_event(env)
        api_url = env.get("GITHUB_API_URL") or DEFAULT_API_URL
        api = GitHubClient(env.get("GITHUB_TOKEN", ""), api_url=api_url, transport=transport)
        labels, files, comments = fetch_pull_request(api, repo, number, head)
        result = evaluate(changed_paths(files), labels, comments, head, rules=rules)
    # OSError: event or rules file unreadable. ValueError: bad JSON, rules, SHA or timestamp, or
    # UnreadableVerdictError.
    except (GitHubAPIError, OSError, ValueError) as exc:
        _emit(f"## zona-roja\n\n**NOT VERIFIED**: {exc}\n", summary_path)
        return EXIT_NOT_VERIFIED
    _emit(render_summary(result, head), summary_path)
    return EXIT_PASSED if result.passed else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
