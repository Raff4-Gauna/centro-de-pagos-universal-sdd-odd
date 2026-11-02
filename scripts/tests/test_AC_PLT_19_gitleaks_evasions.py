"""AC-PLT-19 (RN-PLT-13, C-06): known ways around gitleaks do not get a secret past it (T-PLT-04).

Found in the review of ``3d50418`` and reproduced there with gitleaks v8.30.1. Marker ``gitleaks``
(Docker); each case runs the real hook ``entry`` and/or the real ``secrets`` steps (see
``gitleaks_support``). Fake secrets are generated at runtime.
"""

from __future__ import annotations

from pathlib import Path

import gitleaks_support as gl
import pytest
from conftest import GitRepo, Scan

pytestmark = pytest.mark.gitleaks
IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@example.invalid")


def test_AC_PLT_19_inline_gitleaks_allow_does_not_hide_a_token(scan: Scan) -> None:
    # B-1: a `gitleaks:allow` comment on the line silences the finding unless
    # --ignore-gitleaks-allow is passed.
    token = gl.fake_github_token()
    result = scan(f"GITHUB_TOKEN={token}  # gitleaks:allow\n")

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert token not in output


def test_AC_PLT_19_secret_added_only_by_a_merge_commit_is_detected(
    two_commits: tuple[GitRepo, str, str], tmp_path: Path
) -> None:
    # B-3: `git log -p` prints no diff for a merge, so an "evil merge" that adds a file while
    # merging would never be scanned (--diff-merges=first-parent).
    repo, _, head = two_commits
    repo.git("checkout", "-q", "-b", "side")
    repo.write_bytes("side.txt", b"side work\n")
    gl.commit(repo, "side work")
    repo.git("checkout", "-q", "-")
    repo.git(*IDENTITY, "merge", "-q", "--no-ff", "--no-commit", "side")
    token = gl.fake_github_token()
    repo.write_bytes("evil.txt", f"GITHUB_TOKEN={token}\n".encode())
    merge = gl.commit(repo, "merge side")

    result = gl.ci_scan(repo, tmp_path, head, merge)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert token not in output


@pytest.mark.parametrize("case", ["diff-attribute", "nul-byte"])
def test_AC_PLT_19_secret_in_a_file_git_treats_as_binary_is_detected(
    two_commits: tuple[GitRepo, str, str], tmp_path: Path, case: str
) -> None:
    # B-4: `-diff` in .gitattributes or a NUL byte makes `git log -p` print "Binary files differ"
    # instead of the content (--text).
    repo, _, head = two_commits
    token = gl.fake_github_token()
    content = f"GITHUB_TOKEN={token}\n".encode()
    if case == "diff-attribute":
        repo.write_bytes(".gitattributes", b"settings.cfg -diff\n")
        repo.write_bytes("settings.cfg", content)
    else:
        repo.write_bytes("notes.bin.txt", content + b"\x00\n")
    pr_head = gl.commit(repo, "add settings")

    result = gl.ci_scan(repo, tmp_path, head, pr_head)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert token not in output
