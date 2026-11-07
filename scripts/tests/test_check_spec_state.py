"""Process tooling: ``check_spec_state.py`` detects documented state that git contradicts.

These tests are not tied to an AC of 00-platform: the script is process tooling (see
``context/worklog/2026-11-05-process-stewardship.md``). Each case builds a throwaway git repo with a
minimal spec, tasks table, verification matrix and test file, then calls ``main`` in-process.
"""

from __future__ import annotations

import json
from pathlib import Path

import check_spec_state
import gitleaks_support as gl
import pytest
from conftest import GitRepo

SPEC = """---
id: SPEC-00
estado: Approved
---

## Criterios
- **AC-DEMO-01** el módulo demo existe.
"""

TASKS = """---
spec: SPEC-00
---
# Tareas — demo

## Resumen
| ID | Título | AC | Estado | Evidencia |
|---|---|---|---|---|
{rows}

<!-- check_spec_state:begin -->
| Tarea | PR | SHA | Estado |
|---|---|---|---|
<!-- check_spec_state:end -->
"""

VERIFICATION = """---
spec: SPEC-00
resultado: Con hallazgos
---
# Verificación

| AC | Test | Cobertura |
|---|---|---|
| AC-DEMO-01 | `test_AC_DEMO_01_ok.py` | ✔ |
"""


def row(status: str, evidence: str) -> str:
    return f"| T-DEMO-01 | Demo | AC-DEMO-01 | {status} | {evidence} |"


def build(
    repo: GitRepo,
    *,
    status: str = "✅",
    evidence: str | None = None,
    commit_task: bool = True,
    ac_test: bool = True,
    verification: bool = True,
    state: str = "Approved",
) -> str:
    """Write the fixture files; return the SHA of the commit that names T-DEMO-01."""
    spec = SPEC.replace("estado: Approved", f"estado: {state}")
    repo.write_bytes("specs/00-demo/spec.sdd.md", spec.encode("utf-8"))
    if ac_test:
        repo.write_bytes("scripts/tests/test_AC_DEMO_01_ok.py", b'"""AC-DEMO-01"""\n')
    if verification:
        repo.write_bytes("specs/00-demo/verification.md", VERIFICATION.encode("utf-8"))
    sha = gl.commit(repo, "feat: demo (T-DEMO-01) (#7)" if commit_task else "docs: init")
    if evidence is None:
        evidence = f"#7 · {sha[:7]}" if commit_task else "—"
    repo.write_bytes("specs/00-demo/tasks.md", TASKS.format(rows=row(status, evidence)).encode())
    gl.commit(repo, "docs: tasks")
    return sha


def baseline(tmp_path: Path, data: dict[str, object] | None = None) -> Path:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(data or {}), encoding="utf-8")
    return path


def run(repo: GitRepo, baseline_path: Path, *args: str) -> int:
    return check_spec_state.main(
        ["--root", str(repo.root), "--baseline", str(baseline_path), *args]
    )


def test_clean_state_exits_0(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    build(git_repo)
    assert run(git_repo, baseline(tmp_path)) == 0
    assert "OK: sin drift" in capsys.readouterr().out


def test_merged_task_left_pending_fails(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    build(git_repo, status="☐", evidence="—")
    assert run(git_repo, baseline(tmp_path)) == 1
    assert "mergeada en git" in capsys.readouterr().out


def test_done_without_a_commit_fails(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    build(git_repo, status="✅", evidence="#7 · deadbeef", commit_task=False)
    assert run(git_repo, baseline(tmp_path)) == 1
    assert "no hay commit que la nombre" in capsys.readouterr().out


def test_done_without_evidence_fails(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    build(git_repo, status="✅", evidence="—")
    assert run(git_repo, baseline(tmp_path)) == 1
    assert "sin PR y SHA" in capsys.readouterr().out


def test_evidence_with_wrong_pr_fails(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    sha = build(git_repo)
    git_repo.write_bytes(
        "specs/00-demo/tasks.md",
        TASKS.format(rows=row("✅", f"#99 · {sha[:7]}")).encode("utf-8"),
    )
    gl.commit(git_repo, "docs: wrong evidence")
    assert run(git_repo, baseline(tmp_path)) == 1
    assert "pero git dice #7" in capsys.readouterr().out


def test_verified_without_verification_fails(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    build(git_repo, status="🧪", verification=False)
    assert run(git_repo, baseline(tmp_path)) == 1
    assert "🧪 sin verification.md" in capsys.readouterr().out


def test_missing_ac_test_fails(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    build(git_repo, status="☐", evidence="—", commit_task=False, ac_test=False)
    assert run(git_repo, baseline(tmp_path)) == 1
    assert "AC-DEMO-01: sin test" in capsys.readouterr().out


def test_baseline_allows_known_missing_ac(git_repo: GitRepo, tmp_path: Path) -> None:
    build(git_repo, status="☐", evidence="—", commit_task=False, ac_test=False)
    data: dict[str, object] = {"00-demo": {"allow_missing_tests": ["AC-DEMO-01"]}}
    assert run(git_repo, baseline(tmp_path, data)) == 0


def squash_without_id(repo: GitRepo) -> tuple[str, str]:
    """A merged task whose squash names only the PR; return its SHA and the one of HEAD."""
    build(repo, evidence="#7 · 0000000", commit_task=False)
    repo.write_bytes("feature.txt", b"demo\n")
    sha = gl.commit(repo, "feat: demo (#7)")
    tasks = TASKS.format(rows=row("✅", f"#7 · {sha[:7]}"))
    repo.write_bytes("specs/00-demo/tasks.md", tasks.encode())
    return sha, gl.commit(repo, "docs: tasks")


def link(tmp_path: Path, value: object) -> Path:
    return baseline(tmp_path, {"squashed_without_id": {"T-DEMO-01": value}})


def test_squash_without_id_fails_without_a_baseline_entry(
    git_repo: GitRepo, tmp_path: Path, capsys
) -> None:
    squash_without_id(git_repo)
    assert run(git_repo, baseline(tmp_path)) == 1
    assert "no hay commit que la nombre" in capsys.readouterr().out


def test_squash_without_id_is_linked_by_the_baseline(git_repo: GitRepo, tmp_path: Path) -> None:
    sha, _ = squash_without_id(git_repo)
    assert run(git_repo, link(tmp_path, sha)) == 0


def test_squash_entry_with_an_unknown_sha_is_an_error(
    git_repo: GitRepo, tmp_path: Path, capsys
) -> None:
    squash_without_id(git_repo)
    assert run(git_repo, link(tmp_path, "0" * 40)) == 2
    assert "no es un merge con PR" in capsys.readouterr().err


def test_squash_entry_on_a_commit_without_pr_is_an_error(git_repo: GitRepo, tmp_path: Path) -> None:
    _, head = squash_without_id(git_repo)
    assert run(git_repo, link(tmp_path, head)) == 2


@pytest.mark.parametrize("value", ["short", "ref", "HEAD", "tag", "path", 7])
def test_squash_entry_must_be_a_full_sha(
    git_repo: GitRepo, tmp_path: Path, capsys, value: object
) -> None:
    sha, _ = squash_without_id(git_repo)
    git_repo.git("tag", "v-demo", sha)
    given = (
        {
            "short": sha[:7],
            "ref": "HEAD~1",
            "HEAD": "HEAD",
            "tag": "v-demo",
            "path": "feature.txt",
        }.get(value, value)
        if isinstance(value, str)
        else value
    )
    assert run(git_repo, link(tmp_path, given)) == 2
    assert "no es un SHA completo" in capsys.readouterr().err


def test_squash_entry_on_an_unmerged_branch_is_an_error(
    git_repo: GitRepo, tmp_path: Path, capsys
) -> None:
    squash_without_id(git_repo)
    git_repo.git("checkout", "-q", "-b", "side")
    git_repo.write_bytes("side.txt", b"side\n")
    side = gl.commit(git_repo, "feat: never merged (#99)")
    git_repo.git("checkout", "-q", "-")
    assert run(git_repo, link(tmp_path, side)) == 2
    assert "no es un merge con PR en main" in capsys.readouterr().err


def test_commit_without_pr_does_not_override_a_linked_merge(
    git_repo: GitRepo, tmp_path: Path
) -> None:
    sha, _ = squash_without_id(git_repo)
    git_repo.write_bytes("note.txt", b"note\n")
    gl.commit(git_repo, "docs: mention T-DEMO-01")
    assert run(git_repo, link(tmp_path, sha)) == 0


def test_implemented_without_verification_fails(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    build(
        git_repo,
        status="☐",
        evidence="—",
        commit_task=False,
        verification=False,
        state="Implemented",
    )
    assert run(git_repo, baseline(tmp_path)) == 1
    assert "Implemented sin verification.md" in capsys.readouterr().out


def test_verification_with_unknown_ac_fails(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    build(git_repo)
    git_repo.write_bytes(
        "specs/00-demo/verification.md",
        VERIFICATION.replace("AC-DEMO-01 | `test", "AC-DEMO-99 | `test").encode("utf-8"),
    )
    gl.commit(git_repo, "docs: stale verification")
    assert run(git_repo, baseline(tmp_path)) == 1
    assert "AC-DEMO-99" in capsys.readouterr().out


def test_blocked_without_question_fails(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    build(git_repo, status="⛔", evidence="—", commit_task=False)
    assert run(git_repo, baseline(tmp_path)) == 1
    assert "⛔ sin Q-xxx" in capsys.readouterr().out


def test_blocked_with_question_passes(git_repo: GitRepo, tmp_path: Path) -> None:
    build(git_repo, status="⛔", evidence="Q-048", commit_task=False)
    assert run(git_repo, baseline(tmp_path)) == 0


def test_invalid_status_fails(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    build(git_repo, status="en revisión", evidence="—", commit_task=False)
    assert run(git_repo, baseline(tmp_path)) == 1
    assert "estado inválido" in capsys.readouterr().out


def test_write_regenerates_conciliation(git_repo: GitRepo, tmp_path: Path) -> None:
    sha = build(git_repo)
    assert run(git_repo, baseline(tmp_path), "--write") == 0
    tasks = (git_repo.root / "specs/00-demo/tasks.md").read_text(encoding="utf-8")
    assert f"| T-DEMO-01 | #7 | {sha[:7]} | ✅ |" in tasks


def test_spec_without_tasks_exits_2(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    git_repo.write_bytes("specs/00-demo/spec.sdd.md", SPEC.encode("utf-8"))
    gl.commit(git_repo, "docs: init")
    assert run(git_repo, baseline(tmp_path)) == 2
    assert "ninguna spec tiene tasks.md" in capsys.readouterr().err


def test_unknown_spec_exits_2(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    build(git_repo)
    assert run(git_repo, baseline(tmp_path), "--spec", "99-nope") == 2
    assert "no existe specs/99-nope" in capsys.readouterr().err
