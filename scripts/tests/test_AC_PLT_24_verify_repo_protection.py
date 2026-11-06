"""AC-PLT-24 (RN-PLT-12/13/18, RF-PLT-13): ``verify_repo_protection.py`` (T-PLT-40, D-11).

No network and no real token (``repo_protection_fakes.py``). Every mutation of the fake API must
be named and exit 1; ``..._failures.py`` has what must exit 2. The committed files are pinned too:
weakening them would make the script agree with a weak repo. The third clause of the AC (a PR with
a red check is not mergeable) is the owner's sacrificial PR, ``infra/README.md``.
"""

from __future__ import annotations

from typing import Any

import pytest
from repo_protection_fakes import (
    EXPECTED_RULESET,
    EXPECTED_SETTINGS,
    TOKEN,
    Mutation,
    World,
    checks,
    matching_world,
    rule,
    run_world,
    set_in,
    set_ruleset,
)


def test_AC_PLT_24_matching_config_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    code, output = run_world(matching_world(), capsys)
    assert code == 0, output
    assert "OK" in output


def test_AC_PLT_24_order_of_lists_does_not_matter(capsys: pytest.CaptureFixture[str]) -> None:
    world = matching_world()
    world["ruleset"]["rules"].reverse()
    checks(world).reverse()
    assert run_world(world, capsys)[0] == 0


def test_AC_PLT_24_committed_files_encode_the_spec() -> None:
    assert EXPECTED_RULESET["enforcement"] == "active"
    assert EXPECTED_RULESET["bypass_actors"] == []
    assert EXPECTED_RULESET["conditions"]["ref_name"] == {
        "include": ["~DEFAULT_BRANCH"],
        "exclude": [],
    }
    assert {r["type"] for r in EXPECTED_RULESET["rules"]} == {
        "deletion",
        "non_fast_forward",
        "required_linear_history",
        "pull_request",
        "required_status_checks",
    }
    pull_request = rule(EXPECTED_RULESET, "pull_request")["parameters"]
    assert pull_request["required_approving_review_count"] == 0
    assert pull_request["allowed_merge_methods"] == ["squash"]
    status = rule(EXPECTED_RULESET, "required_status_checks")["parameters"]
    assert status["strict_required_status_checks_policy"] is True

    repo = EXPECTED_SETTINGS["repo"]
    assert repo["visibility"] == "public"
    assert repo["default_branch"] == "main"
    assert (repo["allow_squash_merge"], repo["allow_merge_commit"]) == (True, False)
    assert repo["allow_rebase_merge"] is False
    assert repo["security_and_analysis"] == {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "enabled"},
    }
    actions = EXPECTED_SETTINGS["actions_workflow_permissions"]
    assert actions["default_workflow_permissions"] == "read"
    assert actions["can_approve_pull_request_reviews"] is False
    fork = EXPECTED_SETTINGS["fork_pr_contributor_approval"]
    assert fork["approval_policy"] == "first_time_contributors"
    assert "zona-roja" in EXPECTED_SETTINGS["labels"]


def set_parameter(kind: str, key: str, value: Any) -> Mutation:
    def mutate(world: World) -> None:
        rule(world["ruleset"], kind)["parameters"][key] = value

    return mutate


def drop_parameter(kind: str, key: str) -> Mutation:
    def mutate(world: World) -> None:
        del rule(world["ruleset"], kind)["parameters"][key]

    return mutate


def add_bypass(world: World) -> None:
    actor = {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
    world["ruleset"]["bypass_actors"].append(actor)


def drop_check(world: World) -> None:
    checks(world).pop()


def add_check(world: World) -> None:
    checks(world).append({"context": "made-up", "integration_id": 15368})


def any_source_check(world: World) -> None:
    del checks(world)[0]["integration_id"]


def other_app_check(world: World) -> None:
    checks(world)[0]["integration_id"] = 1


def drop_rule(kind: str) -> Mutation:
    def mutate(world: World) -> None:
        world["ruleset"]["rules"].remove(rule(world["ruleset"], kind))

    return mutate


def add_rule(world: World) -> None:
    world["ruleset"]["rules"].append({"type": "creation"})


def other_branch(world: World) -> None:
    world["ruleset"]["conditions"]["ref_name"]["include"] = ["refs/heads/other"]


def disable_security(key: str) -> Mutation:
    def mutate(world: World) -> None:
        world["repo"]["security_and_analysis"][key]["status"] = "disabled"

    return mutate


def no_ruleset(world: World) -> None:
    world["rulesets"].clear()


def tag_ruleset_only(world: World) -> None:
    world["rulesets"][0]["target"] = "tag"


def extra_ruleset(world: World) -> None:
    extra = {"id": 7, "name": "other", "target": "branch", "enforcement": "disabled"}
    world["rulesets"].append(extra)


def no_label(world: World) -> None:
    world["labels"] = [{"name": "bug"}]


PR = "pull_request"
STATUS = "required_status_checks"


@pytest.mark.parametrize(
    ("mutate", "named"),
    [
        pytest.param(
            set_parameter(PR, "required_approving_review_count", 1),
            "required_approving_review_count",
            id="approvals",
        ),
        pytest.param(add_bypass, "bypass_actors", id="bypass-actor"),
        pytest.param(drop_check, "zona-roja", id="missing-check"),
        pytest.param(add_check, "made-up", id="extra-check"),
        pytest.param(any_source_check, "'lint'", id="check-from-any-source"),
        pytest.param(other_app_check, "'lint'", id="check-from-other-app"),
        pytest.param(
            set_parameter(PR, "allowed_merge_methods", ["squash", "rebase"]),
            "allowed_merge_methods",
            id="ruleset-merge-methods",
        ),
        pytest.param(
            drop_parameter(PR, "allowed_merge_methods"),
            "allowed_merge_methods",
            id="all-merge-methods",
        ),
        pytest.param(drop_rule("non_fast_forward"), "non_fast_forward", id="force-push"),
        pytest.param(drop_rule("deletion"), "deletion", id="deletion"),
        pytest.param(drop_rule("required_linear_history"), "linear", id="linear-history"),
        pytest.param(drop_rule(PR), PR, id="no-pr-rule"),
        pytest.param(drop_rule(STATUS), STATUS, id="no-checks-rule"),
        pytest.param(add_rule, "creation", id="unexpected-rule"),
        pytest.param(
            set_parameter(STATUS, "strict_required_status_checks_policy", False),
            "strict_required_status_checks_policy",
            id="not-strict",
        ),
        pytest.param(
            set_parameter(PR, "required_reviewers", [{"x": 1}]),
            "required_reviewers",
            id="extra-parameter",
        ),
        pytest.param(set_ruleset("enforcement", "disabled"), "enforcement", id="disabled"),
        pytest.param(set_ruleset("enforcement", "evaluate"), "enforcement", id="evaluate"),
        pytest.param(other_branch, "include", id="other-branch"),
        pytest.param(
            set_in("repo", "allow_merge_commit", True), "allow_merge_commit", id="merge-commit"
        ),
        pytest.param(set_in("repo", "allow_rebase_merge", True), "allow_rebase", id="rebase"),
        pytest.param(set_in("repo", "allow_squash_merge", False), "allow_squash", id="no-squash"),
        pytest.param(
            set_in("repo", "delete_branch_on_merge", False), "delete_branch", id="keep-branch"
        ),
        pytest.param(set_in("repo", "visibility", "private"), "visibility", id="private"),
        pytest.param(set_in("repo", "default_branch", "dev"), "default_branch", id="main-renamed"),
        pytest.param(disable_security("secret_scanning"), "secret_scanning", id="secret-scanning"),
        pytest.param(
            disable_security("secret_scanning_push_protection"),
            "secret_scanning_push_protection",
            id="push-protection",
        ),
        pytest.param(
            set_in("workflow", "default_workflow_permissions", "write"),
            "default_workflow_permissions",
            id="actions-write",
        ),
        pytest.param(
            set_in("workflow", "can_approve_pull_request_reviews", True),
            "can_approve_pull_request_reviews",
            id="actions-approve",
        ),
        pytest.param(
            set_in("fork", "approval_policy", "all_external_contributors"),
            "approval_policy",
            id="fork-approval",
        ),
        pytest.param(no_ruleset, "no ruleset", id="no-ruleset"),
        pytest.param(tag_ruleset_only, "no ruleset", id="tag-ruleset-only"),
        pytest.param(extra_ruleset, "'other'", id="extra-ruleset"),
        pytest.param(no_label, "zona-roja", id="no-label"),
    ],
)
def test_AC_PLT_24_each_difference_is_named_and_exits_1(
    mutate: Mutation, named: str, capsys: pytest.CaptureFixture[str]
) -> None:
    world = matching_world()
    mutate(world)
    code, output = run_world(world, capsys)
    assert code == 1, output
    assert named in output
    assert TOKEN not in output


def test_AC_PLT_24_every_difference_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    world = matching_world()
    set_parameter(PR, "required_approving_review_count", 1)(world)
    no_label(world)
    set_in("fork", "approval_policy", "x")(world)
    code, output = run_world(world, capsys)
    assert code == 1
    for named in ("required_approving_review_count", "zona-roja", "approval_policy"):
        assert named in output
