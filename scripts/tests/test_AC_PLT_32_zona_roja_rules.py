"""``scripts/check_zona_roja.py``: decision of the ``zona-roja`` check, no network (T-PLT-06).

AC-PLT-32 (RN-PLT-12): a PR with the ``zona-roja`` label, or touching red-zone paths, fails unless
it has the label and an APROBADO verdict by an account with write access citing the head SHA. The
real ``.github/zona-roja-paths.txt`` is exercised too (Q-058: the gate's own paths are red).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from check_zona_roja import (
    LABEL,
    ChangedFile,
    Comment,
    RedRule,
    changed_paths,
    evaluate,
    load_rules,
    parse_rules,
    parse_verdict,
)

HEAD = "a" * 40
OLD = "b" * 40
T0 = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
RULES = load_rules()
RED = "backend/apps/charges/services/create.py"
GREEN = "docs/notes.md"


def verdict_body(status: str = "APROBADO", sha: str = HEAD) -> str:
    return f"<!-- reviewer-verdict -->\nVeredicto del reviewer: {status}\nSHA: {sha}\n"


def comment(
    status: str = "APROBADO",
    sha: str = HEAD,
    *,
    permission: str = "admin",
    minutes: int = 0,
    author: str = "owner",
    body: str | None = None,
) -> Comment:
    return Comment(
        author=author,
        permission=permission,
        body=verdict_body(status, sha) if body is None else body,
        updated_at=T0 + timedelta(minutes=minutes),
    )


def is_red(path: str) -> bool:
    return evaluate([path], [], [], HEAD, rules=RULES).red_paths == (path,)


# --- Decision (AC-PLT-32) ---


def test_AC_PLT_32_no_red_paths_no_label_passes() -> None:
    result = evaluate([GREEN, "frontend/src/components/EmptyState.tsx"], [], [], HEAD, rules=RULES)
    assert result.passed
    assert result.red_paths == ()


def test_AC_PLT_32_red_path_without_label_fails() -> None:
    result = evaluate([GREEN, RED], [], [comment()], HEAD, rules=RULES)
    assert not result.passed
    assert result.red_paths == (RED,)
    assert LABEL in result.reason


def test_AC_PLT_32_red_path_with_label_without_verdict_fails() -> None:
    result = evaluate([RED], [LABEL], [], HEAD, rules=RULES)
    assert not result.passed
    assert result.verdict is None


def test_AC_PLT_32_label_and_approved_verdict_by_writer_on_head_sha_passes() -> None:
    for permission in ("admin", "maintain", "write"):
        result = evaluate([RED], [LABEL], [comment(permission=permission)], HEAD, rules=RULES)
        assert result.passed, permission
        assert result.verdict is not None
        assert result.verdict.status == "APROBADO"


def test_AC_PLT_32_verdict_by_account_without_write_is_ignored() -> None:
    for permission in ("read", "triage", "none", "", "WRITE"):
        result = evaluate([RED], [LABEL], [comment(permission=permission)], HEAD, rules=RULES)
        assert not result.passed, permission
    # A later approval by an outsider does not override the writer's rejection either.
    verdicts = [comment("RECHAZADO"), comment(permission="read", minutes=5, author="fork")]
    assert not evaluate([RED], [LABEL], verdicts, HEAD, rules=RULES).passed


def test_AC_PLT_32_verdict_on_previous_sha_does_not_count() -> None:
    result = evaluate([RED], [LABEL], [comment(sha=OLD)], HEAD, rules=RULES)
    assert not result.passed
    assert result.verdict is None
    # A rejection on the previous SHA does not block an approval on the head SHA.
    verdicts = [comment(minutes=1), comment("RECHAZADO", OLD, minutes=5)]
    assert evaluate([RED], [LABEL], verdicts, HEAD, rules=RULES).passed


def test_AC_PLT_32_latest_verdict_rejected_fails() -> None:
    verdicts = [comment(minutes=0), comment("RECHAZADO", minutes=5)]
    result = evaluate([RED], [LABEL], verdicts, HEAD, rules=RULES)
    assert not result.passed
    assert result.verdict is not None
    assert result.verdict.status == "RECHAZADO"
    # Order of the input does not matter: the latest by updated_at wins.
    assert evaluate([RED], [LABEL], list(reversed(verdicts)), HEAD, rules=RULES).passed is False
    # Rejected, then approved later (an edit or a new comment): passes.
    verdicts = [comment("RECHAZADO", minutes=0), comment(minutes=5)]
    assert evaluate([RED], [LABEL], verdicts, HEAD, rules=RULES).passed


def test_AC_PLT_32_tied_latest_verdicts_rejected_wins() -> None:
    verdicts = [comment(minutes=5), comment("RECHAZADO", minutes=5, author="other-writer")]
    assert not evaluate([RED], [LABEL], verdicts, HEAD, rules=RULES).passed


def test_AC_PLT_32_label_without_red_paths_still_needs_verdict() -> None:
    assert not evaluate([GREEN], [LABEL], [], HEAD, rules=RULES).passed
    assert evaluate([GREEN], [LABEL], [comment()], HEAD, rules=RULES).passed


def test_AC_PLT_32_label_name_is_exact() -> None:
    for label in ("Zona-Roja", "zona roja", "zona-roja "):
        assert not evaluate([RED], [label], [comment()], HEAD, rules=RULES).passed


def test_AC_PLT_32_head_sha_case_is_normalized_and_must_be_40_hex() -> None:
    assert evaluate([RED], [LABEL], [comment(sha="A" * 40)], HEAD, rules=RULES).passed
    assert evaluate([RED], [LABEL], [comment()], HEAD.upper(), rules=RULES).passed
    for bad in ("", "a" * 39, "g" * 40, HEAD + "\n"):
        with pytest.raises(ValueError, match="head SHA"):
            evaluate([RED], [LABEL], [comment()], bad, rules=RULES)


def test_AC_PLT_32_renamed_file_old_path_counts() -> None:
    files = [ChangedFile(path="docs/old-charge-notes.md", previous_path=RED)]
    paths = changed_paths(files)
    assert paths == ["docs/old-charge-notes.md", RED]
    result = evaluate(paths, [], [], HEAD, rules=RULES)
    assert not result.passed
    assert result.red_paths == (RED,)
    assert changed_paths([ChangedFile(path=GREEN)]) == [GREEN]


def test_AC_PLT_32_red_paths_are_sorted_and_unique() -> None:
    other = ".github/workflows/ci.yml"
    result = evaluate([RED, other, RED, GREEN], [], [], HEAD, rules=RULES)
    assert result.red_paths == (other, RED)


# --- Verdict parser ---


def test_AC_PLT_32_verdict_parser_accepts_the_documented_format() -> None:
    parsed = parse_verdict(
        "Resumen\r\n<!-- reviewer-verdict -->\r\n  Veredicto del reviewer: APROBADO\r\nSHA: "
        + HEAD.upper()
    )
    assert parsed is not None
    assert (parsed.status, parsed.sha) == ("APROBADO", HEAD)


@pytest.mark.parametrize(
    "body",
    [
        "Veredicto del reviewer: APROBADO\nSHA: " + HEAD,  # no marker
        "<!-- reviewer-verdict -->\nSHA: " + HEAD,  # no verdict line
        "<!-- reviewer-verdict -->\nVeredicto del reviewer: APROBADO",  # no SHA
        "<!-- reviewer-verdict -->\nVeredicto del reviewer: aprobado\nSHA: " + HEAD,
        "<!-- reviewer-verdict -->\nVeredicto del reviewer: APROBADO con cambios\nSHA: " + HEAD,
        "<!-- reviewer-verdict -->\nVeredicto del reviewer: APROBADO\nSHA: " + HEAD[:39],
        "<!-- reviewer-verdict -->\nVeredicto del reviewer: APROBADO\nSHA: " + HEAD + "0",
        "<!-- reviewer-verdict -->\nVeredicto del reviewer: APROBADO\nSHA: "
        + HEAD
        + "\nSHA: "
        + OLD,
        "<!-- reviewer-verdict -->\n> Veredicto del reviewer: APROBADO\n> SHA: " + HEAD,  # quoted
    ],
)
def test_AC_PLT_32_verdict_parser_rejects_malformed_bodies(body: str) -> None:
    assert parse_verdict(body) is None


def test_AC_PLT_32_contradictory_verdict_counts_as_rejected() -> None:
    body = verdict_body() + "Veredicto del reviewer: RECHAZADO\n"
    parsed = parse_verdict(body)
    assert parsed is not None
    assert parsed.status == "RECHAZADO"
    assert not evaluate([RED], [LABEL], [comment(body=body)], HEAD, rules=RULES).passed


def test_AC_PLT_32_repeated_identical_lines_are_one_verdict() -> None:
    parsed = parse_verdict(verdict_body() + verdict_body())
    assert parsed is not None
    assert parsed.status == "APROBADO"


# --- Rules file syntax ---


def test_AC_PLT_32_rules_parser_skips_comments_and_reads_exceptions() -> None:
    rules = parse_rules("# comment\n\n  a/**  !a/b/**   !a/c.py \nd/*.py\n")
    assert rules == (RedRule("a/**", ("a/b/**", "a/c.py")), RedRule("d/*.py", ()))
    assert rules[0].matches("a/x.py")
    assert not rules[0].matches("a/b/x.py")
    assert not rules[0].matches("a/c.py")


@pytest.mark.parametrize(
    "text", ["!a/**\n", "a/** b/**\n", "a/** !\n", "/abs/**\n", "a/**x\n", "a/{b\n"]
)
def test_AC_PLT_32_rules_parser_rejects_invalid_lines(text: str) -> None:
    with pytest.raises(ValueError, match="line 1"):
        parse_rules(text)


def test_AC_PLT_32_rules_file_is_never_empty(tmp_path: Path) -> None:
    empty = tmp_path / "paths.txt"
    empty.write_text("# nothing\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no rules"):
        load_rules(empty)


def test_AC_PLT_32_exception_does_not_shadow_another_line() -> None:
    rules = parse_rules("backend/** !backend/apps/**\nbackend/**/migrations/**\n")
    result = evaluate(["backend/apps/x/migrations/0001_initial.py"], [], [], HEAD, rules=rules)
    assert result.red_paths == ("backend/apps/x/migrations/0001_initial.py",)
    assert evaluate(["backend/apps/x/views.py"], [], [], HEAD, rules=rules).passed


# --- The real list (.github/zona-roja-paths.txt) ---


@pytest.mark.parametrize(
    "path",
    [
        "specs/_contracts/openapi.yaml",
        "backend/apps/common/api/problems.py",
        "backend/apps/common/api/exceptions.py",
        "backend/apps/common/api/schema.py",
        "backend/apps/charges/migrations/0001_initial.py",
        "backend/apps/common/migration_lint/rules.py",
        "backend/apps/common/management/commands/lint_migrations.py",
        "backend/apps/common/management/commands/check_migrations_roundtrip.py",
        "backend/tests/migrations/conftest.py",
        "backend/tests/architecture/ast_rules.py",
        "backend/apps/identity/models.py",
        "backend/apps/tenancy/selectors/organizations.py",
        "backend/apps/integrations/providers/mercadopago/client.py",
        "backend/apps/charges/domain/states.py",
        "backend/apps/webhooks/services/receive.py",
        "backend/apps/reconciliation/services/run.py",
        "frontend/src/app/api/[...path]/route.ts",  # the BFF, from SPEC-01 on (T-IDA-22)
        "frontend/src/app/api/auth/google/callback/route.ts",
        "frontend/src/lib/server/backend-proxy.ts",
        "frontend/src/lib/server/cookies.ts",
        "frontend/src/proxy.ts",
    ],
)
def test_AC_PLT_32_red_zone_paths_are_red(path: str) -> None:
    assert is_red(path)


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        ".github/workflows/zona-roja.yml",
        ".github/zona-roja-paths.txt",
        ".github/actions/setup/action.yml",
        ".github/dependabot.yml",
        "scripts/check_zona_roja.py",
        "scripts/glob_paths.py",
        "scripts/audit_tool_requirements.txt",
        "scripts/tests/test_AC_PLT_32_zona_roja_rules.py",
        ".pre-commit-config.yaml",
        ".gitleaks.toml",
        "ruff.toml",
        "backend/pyproject.toml",
        "frontend/tsconfig.json",
        "frontend/eslint.config.mjs",
        "frontend/vitest.config.mts",
        "frontend/package.json",
        "frontend/pnpm-workspace.yaml",
        "frontend/.npmrc",
        "frontend/.pnpmfile.cjs",
        "backend/uv.lock",
        "backend/pip_audit.py",
        "backend/mypy.ini",
        "backend/build_backend/hooks.py",
        "uv.toml",
        "pyproject.toml",
        "package.json",
        ".npmrc",
        ".python-version",
    ],
)
def test_Q058_gate_paths_are_red(path: str) -> None:
    assert is_red(path)


def test_Q058_gitleaksignore_at_any_depth_is_red() -> None:
    assert is_red(".gitleaksignore")
    assert is_red("docs/x/.gitleaksignore")
    assert is_red("frontend/src/.gitleaksignore")


@pytest.mark.parametrize(
    "path",
    [
        *("ruff.toml", ".ruff.toml", "docs/ruff.toml", "backend/apps/x/.ruff.toml"),
        *("backend/conftest.py", "backend/tests/api/conftest.py", "scripts/tests/conftest.py"),
        *("scripts/pytest.ini", "frontend/next.config.ts", "frontend/next.config.mjs"),
        *("frontend/eslint.config.js", "frontend/vitest.config.ts", "frontend/vitest.setup.ts"),
        *("frontend/tsconfig.json", "frontend/tsconfig.build.json", "frontend/postcss.config.mjs"),
        *("frontend/tailwind.config.ts", "frontend/scripts/check-client-bundle.ts"),
        *("backend/config/settings/base.py", "backend/config/settings/prod.py"),
        *("AGENTS.md", "CLAUDE.md", "context/01-constitution.md"),
        *(".claude/settings.json", ".claude/agents/reviewer.md", ".agents/roles.md"),
        *("backend/apps/common/pyproject.toml", "frontend/pyproject.toml", "docs/pyproject.toml"),
        *("backend/tests/pytest.ini", "backend/tests/architecture/.pytest.ini", "tox.ini"),
        *("backend/setup.cfg", "backend/apps/common/tox.ini", "frontend/setup.cfg"),
        *("docs/AGENTS.md", "backend/apps/charges/CLAUDE.md", ".mcp.json"),
        *("frontend/pnpm-lock.yaml", ".gitattributes", "frontend/src/.gitattributes"),
        *(".vscode/settings.json", ".vscode/tasks.json"),
    ],
)
def test_Q058_paths_that_can_alter_the_gate_are_red(path: str) -> None:
    assert is_red(path)


@pytest.mark.parametrize(
    "path",
    [
        "docs/notes.md",
        "README.md",
        "docs/AGENTS.md.bak",
        "frontend/src/components/EmptyState.tsx",
        "frontend/src/lib/api-client.ts",  # browser code, not the BFF
        "frontend/src/app/(dashboard)/page.tsx",
        "frontend/src/pnpm-lock.yaml",
        "frontend/src/next.config.ts",
        "backend/apps/common/api/throttling.py",
        "backend/apps/common/health/views.py",
        "backend/config/celery.py",
        "backend/tests/api/test_AC_PLT_34_problem_json.py",
        "backend/apps/charges_report/views.py",  # prefix of a red module, not the module
        "backend/apps/common/migrations_helper.py",
        "xscripts/tool.py",
        "scripts",
        "docs/ruff.toml.md",
        "frontend/src/conftest.py",
        "frontend/src/package.json",
        "specs/06-charges/spec.sdd.md",
        "context/02-glossary.md",
    ],
)
def test_AC_PLT_32_non_red_paths_are_not_red(path: str) -> None:
    assert not is_red(path)


def test_AC_PLT_32_red_path_matching_ignores_case() -> None:
    # Marking too much is cheap; on a case-insensitive checkout these are the red paths.
    assert is_red("Scripts/check_zona_roja.py")
    assert is_red("Backend/apps/charges/models.py")
    assert is_red("docs/agents.md")
    assert is_red("Frontend/PNPM-LOCK.yaml")
    # Exceptions ignore case too: `Backend/Apps/x.py` is still outside the backend/** line.
    assert not is_red("Backend/Apps/common/views.py")
    assert not is_red("DOCS/NOTES.md")


def test_AC_PLT_32_backend_tests_exception_does_not_hide_pytest_config() -> None:
    assert is_red("backend/tests/pytest.ini")
    assert is_red("backend/tests/pyproject.toml")
    assert is_red("backend/apps/common/setup.cfg")


def test_AC_PLT_32_default_rules_file_is_the_repo_list() -> None:
    repo_list = Path(__file__).resolve().parents[2] / ".github" / "zona-roja-paths.txt"
    assert load_rules(repo_list) == RULES
    assert evaluate([RED], [], [], HEAD).red_paths == (RED,)
