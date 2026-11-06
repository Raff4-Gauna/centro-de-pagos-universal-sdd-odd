"""AC-PLT-25 / AC-PLT-29 (RN-PLT-14, RNF-PLT-01, Q-049): the CI ``build`` job (T-PLT-37).

Static checks of the two ``build-push-action`` steps and of ``infra/docker-compose.ci.yml``, plus
the real ``run:`` of the tag and image steps under bash, with a fake ``docker``: a tag step that
stops validating or a uid check that stops failing shows up here. The build itself only runs in the
job. Where it sits in the chain: ``test_AC_PLT_20_pipeline_chain.py``.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from gitleaks_support import find_bash

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CI_OVERRIDE = REPO_ROOT / "infra" / "docker-compose.ci.yml"
SHA = "a" * 40
IMAGE_CHECK = "Images carry the commit SHA and do not run as root"
RESET = object()


class ComposeLoader(yaml.SafeLoader):
    """SafeLoader that knows the ``!reset`` tag of Compose (drops the base file's value)."""


ComposeLoader.add_constructor("!reset", lambda *_: RESET)


def load_override() -> dict[str, Any]:
    text = CI_OVERRIDE.read_text(encoding="utf-8")
    return yaml.load(text, Loader=ComposeLoader)  # noqa: S506 - a SafeLoader subclass


def build_job() -> dict[str, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["build"]


def build_steps() -> dict[str, dict[str, Any]]:
    return {step.get("name") or step["uses"]: step for step in build_job()["steps"]}


def run_build_step(
    name: str, tmp_path: Path, env: dict[str, str], prelude: str = ""
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    """Run a ``run:`` of the ``build`` job like the runner; ``prelude`` can define a fake docker."""
    script = tmp_path / "step.sh"
    script.write_text(f"{prelude}\n{build_steps()[name]['run']}", encoding="utf-8", newline="\n")
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    full_env = {**os.environ, "GIT_SHA": SHA, **env, "GITHUB_OUTPUT": output.as_posix()}
    completed = subprocess.run(  # noqa: S603 - fixed argv, test-only
        [find_bash(), "--noprofile", "--norc", "-eo", "pipefail", script.as_posix()],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=full_env,
        check=False,
    )
    lines = output.read_text(encoding="utf-8").splitlines()
    return completed, dict(line.split("=", 1) for line in lines if line)


def fake_docker(uid: str, revision: str = SHA) -> str:
    return f'docker() {{ if [ "$1" = run ]; then echo "{uid}"; else echo "{revision}"; fi; }}'


@pytest.mark.parametrize("component", ["backend", "frontend"])
def test_AC_PLT_25_build_job_builds_runtime_image_without_pushing(component: str) -> None:
    step = build_steps()[f"Build {component} image"]
    assert step["uses"].startswith("docker/build-push-action@")
    inputs = step["with"]
    assert inputs["context"] == component
    assert inputs["target"] == "runtime"
    # Q-049: built and loaded on the runner, never published.
    assert inputs["push"] is False
    assert inputs["load"] is True
    assert inputs["build-args"] == "GIT_SHA=${{ env.GIT_SHA }}"
    assert inputs["tags"] == f"${{{{ steps.tags.outputs.{component} }}}}"
    assert inputs["cache-from"] == f"type=gha,scope={component}"
    assert inputs["cache-to"] == f"type=gha,mode=max,scope={component}"


def test_AC_PLT_25_build_job_tags_the_commit_built() -> None:
    # github.sha is what actions/checkout built: on a PR, the merge commit.
    assert build_job()["env"]["GIT_SHA"] == "${{ github.sha }}"


def test_AC_PLT_25_buildkit_is_pinned_by_digest() -> None:
    setup = next(s for name, s in build_steps().items() if "setup-buildx-action" in name)
    pinned = r"image=moby/buildkit:v[\d.]+@sha256:[0-9a-f]{64}"
    assert re.fullmatch(pinned, setup["with"]["driver-opts"])


@pytest.mark.parametrize(
    ("ref_type", "ref_name", "versioned"),
    [
        ("branch", "42/merge", False),
        ("branch", "main", False),
        ("tag", "v1.2.3", True),
        # `v*` triggers the workflow, but only vX.Y.Z is a version (Q-049).
        ("tag", "v1", False),
        ("tag", "v1.2.3-rc1", False),
        ("tag", "vault", False),
    ],
)
def test_AC_PLT_25_image_tags(
    ref_type: str, ref_name: str, versioned: bool, tmp_path: Path
) -> None:
    completed, outputs = run_build_step(
        "Image tags", tmp_path, {"REF_TYPE": ref_type, "REF_NAME": ref_name}
    )
    assert completed.returncode == 0, completed.stderr
    for component in ("backend", "frontend"):
        expected = [f"hub-{component}:{SHA}"]
        if versioned:
            expected.append(f"hub-{component}:{ref_name}")
        assert outputs[component].split(",") == expected


def test_AC_PLT_25_image_tags_reject_a_value_that_is_not_a_sha(tmp_path: Path) -> None:
    env = {"GIT_SHA": "main", "REF_TYPE": "branch", "REF_NAME": "main"}
    completed, outputs = run_build_step("Image tags", tmp_path, env)
    assert completed.returncode != 0
    assert outputs == {}


@pytest.mark.parametrize("uid", ["10001", "1000"])
def test_AC_PLT_25_image_not_root_passes(uid: str, tmp_path: Path) -> None:
    completed, _ = run_build_step(IMAGE_CHECK, tmp_path, {}, fake_docker(uid))
    assert completed.returncode == 0, completed.stdout + completed.stderr


# "" and a non-number: an image whose `id -u` printed nothing proves nothing (fail closed).
@pytest.mark.parametrize("uid", ["0", "", "root"])
def test_AC_PLT_25_image_running_as_root_fails_the_job(uid: str, tmp_path: Path) -> None:
    completed, _ = run_build_step(IMAGE_CHECK, tmp_path, {}, fake_docker(uid))
    assert completed.returncode != 0
    assert "::error::" in completed.stdout


@pytest.mark.parametrize("revision", ["0" * 40, ""])
def test_AC_PLT_25_image_without_the_commit_sha_fails_the_job(
    revision: str, tmp_path: Path
) -> None:
    completed, _ = run_build_step(IMAGE_CHECK, tmp_path, {}, fake_docker("10001", revision))
    assert completed.returncode != 0
    assert "::error::" in completed.stdout


def test_AC_PLT_29_build_job_runs_the_bundle_check_of_the_builder_stage() -> None:
    # BuildKit only runs the stages the target needs: the check lives in `builder`, so it runs (and
    # its failure stops the build, with no continue-on-error) because `runtime` copies from it.
    assert build_steps()["Build frontend image"]["with"]["target"] == "runtime"
    dockerfile = (REPO_ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY --from=builder " in dockerfile.split(" AS runtime", 1)[1]
    builder = dockerfile.split(" AS builder", 1)[1].split("\nFROM ", 1)[0]
    assert "check-client-bundle.ts" in builder


def test_AC_PLT_25_ci_override_uses_sha_tagged_runtime_images() -> None:
    services = load_override()["services"]
    assert set(services) == {"db", "backend", "worker", "beat", "frontend"}
    for name, repository in (
        ("backend", "hub-backend"),
        ("worker", "hub-backend"),
        ("beat", "hub-backend"),
        ("frontend", "hub-frontend"),
    ):
        service = services[name]
        # GIT_SHA is required: an unset one stops Compose instead of naming the wrong image.
        assert re.fullmatch(rf"{repository}:\$\{{GIT_SHA:\?[^}}]+\}}", service["image"]), name
        # No bind mount of the source: the stack runs what the job built.
        assert service["volumes"] is RESET, name
        assert "env_file" not in service, name
    # Nothing rebuilds a missing image (worker and beat have no build in the base file).
    assert services["backend"]["build"] is RESET
    assert services["frontend"]["build"] is RESET


def test_AC_PLT_25_ci_override_runs_prod_settings_with_fictitious_values() -> None:
    services = load_override()["services"]
    assert services["db"]["ports"] is RESET
    credentials = services["db"]["environment"]
    database = (
        f"postgres://{credentials['POSTGRES_USER']}:{credentials['POSTGRES_PASSWORD']}"
        f"@db:5432/{credentials['POSTGRES_DB']}"
    )
    for name in ("backend", "worker", "beat"):
        env = services[name]["environment"]
        assert env["DJANGO_SETTINGS_MODULE"] == "config.settings.prod"
        assert env["DJANGO_DEBUG"] == "false"
        assert env["DJANGO_SECRET_KEY"].startswith("ci-only-not-a-secret")
        assert len(env["DJANGO_SECRET_KEY"]) >= 50  # ProdEnv refuses a shorter one
        assert {"localhost", "backend"} <= set(env["DJANGO_ALLOWED_HOSTS"].split(","))
        assert env["DATABASE_URL"] == database
        assert env["REDIS_URL"] == "redis://redis:6379/0"
        # The base file passes an empty APP_VERSION, which would hide the one of the image.
        assert env["APP_VERSION"].startswith("${GIT_SHA:?")
    # The dev commands (gunicorn --reload, next dev) stay out.
    backend_command = " ".join(services["backend"]["command"])
    assert "gunicorn -c config/gunicorn.conf.py config.wsgi" in backend_command
    assert "--reload" not in backend_command
    assert services["frontend"]["command"] == ["node", "server.js"]
