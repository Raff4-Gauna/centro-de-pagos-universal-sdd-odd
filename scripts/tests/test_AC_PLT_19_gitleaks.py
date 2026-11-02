"""AC-PLT-19 (RN-PLT-13, C-06): gitleaks blocks a token-shaped secret, not a placeholder (T-PLT-04).

Marker ``gitleaks`` (Docker, the image pinned in ``ci.yml``): deselected by default in
``scripts/pytest.ini``; the ``secrets`` job runs them with ``-m gitleaks``. Each case runs the real
commands both ways (fixture ``scan``): the pre-commit hook's ``entry`` on the staged diff, and the
``range`` + ``scan`` steps of the job on a PR. Fake secrets are generated at runtime, so the repo
never holds one (gitleaks would flag its own tests). The same-line case proves the placeholder
allowlist does not hide a real token next to it (it would with ``regexTarget = "line"``).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import gitleaks_support as gl
import pytest
from conftest import Scan, clean_git_env

pytestmark = pytest.mark.gitleaks


def test_AC_PLT_19_token_shaped_secret_is_detected(scan: Scan) -> None:
    token = gl.fake_github_token()
    result = scan(f"GITHUB_TOKEN={token}\n")

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "github-pat" in output
    assert token not in output  # --redact


def test_AC_PLT_19_env_placeholder_is_not_flagged(scan: Scan) -> None:
    placeholder = gl.PLACEHOLDER
    result = scan(
        f"MP_ACCESS_TOKEN={placeholder}\n| Access Token (prueba) | `{placeholder}` |\n"
        f'access_token = "{placeholder}"\n'
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_AC_PLT_19_placeholder_and_real_token_on_same_line_still_fails(scan: Scan) -> None:
    token = gl.fake_github_token()
    result = scan(f"MP_ACCESS_TOKEN={gl.PLACEHOLDER} GITHUB_TOKEN={token}\n")

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert token not in output


@pytest.mark.parametrize("prefix", ["APP_USR", "TEST"])
def test_AC_PLT_19_mercadopago_token_is_detected_in_every_form(scan: Scan, prefix: str) -> None:
    token = gl.fake_mp_token(prefix)
    forms = [
        f"MP_ACCESS_TOKEN={token}",
        f'curl -H "Authorization: Bearer {token}"',
        f'{{"access_token": "{token}"}}',
        f"https://api.mercadopago.com/pos?access_token={token}",
    ]
    result = scan("".join(f"{form}\n" for form in forms))

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert len(re.findall(r"RuleID:\s+mercadopago-access-token", output)) == len(forms), output
    assert token not in output


def test_AC_PLT_19_repo_history_has_no_findings(tmp_path: Path, empty_git_config: Path) -> None:
    # Every commit of every ref (with fetch-depth 0 in CI): the own rule and the allowlist give no
    # false positives on the real content, placeholders included.
    history = subprocess.run(
        ["git", "log", "-p", "--all", "--no-color", "--no-ext-diff"],  # noqa: S607 - git from PATH
        cwd=gl.REPO_ROOT,
        capture_output=True,
        check=True,
        env=clean_git_env(empty_git_config),
    ).stdout
    assert history
    config_dir = tmp_path / "gitleaks-config"
    config_dir.mkdir()
    shutil.copyfile(gl.GITLEAKS_CONFIG, config_dir / ".gitleaks.toml")
    docker = ["docker", "run", "--rm", "-i", "-v", f"{config_dir}:/cfg:ro"]
    options = ["--config", "/cfg/.gitleaks.toml", "--redact", "--no-banner", "--verbose"]
    result = subprocess.run(  # noqa: S603 - fixed argv, test-only; docker from PATH
        [*docker, gl.gitleaks_image(), "stdin", *options],
        input=history,
        capture_output=True,
        check=False,
        timeout=gl.DOCKER_TIMEOUT,
    )
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    assert result.returncode == 0, output
