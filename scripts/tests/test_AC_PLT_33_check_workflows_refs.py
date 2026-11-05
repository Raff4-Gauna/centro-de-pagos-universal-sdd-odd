"""AC-PLT-33 (RN-PLT-18): local ``uses: ./X``, tag comment by line, fail-closed reads (T-PLT-05).

Split from ``test_AC_PLT_33_check_workflows.py`` (C-14) after the T-PLT-05 review (B-1): a local
action outside ``.github/actions/`` was never read, so its own ``uses:`` went unchecked.
"""

from __future__ import annotations

from pathlib import Path

import check_workflows as cw
import pytest
from test_AC_PLT_33_check_workflows import GOOD, SHA, rules_of, write

EVIL_ACTION = "name: act\nruns:\n  using: composite\n  steps:\n    - uses: evil/act@main\n"
STEP = "      - uses: actions/checkout@"


def with_step(uses: str) -> str:
    """GOOD with one more step that runs ``uses``."""
    return GOOD.replace(STEP, f"      - uses: {uses}\n{STEP}", 1)


def test_AC_PLT_33_local_action_outside_github_actions_is_checked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, with_step("./tools/act"))
    write(tmp_path, EVIL_ACTION, "action.yml", "tools/act")
    assert cw.main(["--root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "tools/act/action.yml: [uses-pin] 'evil/act@main'" in err


def test_AC_PLT_33_local_action_reached_from_a_composite_action_is_checked(tmp_path: Path) -> None:
    write(tmp_path, with_step("./tools/outer"))
    outer = "name: outer\nruns:\n  using: composite\n  steps:\n    - uses: ./tools/inner\n"
    write(tmp_path, outer, "action.yaml", "tools/outer")
    write(tmp_path, EVIL_ACTION, "Action.YML", "tools/inner")
    violations = cw.check_repo(tmp_path)
    assert [(v.path, v.rule) for v in violations] == [("tools/inner/Action.YML", "uses-pin")]


def test_AC_PLT_33_clean_local_action_outside_github_actions_passes(tmp_path: Path) -> None:
    write(tmp_path, with_step("./tools/act/"))
    write(
        tmp_path,
        EVIL_ACTION.replace("evil/act@main", f"org/act@{SHA} # v1"),
        "action.yml",
        "tools/act",
    )
    violations, checked = cw.scan(tmp_path)
    assert violations == []
    assert "tools/act/action.yml" in {p.relative_to(tmp_path.resolve()).as_posix() for p in checked}


@pytest.mark.parametrize(
    "ref",
    ["./.github/actions/nope", "./tools/empty", "./../outside", "./tools/act@v1", "./x.yml"],
    ids=["missing", "dir-without-action", "escapes-repo", "with-ref", "workflow-as-step"],
)
def test_AC_PLT_33_unresolvable_local_action_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], ref: str
) -> None:
    (tmp_path / "tools/empty").mkdir(parents=True)
    write(tmp_path, with_step(ref))
    assert cw.main(["--root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert ".github/workflows/x.yml: [uses-local] job 'lint':" in err


@pytest.mark.parametrize(
    ("ref", "ok"),
    [
        ("./.github/workflows/r.yml", True),
        ("./.github/workflows/missing.yml", False),
        ("./tools/r.yml", False),
    ],
    ids=["reusable-in-workflows", "missing", "outside-workflows"],
)
def test_AC_PLT_33_local_reusable_workflow_must_be_in_workflows(
    tmp_path: Path, ref: str, ok: bool
) -> None:
    write(tmp_path, GOOD + f"  call:\n    uses: {ref}\n")
    write(tmp_path, GOOD, "r.yml")
    write(tmp_path, GOOD, "r.yml", "tools")
    assert (rules_of(tmp_path) == set()) is ok
    if not ok:
        assert rules_of(tmp_path) == {"uses-local"}


@pytest.mark.parametrize(
    ("name", "folder"),
    [("b.YML", ".github/workflows"), ("c.Yaml", ".github/workflows")],
)
def test_AC_PLT_33_workflow_extension_in_any_case_is_checked(
    tmp_path: Path, name: str, folder: str
) -> None:
    write(tmp_path, GOOD)
    write(tmp_path, GOOD.replace("  pull_request:\n", "  pull_request_target:\n"), name, folder)
    assert rules_of(tmp_path) == {"forbidden-trigger"}


def test_AC_PLT_33_action_file_name_in_any_case_is_checked(tmp_path: Path) -> None:
    write(tmp_path, GOOD)
    write(tmp_path, EVIL_ACTION, "ACTION.YML", ".github/actions/other")
    assert rules_of(tmp_path) == {"uses-pin"}


def test_AC_PLT_33_tag_comment_is_checked_on_the_line_of_each_uses(tmp_path: Path) -> None:
    # The same pin twice: one line with the tag, one without. A search over the whole file (or a
    # comment elsewhere that quotes the line) must not cover the second one.
    second = (
        f"      # uses: actions/checkout@{SHA} # v7.0.1\n      - uses: actions/checkout@{SHA}\n"
    )
    write(tmp_path, GOOD + second)
    assert rules_of(tmp_path) == {"uses-tag-comment"}


@pytest.mark.parametrize(
    "value",
    [f'"actions/checkout@{SHA}" # v7.0.1', f"'actions/checkout@{SHA}'   #v7.0.1"],
    ids=["double-quoted", "single-quoted"],
)
def test_AC_PLT_33_quoted_pin_with_tag_comment_passes(tmp_path: Path, value: str) -> None:
    write(tmp_path, GOOD.replace(f"actions/checkout@{SHA} # v7.0.1", value))
    assert cw.check_repo(tmp_path) == []


@pytest.mark.parametrize(
    ("data", "detail"),
    [(b"on: push\njobs: \xff\xfe\n", "utf-8"), (b"? [a, b]\n: c\n", "unhashable")],
    ids=["not-utf8", "unhashable-key"],
)
def test_AC_PLT_33_undecodable_or_unhashable_yaml_is_invalid(
    tmp_path: Path, data: bytes, detail: str
) -> None:
    write(tmp_path, GOOD)
    (tmp_path / ".github/workflows/bad.yml").write_bytes(data)
    violations = [v for v in cw.check_repo(tmp_path) if v.path == ".github/workflows/bad.yml"]
    assert [v.rule for v in violations] == ["invalid-yaml"]
    assert detail in violations[0].detail


def test_AC_PLT_33_job_if_with_an_expression_in_the_name_fails(tmp_path: Path) -> None:
    dynamic = GOOD.replace(
        "  lint:\n", "  helper:\n    name: ${{ inputs.check }}\n    if: always()\n"
    )
    write(tmp_path, dynamic)
    assert rules_of(tmp_path) == {"job-if"}


def test_AC_PLT_33_trigger_and_inherit_in_other_case_fail(tmp_path: Path) -> None:
    write(tmp_path, GOOD.replace("  pull_request:\n", "  Pull_Request_Target:\n"))
    assert rules_of(tmp_path) == {"forbidden-trigger"}
    call = f"  call:\n    uses: org/repo/.github/workflows/r.yml@{SHA} # v1\n    secrets: INHERIT\n"
    write(tmp_path, GOOD + call)
    assert rules_of(tmp_path) == {"secrets"}
