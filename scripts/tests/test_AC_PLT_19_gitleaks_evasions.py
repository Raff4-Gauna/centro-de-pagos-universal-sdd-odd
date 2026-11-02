"""AC-PLT-19 (RN-PLT-13, C-06): known ways around gitleaks do not get a secret past it (T-PLT-04).

Found in the review of ``3d50418`` and reproduced there with gitleaks v8.30.1. Marker ``gitleaks``
(Docker); each case runs the real hook ``entry`` and/or the real ``secrets`` steps (see
``gitleaks_support``). Fake secrets are generated at runtime.
"""

from __future__ import annotations

import base64
import re
import secrets
import subprocess
import tomllib
from pathlib import Path

import gitleaks_support as gl
import pytest
from conftest import GitRepo, Scan

pytestmark = pytest.mark.gitleaks
IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@example.invalid")
# The default config is embedded in the binary (go:embed of config/gitleaks.toml).
GLOBAL_ALLOWLIST = re.compile(
    rb'\[allowlist\]\ndescription = "global allow lists"\npaths = \[\n.*?\n\]\n', re.DOTALL
)


def default_path_allowlist() -> list[str]:
    """`[allowlist] paths` of the default config, read from the binary of the pinned image."""
    binary = subprocess.run(  # noqa: S603 - fixed argv, test-only; docker from PATH
        ["docker", "run", "--rm", "--entrypoint", "cat", gl.gitleaks_image(), "/usr/bin/gitleaks"],  # noqa: S607
        capture_output=True,
        check=True,
        timeout=gl.DOCKER_TIMEOUT,
    ).stdout
    found = GLOBAL_ALLOWLIST.search(binary)
    assert found, "global allowlist not found in the gitleaks binary: the format changed"
    return tomllib.loads(found.group(0).decode("utf-8"))["allowlist"]["paths"]


def test_AC_PLT_19_guard_covers_every_directory_entry_of_the_default_allowlist() -> None:
    # B-7: the guard is the default allowlist minus its file-extension entries, verbatim. A newer
    # gitleaks that adds, drops or changes a path entry makes this fail until the guard (and its
    # example in gitleaks_support) follow.
    paths = default_path_allowlist()
    directories = [entry for entry in paths if not gl.is_extension_entry(entry)]
    extensions = [entry for entry in paths if gl.is_extension_entry(entry)]

    assert gl.guard_entries() == directories
    assert list(gl.ALLOWLISTED_PATH_EXAMPLES) == directories
    # Accepted risk (Q-062): images, fonts, binaries the frontend has legitimately; .svg included.
    assert extensions
    assert any("svg" in entry for entry in extensions)


def test_AC_PLT_19_inline_gitleaks_allow_does_not_hide_a_token(scan: Scan) -> None:
    # B-1: a `gitleaks:allow` comment on the line silences the finding unless
    # --ignore-gitleaks-allow is passed.
    token = gl.fake_github_token()
    result = scan(f"GITHUB_TOKEN={token}  # gitleaks:allow\n")

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert token not in output


def test_AC_PLT_19_private_key_with_a_placeholder_inside_is_detected(scan: Scan) -> None:
    # B-5: an unanchored allowlist regex matched the placeholder anywhere in the captured secret,
    # so a multi-line key with a `<ver .env: X>` line in it was allowed.
    key = gl.fake_rsa_private_key(gl.PLACEHOLDER)
    result = scan(key)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "private-key" in output


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


LOCKFILE = "frontend/pnpm-lock.yaml"


def lockfile_body(*extra: str) -> bytes:
    """A small pnpm lockfile with a random integrity hash, plus ``extra`` lines."""
    integrity = base64.b64encode(secrets.token_bytes(64)).decode("ascii")
    lines = [
        "lockfileVersion: '9.0'",
        "packages:",
        "  react@19.2.0:",
        f"    resolution: {{integrity: sha512-{integrity}}}",
        *extra,
    ]
    return "\n".join(lines).encode() + b"\n"


def test_AC_PLT_19_token_in_the_exempt_lockfile_fails_the_lockfile_scan(
    two_commits: tuple[GitRepo, str, str], tmp_path: Path
) -> None:
    # Q-062: `gitleaks git` never scans pnpm-lock.yaml (default path allowlist), so the job scans
    # its diff in the range through stdin, which has no path to allowlist.
    repo, _, head = two_commits
    token = gl.fake_github_token()
    repo.write_bytes(LOCKFILE, lockfile_body(f"    registryToken: {token}"))
    pr_head = gl.commit(repo, "add lockfile")

    main = gl.ci_scan(repo, tmp_path, head, pr_head)
    assert main.returncode == 0, main.stdout + main.stderr  # the hole the extra step closes
    result = gl.ci_scan(repo, tmp_path, head, pr_head, "scan-lockfiles")
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "github-pat" in output
    assert token not in output


@pytest.mark.parametrize("changed_in_range", [True, False], ids=["changed", "unchanged"])
def test_AC_PLT_19_clean_exempt_lockfile_passes_the_lockfile_scan(
    two_commits: tuple[GitRepo, str, str], tmp_path: Path, changed_in_range: bool
) -> None:
    repo, _, head = two_commits
    repo.write_bytes(LOCKFILE, lockfile_body())
    with_lockfile = gl.commit(repo, "add lockfile")
    if changed_in_range:
        start, pr_head = head, with_lockfile
    else:  # the PR touches another file only: empty diff for the lockfile
        repo.write_bytes("notes.txt", b"other change\n")
        start, pr_head = with_lockfile, gl.commit(repo, "touch another file")

    result = gl.ci_scan(repo, tmp_path, start, pr_head, "scan-lockfiles")
    assert result.returncode == 0, result.stdout + result.stderr
