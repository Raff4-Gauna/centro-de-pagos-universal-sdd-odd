"""Compare the protection of the repo on GitHub with what is committed (AC-PLT-24, D-11).

Usage (the owner, from the repo root; design.md §3.7.4, ``infra/README.md``):
    GH_TOKEN=<admin token> python scripts/verify_repo_protection.py

Read-only: it only sends GET requests. Expected values: ``.github/rulesets/main.json`` and
``.github/repo-settings.expected.json``. Prints every difference.

Exit 0: everything matches. Exit 1: something differs. Exit 2: not verified.

Fails closed. Only ``GH_TOKEN`` is read, on purpose not ``GITHUB_TOKEN``: without admin rights
GitHub answers 200 and omits ``bypass_actors`` and ``security_and_analysis``, so a missing field is
"not verified" and never "there are none". The token is not an argument and is never printed.
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from github_api import GitHubAPIError, GitHubClient, Transport, urllib_transport

EXIT_OK = 0
EXIT_DIFFERS = 1
EXIT_NOT_VERIFIED = 2

REPO_ROOT = Path(__file__).resolve().parent.parent
RULESET_FILE = REPO_ROOT / ".github" / "rulesets" / "main.json"
SETTINGS_FILE = REPO_ROOT / ".github" / "repo-settings.expected.json"
STATUS_CHECKS_PARAMETER = "required_status_checks"


class NotVerifiedError(Exception):
    """An expected file or an answer of the API cannot be trusted to decide."""


def load_expected(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise NotVerifiedError(f"cannot read {path.name}: {exc.__class__.__name__}") from exc
    if not isinstance(payload, dict):
        raise NotVerifiedError(f"{path.name}: expected a JSON object")
    return payload


def require(payload: Any, key: str, where: str) -> Any:
    """A field of an answer. Its absence decides nothing, so it stops the check."""
    if not isinstance(payload, dict) or payload.get(key) is None:
        raise NotVerifiedError(f"{where}.{key} is missing: does the token have admin rights?")
    return payload[key]


def compare_fields(where: str, expected: Mapping[str, Any], actual: Any) -> list[str]:
    """Each expected field, by exact value. Fields GitHub adds do not count."""
    differences: list[str] = []
    for key, wanted in expected.items():
        name = f"{where}.{key}"
        found = require(actual, key, where)
        if isinstance(wanted, dict):
            differences += compare_fields(name, wanted, found)
        elif found != wanted:
            differences.append(f"{name}: expected {wanted!r}, found {found!r}")
    return differences


def _same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, list) and isinstance(actual, list):
        keys = (
            Counter(json.dumps(i, sort_keys=True) for i in items) for items in (expected, actual)
        )
        return next(keys) == next(keys)
    return bool(expected == actual)


def _check_sources(checks: Any, where: str) -> dict[str, list[Any]]:
    """Required check name -> the apps it is accepted from."""
    if not isinstance(checks, list):
        raise NotVerifiedError(f"{where}: expected a list of checks")
    sources: dict[str, list[Any]] = {}
    for check in checks:
        name = require(check, "context", where)
        sources.setdefault(name, []).append(check.get("integration_id"))
    return sources


def compare_checks(where: str, expected: Any, actual: Any) -> list[str]:
    wanted = _check_sources(expected, where)
    found = _check_sources(actual if actual is not None else [], where)
    differences = [f"{where}: required check {n!r} is missing" for n in wanted if n not in found]
    differences += [
        f"{where}: required check {n!r} is not expected" for n in found if n not in wanted
    ]
    for name in wanted.keys() & found.keys():
        if found[name] != wanted[name]:
            differences.append(
                f"{where}: required check {name!r} accepted from app {found[name]!r}, "
                f"expected {wanted[name]!r}"
            )
    return sorted(differences)


def compare_parameters(where: str, expected: Mapping[str, Any], actual: Any) -> list[str]:
    """Absent and empty mean the same: a field GitHub adds only counts if it has a value."""
    if actual is None:
        actual = {}
    if not isinstance(actual, dict):
        raise NotVerifiedError(f"{where}: expected an object of parameters")
    differences: list[str] = []
    for key in sorted(expected.keys() | actual.keys()):
        wanted, found = expected.get(key), actual.get(key)
        if key == STATUS_CHECKS_PARAMETER:
            differences += compare_checks(where, wanted, found)
        elif (wanted or found) and not _same(wanted, found):
            differences.append(f"{where}.{key}: expected {wanted!r}, found {found!r}")
    return differences


def compare_rules(where: str, expected: Any, actual: Any) -> list[str]:
    if not isinstance(actual, list):
        raise NotVerifiedError(f"{where}: expected a list of rules")
    wanted = {rule["type"]: rule.get("parameters", {}) for rule in expected}
    found = {require(rule, "type", where): rule.get("parameters") for rule in actual}
    differences = [f"{where}: rule {kind!r} is missing" for kind in wanted if kind not in found]
    differences += [
        f"{where}: rule {kind!r} is not expected" for kind in found if kind not in wanted
    ]
    for kind in sorted(wanted.keys() & found.keys()):
        differences += compare_parameters(f"{where}.{kind}", wanted[kind], found[kind])
    return differences


def compare_ruleset(client: GitHubClient, repo: str, expected: Mapping[str, Any]) -> list[str]:
    """The list has no rules nor bypass actors: those come from the detail of the ruleset."""
    summaries = client.get_list(f"/repos/{repo}/rulesets")
    branch = [s for s in summaries if require(s, "target", "ruleset") == "branch"]
    name = expected["name"]
    where = f"ruleset {name!r}"
    others = [require(s, "name", "ruleset") for s in branch if s.get("name") != name]
    differences = [f"branch ruleset {other!r} is not expected" for other in others]
    current = [s for s in branch if s.get("name") == name]
    if not current:
        return [f"no ruleset named {name!r} on the branch", *differences]
    identifier = require(current[0], "id", where)
    detail = client.get_object(f"/repos/{repo}/rulesets/{identifier}")
    fields = {key: value for key, value in expected.items() if key != "rules"}
    differences += compare_fields(where, fields, detail)
    return differences + compare_rules(where, expected["rules"], require(detail, "rules", where))


def compare_labels(client: GitHubClient, repo: str, expected: Sequence[str]) -> list[str]:
    names = {require(label, "name", "label") for label in client.get_list(f"/repos/{repo}/labels")}
    return [f"label {label!r} does not exist" for label in expected if label not in names]


def verify(
    client: GitHubClient, ruleset: Mapping[str, Any], settings: Mapping[str, Any]
) -> list[str]:
    repo = settings["repository"]
    return [
        *compare_ruleset(client, repo, ruleset),
        *compare_fields("repo", settings["repo"], client.get_object(f"/repos/{repo}")),
        *compare_fields(
            "actions",
            settings["actions_workflow_permissions"],
            client.get_object(f"/repos/{repo}/actions/permissions/workflow"),
        ),
        *compare_fields(
            "fork_pr",
            settings["fork_pr_contributor_approval"],
            client.get_object(f"/repos/{repo}/actions/permissions/fork-pr-contributor-approval"),
        ),
        *compare_labels(client, repo, settings["labels"]),
    ]


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport = urllib_transport,
) -> int:
    parser = argparse.ArgumentParser(description="Verify the protection of the repo (AC-PLT-24).")
    parser.add_argument("--ruleset", type=Path, default=RULESET_FILE)
    parser.add_argument("--settings", type=Path, default=SETTINGS_FILE)
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ
    try:
        token = env.get("GH_TOKEN")
        if not token:
            raise NotVerifiedError("GH_TOKEN is not set: this needs an admin token of the owner")
        ruleset, settings = load_expected(args.ruleset), load_expected(args.settings)
        differences = verify(GitHubClient(token, transport=transport), ruleset, settings)
    except (GitHubAPIError, NotVerifiedError) as exc:
        print(f"NOT VERIFIED: {exc}", file=sys.stderr)
        return EXIT_NOT_VERIFIED
    # Whatever else went wrong, it is not a pass. Only the type: its text could hold anything.
    except Exception as exc:
        print(f"NOT VERIFIED: unexpected {exc.__class__.__name__}", file=sys.stderr)
        return EXIT_NOT_VERIFIED
    if differences:
        for difference in differences:
            print(f"DIFFERS: {difference}")
        print(f"FAILED: {len(differences)} difference(s)")
        return EXIT_DIFFERS
    print(f"OK: {settings['repository']} matches the committed protection")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
