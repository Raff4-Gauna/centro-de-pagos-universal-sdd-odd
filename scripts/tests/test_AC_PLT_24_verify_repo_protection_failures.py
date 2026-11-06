"""AC-PLT-24: ``verify_repo_protection.py`` fails closed and keeps the token out (T-PLT-40).

Anything that could not be read exits 2, never 0. The differences (exit 1) are in the sibling test
module; this one is split off by C-14.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import verify_repo_protection as vrp
from github_api import Response
from repo_protection_fakes import (
    API,
    ENV,
    TOKEN,
    FakeTransport,
    Mutation,
    World,
    matching_world,
    rule,
    run,
    run_world,
    set_in,
    set_ruleset,
    urls,
)

EVERY_URL = sorted(urls(matching_world()))


@pytest.mark.parametrize("url", EVERY_URL)
@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(Response(500), id="500"),
        pytest.param(Response(401), id="401"),
        pytest.param(Response(403), id="403"),
        pytest.param(Response(404), id="404"),
        pytest.param(Response(302, {"Location": "https://evil.test"}), id="redirect"),
        pytest.param(Response(200, {}, b"<html>"), id="not-json"),
        pytest.param(OSError(f"connection reset {TOKEN}"), id="transport"),
    ],
)
def test_AC_PLT_24_api_failure_exits_2_never_success(
    url: str, failure: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = run({**urls(matching_world()), url: failure}, capsys)
    assert code == 2, output
    assert "NOT VERIFIED" in output
    assert TOKEN not in output


def drop_key(section: str, key: str) -> Mutation:
    def mutate(world: World) -> None:
        del world[section][key]

    return mutate


@pytest.mark.parametrize(
    "mutate",
    [
        # A token without admin rights gets a 200 without these two (D-11): never read as "none".
        pytest.param(drop_key("ruleset", "bypass_actors"), id="no-bypass-actors"),
        pytest.param(drop_key("repo", "security_and_analysis"), id="no-security-and-analysis"),
        pytest.param(set_in("repo", "security_and_analysis", None), id="null-security"),
    ],
)
def test_AC_PLT_24_token_without_admin_exits_2(
    mutate: Mutation, capsys: pytest.CaptureFixture[str]
) -> None:
    world = matching_world()
    mutate(world)
    code, output = run_world(world, capsys)
    assert code == 2, output
    assert "admin" in output


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(drop_key("ruleset", "rules"), id="no-rules"),
        pytest.param(drop_key("ruleset", "enforcement"), id="no-enforcement"),
        pytest.param(drop_key("ruleset", "conditions"), id="no-conditions"),
        pytest.param(set_ruleset("rules", {"type": "deletion"}), id="rules-not-a-list"),
        pytest.param(set_ruleset("rules", ["deletion"]), id="rule-not-an-object"),
        pytest.param(set_ruleset("rules", [{}]), id="rule-without-type"),
        pytest.param(drop_key("workflow", "default_workflow_permissions"), id="no-permissions"),
        pytest.param(drop_key("fork", "approval_policy"), id="no-policy"),
        pytest.param(drop_key("repo", "default_branch"), id="no-default-branch"),
    ],
)
def test_AC_PLT_24_answer_of_the_wrong_shape_exits_2(
    mutate: Mutation, capsys: pytest.CaptureFixture[str]
) -> None:
    world = matching_world()
    mutate(world)
    code, output = run_world(world, capsys)
    assert code == 2, output
    assert "NOT VERIFIED" in output


@pytest.mark.parametrize("key", ["id", "name", "target"])
def test_AC_PLT_24_ruleset_list_without_a_field_exits_2(
    key: str, capsys: pytest.CaptureFixture[str]
) -> None:
    world = matching_world()
    del world["rulesets"][0][key]
    assert run_world(world, capsys)[0] == 2


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(["lint"], id="items-not-objects"),
        pytest.param([{"integration_id": 15368}], id="item-without-context"),
        pytest.param("lint", id="not-a-list"),
    ],
)
def test_AC_PLT_24_bad_check_list_exits_2(value: Any, capsys: pytest.CaptureFixture[str]) -> None:
    world = matching_world()
    parameters = rule(world["ruleset"], "required_status_checks")["parameters"]
    parameters["required_status_checks"] = value
    assert run_world(world, capsys)[0] == 2


def test_AC_PLT_24_label_without_a_name_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    world = matching_world()
    world["labels"] = [{}]
    assert run_world(world, capsys)[0] == 2


def test_AC_PLT_24_unexpected_error_exits_2_without_its_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(*_: Any) -> list[str]:
        raise RuntimeError(TOKEN)

    monkeypatch.setattr(vrp, "verify", explode)
    code, output = run(urls(matching_world()), capsys)
    assert code == 2
    assert "RuntimeError" in output
    assert TOKEN not in output


@pytest.mark.parametrize(
    "env",
    [
        pytest.param({}, id="no-token"),
        pytest.param({"GH_TOKEN": ""}, id="empty-token"),
        # The token of Actions cannot see bypass_actors nor security_and_analysis (D-11).
        pytest.param({"GITHUB_TOKEN": TOKEN}, id="only-GITHUB_TOKEN"),
    ],
)
def test_AC_PLT_24_without_gh_token_exits_2(
    env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = run(urls(matching_world()), capsys, env=env)
    assert code == 2
    assert "GH_TOKEN" in output


@pytest.mark.parametrize("content", [None, "{", "[]"], ids=["missing", "bad-json", "not-an-object"])
@pytest.mark.parametrize("option", ["--ruleset", "--settings"])
def test_AC_PLT_24_unreadable_expected_file_exits_2(
    option: str, content: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "expected.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    code, output = run(urls(matching_world()), capsys, argv=(option, str(path)))
    assert code == 2
    assert "NOT VERIFIED" in output


def test_AC_PLT_24_the_token_only_goes_to_the_api_as_a_header(
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = FakeTransport(urls(matching_world()))
    assert vrp.main([], environ=ENV, transport=transport) == 0
    assert TOKEN not in capsys.readouterr().out
    assert len(transport.requests) == len(EVERY_URL)
    for url, headers in transport.requests:
        assert url.startswith(f"{API}/")
        assert TOKEN not in url
        assert headers["Authorization"] == f"Bearer {TOKEN}"
