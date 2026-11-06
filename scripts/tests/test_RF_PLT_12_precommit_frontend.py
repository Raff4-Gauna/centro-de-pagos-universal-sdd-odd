"""RF-PLT-12 (Q-060, design.md sec. 3.6): eslint and prettier in pre-commit, T-PLT-29.

The script gets a fake pnpm: what matters here is which paths and flags it hands over and which exit
code comes back. The real tools run in the manual verification recorded in tasks.md. The last tests
pin the hooks of ``.pre-commit-config.yaml`` and that the flags still match the CI commands.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import precommit_frontend as pf
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PNPM = "/fake/bin/pnpm"


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Replace pnpm: records each argv and answers exit code 0."""
    recorded: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs["cwd"] == REPO_ROOT / "frontend"
        recorded.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(pf.os, "name", "posix")
    monkeypatch.setattr(pf.shutil, "which", lambda name: PNPM if name == "pnpm" else None)
    monkeypatch.setattr(pf.subprocess, "run", fake_run)
    return recorded


def files_passed(argv: list[str]) -> list[str]:
    return argv[argv.index("--") + 1 :]


def test_RF_PLT_12_strips_frontend_prefix(calls: list[list[str]]) -> None:
    assert pf.main(["eslint", "frontend/src/lib/a.ts", "frontend/next.config.ts"]) == 0

    assert calls == [
        [
            PNPM,
            *("exec", "eslint", "--max-warnings", "0", "--no-warn-ignored"),
            *("--", "src/lib/a.ts", "next.config.ts"),
        ]
    ]


def test_RF_PLT_12_prettier_checks_without_rewriting(calls: list[list[str]]) -> None:
    assert pf.main(["prettier", "frontend/src/app/globals.css"]) == 0

    assert calls == [
        [
            PNPM,
            *("exec", "prettier", "--check", "--ignore-path", "../.gitignore"),
            *("--", "src/app/globals.css"),
        ]
    ]


@pytest.mark.parametrize("tool", ["eslint", "prettier"])
def test_RF_PLT_12_excludes_generated_types(tool: str, calls: list[list[str]]) -> None:
    paths = ["frontend/src/types/api.d.ts", "frontend/src/typesafe.ts", "frontend/src/a/types/b.ts"]

    assert pf.main([tool, *paths]) == 0

    assert files_passed(calls[0]) == ["src/typesafe.ts", "src/a/types/b.ts"]


@pytest.mark.parametrize("tool", ["eslint", "prettier"])
def test_RF_PLT_12_ignores_paths_outside_frontend(tool: str, calls: list[list[str]]) -> None:
    assert pf.main([tool, "scripts/frontend/a.ts", "a.ts", "frontend.ts"]) == 0

    assert calls == []


@pytest.mark.parametrize(
    ("tool", "expected"),
    [
        ("eslint", ["a.ts", "b.tsx", "c.mjs", "d.mts"]),
        ("prettier", ["a.ts", "b.tsx", "c.mjs", "d.mts", "e.json", "f.css"]),
    ],
)
def test_RF_PLT_12_each_tool_gets_only_what_ci_covers(
    tool: str, expected: list[str], calls: list[list[str]]
) -> None:
    names = ["a.ts", "b.tsx", "c.mjs", "d.mts", "e.json", "f.css"]
    other = ["README.md", "pnpm-lock.yaml", "Dockerfile", ".dockerignore"]

    assert pf.main([tool, *(f"frontend/{name}" for name in [*names, *other])]) == 0

    assert files_passed(calls[0]) == expected


def test_RF_PLT_12_nothing_left_to_check_does_not_need_pnpm(
    monkeypatch: pytest.MonkeyPatch, calls: list[list[str]]
) -> None:
    monkeypatch.setattr(pf.shutil, "which", lambda _: None)

    assert pf.main(["prettier", "frontend/README.md"]) == 0
    assert pf.main(["eslint"]) == 0
    assert calls == []


@pytest.mark.parametrize("code", [1, 2, 127])
def test_RF_PLT_12_propagates_tool_exit_code(code: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pf.shutil, "which", lambda _: PNPM)
    monkeypatch.setattr(
        pf.subprocess, "run", lambda argv, **_: subprocess.CompletedProcess(argv, code)
    )

    assert pf.main(["eslint", "frontend/src/a.ts"]) == code


def test_RF_PLT_12_missing_pnpm_fails_instead_of_skipping(
    monkeypatch: pytest.MonkeyPatch, calls: list[list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(pf.shutil, "which", lambda _: None)

    assert pf.main(["eslint", "frontend/src/a.ts"]) == 2
    assert calls == []
    assert "pnpm not found" in capsys.readouterr().err


def test_RF_PLT_12_unknown_tool_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        pf.main(["tsc", "frontend/src/a.ts"])

    assert raised.value.code == 2


def test_RF_PLT_12_prefers_the_cmd_shim_of_pnpm(
    monkeypatch: pytest.MonkeyPatch, calls: list[list[str]]
) -> None:
    """corepack leaves ``pnpm`` (sh script) next to ``pnpm.CMD``; only the second one runs there."""
    found = {"pnpm": "C:/bin/pnpm", "pnpm.cmd": "C:/bin/pnpm.CMD"}
    monkeypatch.setattr(pf.shutil, "which", found.get)

    assert pf.main(["eslint", "frontend/src/a.ts"]) == 0

    assert calls[0][0] == "C:/bin/pnpm.CMD"


def test_RF_PLT_12_windows_quotes_every_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``.cmd`` shim of pnpm breaks on the parentheses of a route group left unquoted."""
    monkeypatch.setattr(pf.os, "name", "nt")

    line = pf.spawnable(["C:/a b/pnpm.CMD", "exec", "src/app/(dashboard)/page.tsx"])

    assert line == '"C:/a b/pnpm.CMD" "exec" "src/app/(dashboard)/page.tsx"'


def local_hooks() -> dict[str, dict[str, Any]]:
    text = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    config = yaml.safe_load(text)
    [local] = [repo for repo in config["repos"] if repo["repo"] == "local"]
    return {hook["id"]: hook for hook in local["hooks"]}


@pytest.mark.parametrize("tool", ["eslint", "prettier"])
def test_RF_PLT_12_hook_runs_the_script_on_frontend_only(tool: str) -> None:
    hook = local_hooks()[tool]

    assert hook["entry"] == f"python scripts/precommit_frontend.py {tool}"
    assert hook["language"] == "system"
    assert hook["files"] == "^frontend/"
    assert "pass_filenames" not in hook
    assert not {"exclude_types", "stages", "always_run"} & set(hook)


def test_RF_PLT_12_flags_match_the_ci_commands() -> None:
    """A flag or an extension added to ``pnpm lint``/``format:check`` must reach the hooks too."""
    package = json.loads((REPO_ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    lint, format_check = package["scripts"]["lint"], package["scripts"]["format:check"]

    assert lint == "eslint . --max-warnings 0"
    assert format_check.startswith("prettier --check --ignore-path ../.gitignore ")
    [extensions] = re.findall(r"\*\*/\*\.\{([a-z,]+)\}", format_check)
    assert sorted(extensions.split(",")) == sorted(s[1:] for s in pf.SUFFIXES["prettier"])
    assert '"!src/types/**"' in format_check
    assert pf.GENERATED_PREFIX == "src/types/"
