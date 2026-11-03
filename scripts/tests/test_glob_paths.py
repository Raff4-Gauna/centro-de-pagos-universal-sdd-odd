"""``scripts/glob_paths.py``: globs with ``**`` over repo-relative POSIX paths (T-PLT-01)."""

from __future__ import annotations

import pytest
from glob_paths import expand_braces, match_any, matches


@pytest.mark.parametrize(
    "path",
    [
        "migrations/0001_initial.py",
        "backend/apps/charges/migrations/0001_initial.py",
        "backend/apps/charges/migrations/sub/helper.py",
    ],
)
def test_glob_paths_double_star_matches_zero_or_more_directories(path: str) -> None:
    assert matches(path, "**/migrations/**")


def test_glob_paths_double_star_in_the_middle() -> None:
    assert matches("backend/x.py", "backend/**/x.py")
    assert matches("backend/a/b/x.py", "backend/**/x.py")
    assert not matches("backendx.py", "backend/**/x.py")


def test_glob_paths_trailing_double_star_matches_everything_below() -> None:
    assert matches("context/legacy-source/mpqr/qr_client.py", "context/legacy-source/**")
    assert matches("context/legacy-source/README.md", "context/legacy-source/**")
    assert not matches("context/legacy-sourcex/a.py", "context/legacy-source/**")


def test_glob_paths_bare_double_star_matches_any_path() -> None:
    assert matches("a/b/c.py", "**")
    assert matches("c.py", "**")


def test_glob_paths_root_pattern_is_anchored() -> None:
    assert matches("ruff.toml", "ruff.toml")
    assert not matches("backend/ruff.toml", "ruff.toml")
    assert matches("next-env.d.ts", "**/next-env.d.ts")
    assert matches("frontend/next-env.d.ts", "**/next-env.d.ts")


@pytest.mark.parametrize(
    ("path", "pattern"),
    [
        ("backend/apps/common/migrations_helper.py", "**/migrations/**"),
        ("backend/mymigrations/0001.py", "**/migrations/**"),
        ("frontend/src/typesafe/api.ts", "frontend/src/types/**"),
        ("backend/frontend/src/types/api.ts", "frontend/src/types/**"),
        ("frontend/src/types", "frontend/src/types/**"),
        ("aXpy", "a.py"),
        ("scripts/tests/test_x.py", "scripts/*.py"),
    ],
)
def test_glob_paths_no_match(path: str, pattern: str) -> None:
    assert not matches(path, pattern)


def test_glob_paths_single_star_and_question_mark_stay_in_one_segment() -> None:
    assert matches("scripts/check_file_size.py", "scripts/*.py")
    assert matches("backend/apps/common/migrations/0001.py", "backend/apps/*/migrations/000?.py")
    assert not matches("backend/apps/a/b/migrations/0001.py", "backend/apps/*/migrations/0001.py")
    assert not matches("a/b", "a?b")


def test_glob_paths_braces_expand_alternatives() -> None:
    pattern = "frontend/{tsconfig.json,eslint.config.mjs,vitest.config.mts}"
    assert matches("frontend/eslint.config.mjs", pattern)
    assert not matches("frontend/package.json", pattern)
    assert matches("backend/apps/charges/services/create.py", "backend/apps/{identity,charges}/**")
    assert expand_braces("a/{b,c{d,e}}.py") == ["a/b.py", "a/cd.py", "a/ce.py"]


def test_glob_paths_match_any() -> None:
    patterns = ["**/migrations/**", "frontend/src/types/**"]
    assert match_any("frontend/src/types/api.d.ts", patterns)
    assert not match_any("frontend/src/lib/api-client.ts", patterns)
    assert not match_any("anything.py", [])


@pytest.mark.parametrize("pattern", ["", "/abs/path", "a**", "**b/x", "a/**b", "{a,b", "a}"])
def test_glob_paths_invalid_patterns_raise(pattern: str) -> None:
    with pytest.raises(ValueError, match="glob"):
        matches("a/b", pattern)
