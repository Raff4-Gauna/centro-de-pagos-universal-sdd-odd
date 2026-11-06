"""Fake GitHub API of the AC-PLT-24 tests, built from the committed files (T-PLT-40).

No network and no real token. ``matching_world`` is what GitHub answers when the repo matches;
each test breaks one part of it.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from typing import Any

import pytest
import verify_repo_protection as vrp
from github_api import Response

TOKEN = "fake-admin-token-for-tests"  # noqa: S105 - not a secret, never sent anywhere
ENV = {"GH_TOKEN": TOKEN}
API = "https://api.github.com"
RULESET_ID = 4242
World = dict[str, Any]
Mutation = Callable[[World], None]

EXPECTED_RULESET = json.loads(vrp.RULESET_FILE.read_text(encoding="utf-8"))
EXPECTED_SETTINGS = json.loads(vrp.SETTINGS_FILE.read_text(encoding="utf-8"))
BASE = f"{API}/repos/{EXPECTED_SETTINGS['repository']}"


def rule(ruleset: World, kind: str) -> World:
    return next(r for r in ruleset["rules"] if r["type"] == kind)


def matching_world() -> World:
    """What GitHub answers when the repo matches: the expected values plus the fields it adds."""
    detail = copy.deepcopy(EXPECTED_RULESET)
    detail |= {"id": RULESET_ID, "source_type": "Repository", "source": "o/r", "created_at": "t"}
    pull_request = rule(detail, "pull_request")["parameters"]
    pull_request |= {"automatic_copilot_code_review_enabled": False, "required_reviewers": []}
    repo = copy.deepcopy(EXPECTED_SETTINGS["repo"]) | {"id": 1, "private": False, "fork": False}
    repo["security_and_analysis"]["dependabot_security_updates"] = {"status": "disabled"}
    return {
        "rulesets": [{key: detail[key] for key in ("id", "name", "target", "enforcement")}],
        "ruleset": detail,
        "repo": repo,
        "workflow": copy.deepcopy(EXPECTED_SETTINGS["actions_workflow_permissions"]),
        "fork": copy.deepcopy(EXPECTED_SETTINGS["fork_pr_contributor_approval"]),
        "labels": [{"name": "bug"}, *({"name": n} for n in EXPECTED_SETTINGS["labels"])],
    }


def checks(world: World) -> list[dict[str, Any]]:
    parameters = rule(world["ruleset"], "required_status_checks")["parameters"]
    return parameters["required_status_checks"]


def urls(world: World) -> dict[str, Any]:
    return {
        f"{BASE}/rulesets?per_page=100": world["rulesets"],
        f"{BASE}/rulesets/{RULESET_ID}": world["ruleset"],
        BASE: world["repo"],
        f"{BASE}/actions/permissions/workflow": world["workflow"],
        f"{BASE}/actions/permissions/fork-pr-contributor-approval": world["fork"],
        f"{BASE}/labels?per_page=100": world["labels"],
    }


class FakeTransport:
    def __init__(self, answers: Mapping[str, Any]) -> None:
        self.answers = dict(answers)
        self.requests: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float) -> Response:
        self.requests.append((url, dict(headers)))
        answer = self.answers[url]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, Response):
            return answer
        return Response(200, {}, json.dumps(answer).encode())


def run(
    answers: Mapping[str, Any],
    capsys: pytest.CaptureFixture[str],
    *,
    argv: tuple[str, ...] = (),
    env: Mapping[str, str] = ENV,
) -> tuple[int, str]:
    code = vrp.main(list(argv), environ=env, transport=FakeTransport(answers))
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def run_world(world: World, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    return run(urls(world), capsys)


def set_ruleset(key: str, value: Any) -> Mutation:
    def mutate(world: World) -> None:
        world["ruleset"][key] = value

    return mutate


def set_in(section: str, key: str, value: Any) -> Mutation:
    def mutate(world: World) -> None:
        world[section][key] = value

    return mutate
