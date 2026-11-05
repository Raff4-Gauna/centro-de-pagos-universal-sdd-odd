"""AC-PLT-25 (RN-PLT-14, RNF-PLT-01, T-PLT-25, T-PLT-36): the images, read statically.

``backend/Dockerfile`` installs only from the frozen ``uv.lock``, pins every base image by tag and
digest, ships no dev group nor ``tests/`` in ``runtime``, runs as uid 10001 and carries the commit
SHA (``APP_VERSION`` and the OCI ``revision`` label). ``frontend/Dockerfile`` installs only from the
frozen ``pnpm-lock.yaml`` with the CI flags, builds with sentinels and runs the client bundle check
(AC-PLT-29), and its ``runtime`` is the standalone output run by ``node``. Both ``.dockerignore``
keep ``.env*`` and ``.git`` out of the build context. The build itself and ``id -u`` run in the CI
``build`` job.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
FRONTEND = REPO_ROOT / "frontend"

PYTHON_IMAGE = "python:3.12.16-slim-trixie"
UV_IMAGE = "ghcr.io/astral-sh/uv:0.13.6"
NODE_IMAGE = "node:24.22.2-trixie-slim"
PNPM_INSTALL = ["pnpm", "install", "--frozen-lockfile", "--ignore-scripts", "--ignore-pnpmfile"]
PNPM_STORE = "/pnpm-store"
DIGEST = re.compile(r"^(?P<name>[^@\s]+:[^@\s:/]+)@sha256:[0-9a-f]{64}$")
APP_UID = "10001"
RUNTIME_SOURCES = {"apps/", "config/", "manage.py"}


@dataclass
class Stage:
    image: str
    name: str
    instructions: list[tuple[str, str]] = field(default_factory=list)

    def args(self, keyword: str) -> list[str]:
        return [args for kw, args in self.instructions if kw == keyword]

    def env(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for args in self.args("ENV"):
            for word in shlex.split(args):
                key, _, value = word.partition("=")
                values[key] = value
        return values


def instructions(text: str) -> list[tuple[str, str]]:
    """``(KEYWORD, arguments)`` per instruction: comments dropped, continuations joined."""
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    joined = "\n".join(lines).replace("\\\n", " ")
    result = []
    for line in joined.splitlines():
        if line.strip():
            keyword, _, args = line.strip().partition(" ")
            result.append((keyword.upper(), " ".join(args.split())))
    return result


def stages(text: str) -> list[Stage]:
    result: list[Stage] = []
    for keyword, args in instructions(text):
        if keyword == "FROM":
            words = args.split()
            assert len(words) == 3, f"unnamed stage: FROM {args}"
            assert words[1].upper() == "AS", f"unnamed stage: FROM {args}"
            result.append(Stage(image=words[0], name=words[2]))
        else:
            assert result, f"{keyword} before the first FROM"
            result[-1].instructions.append((keyword, args))
    return result


def stages_by_name(dockerfile: Path) -> dict[str, Stage]:
    parsed = stages(dockerfile.read_text(encoding="utf-8"))
    by_name = {stage.name: stage for stage in parsed}
    assert len(by_name) == len(parsed), "duplicate stage names"
    # The default target (no --target) must be the production one.
    assert parsed[-1].name == "runtime"
    return by_name


@pytest.fixture(scope="module")
def backend_stages() -> dict[str, Stage]:
    return stages_by_name(BACKEND / "Dockerfile")


@pytest.fixture(scope="module")
def frontend_stages() -> dict[str, Stage]:
    return stages_by_name(FRONTEND / "Dockerfile")


def external_images(by_name: dict[str, Stage]) -> list[str]:
    """Every image pulled from a registry: ``FROM`` and ``COPY --from`` that are not stages."""
    names = set(by_name)
    external = [stage.image for stage in by_name.values() if stage.image not in names]
    external += [
        source
        for stage in by_name.values()
        for source, _ in map(copy_from, stage.args("COPY"))
        if source is not None and source not in names
    ]
    assert external, "no base image found"
    return external


def copy_from(args: str) -> tuple[str | None, list[str]]:
    """``COPY`` arguments -> (``--from`` value or None, sources); other flags dropped."""
    words = shlex.split(args)
    source = next((w.split("=", 1)[1] for w in words if w.startswith("--from=")), None)
    paths = [w for w in words if not w.startswith("--")]
    return source, paths[:-1]


def uv_commands(stage: Stage) -> list[list[str]]:
    commands = []
    for args in stage.args("RUN"):
        for part in re.split(r"&&|;", args):
            words = part.split()
            if "uv" in words:
                commands.append(words[words.index("uv") :])
    return commands


def test_AC_PLT_25_backend_installs_from_frozen_lock(backend_stages: dict[str, Stage]) -> None:
    builder = backend_stages["builder"]
    # pyproject.toml + uv.lock are copied before the first sync (dependency layer cached).
    copies = [copy_from(args) for args in builder.args("COPY")]
    assert (None, ["pyproject.toml", "uv.lock"]) in copies
    assert uv_commands(builder) == [["uv", "sync", "--frozen", "--no-dev", "--no-install-project"]]
    assert uv_commands(backend_stages["dev"]) == [
        ["uv", "sync", "--frozen", "--no-install-project"]
    ]
    assert builder.env()["UV_PYTHON_DOWNLOADS"] == "never"
    assert builder.env()["UV_PROJECT_ENVIRONMENT"] == "/opt/venv"
    # Nothing installs around the lock: no pip, no `uv pip`/`uv add`/`uv lock`.
    for stage in backend_stages.values():
        for args in stage.args("RUN"):
            assert "pip " not in args, (stage.name, args)
            assert "pip3 " not in args, (stage.name, args)
        for command in uv_commands(stage):
            assert command[1] == "sync", (stage.name, command)
            assert "--frozen" in command, (stage.name, command)


def test_AC_PLT_25_backend_runtime_user_is_not_root(backend_stages: dict[str, Stage]) -> None:
    runtime = backend_stages["runtime"]
    users = runtime.args("USER")
    assert users == [f"{APP_UID}:{APP_UID}"]
    # The USER comes before the CMD, and nothing runs as root after it.
    keywords = [kw for kw, _ in runtime.instructions]
    assert keywords.index("USER") < keywords.index("CMD")
    assert "RUN" not in keywords[keywords.index("USER") :]
    created = " ".join(runtime.args("RUN"))
    assert f"--gid {APP_UID} app" in created
    assert f"--uid {APP_UID} --gid app" in created


@pytest.mark.parametrize("component", [BACKEND, FRONTEND], ids=["backend", "frontend"])
def test_AC_PLT_25_base_images_pinned_by_digest(component: Path) -> None:
    for image in external_images(stages_by_name(component / "Dockerfile")):
        match = DIGEST.fullmatch(image)
        assert match, f"not pinned by tag + digest: {image}"
        assert not match["name"].endswith(":latest"), image


def test_AC_PLT_25_backend_base_images(backend_stages: dict[str, Stage]) -> None:
    assert backend_stages["uv"].image.split("@")[0] == UV_IMAGE
    # builder and runtime share the same Python: /opt/venv points at its interpreter.
    assert backend_stages["builder"].image.split("@")[0] == PYTHON_IMAGE
    assert backend_stages["runtime"].image == backend_stages["builder"].image


def test_AC_PLT_25_backend_image_carries_git_sha(backend_stages: dict[str, Stage]) -> None:
    runtime = backend_stages["runtime"]
    assert runtime.args("ARG") == ["GIT_SHA"]
    assert runtime.env()["APP_VERSION"] == "${GIT_SHA}"
    assert runtime.args("LABEL") == ["org.opencontainers.image.revision=${GIT_SHA}"]


def test_AC_PLT_25_backend_runtime_defaults_to_prod_settings(
    backend_stages: dict[str, Stage],
) -> None:
    # manage.py inside the container must not fall back to dev (T-PLT-08 review N-5).
    runtime = backend_stages["runtime"]
    assert runtime.env()["DJANGO_SETTINGS_MODULE"] == "config.settings.prod"
    assert runtime.args("CMD") == ['["gunicorn", "-c", "config/gunicorn.conf.py", "config.wsgi"]']


def test_RNF_PLT_01_runtime_has_no_dev_group_nor_tests(backend_stages: dict[str, Stage]) -> None:
    runtime = backend_stages["runtime"]
    # A fresh base image, not built on top of the stages that hold uv or the dev group.
    assert runtime.image not in backend_stages
    copies = [copy_from(args) for args in runtime.args("COPY")]
    assert copies[0] == ("builder", ["/opt/venv"])
    sources = {path for source, paths in copies[1:] for path in paths if source is None}
    assert sources == RUNTIME_SOURCES
    assert all(source in {None, "builder"} for source, _ in copies)
    assert uv_commands(runtime) == []
    # builder (what runtime copies) installs without the dev group; only dev adds it.
    assert "--no-dev" in uv_commands(backend_stages["builder"])[0]
    assert backend_stages["dev"].image == "builder"


def pnpm_commands(stage: Stage) -> list[list[str]]:
    commands = []
    for args in stage.args("RUN"):
        for part in re.split(r"&&|;", args):
            words = [w for w in part.split() if not w.startswith("--mount=")]
            if "pnpm" in words:
                commands.append(words[words.index("pnpm") :])
    return commands


def test_AC_PLT_25_frontend_frozen_lockfile_and_non_root(
    frontend_stages: dict[str, Stage],
) -> None:
    deps = frontend_stages["deps"]
    # The manifests are copied before the install (dependency layer cached), the source after.
    copies = [copy_from(args) for args in deps.args("COPY")]
    assert copies == [(None, ["package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml"])]
    assert pnpm_commands(deps) == [PNPM_INSTALL]
    # The same flags as the CI install (.github/actions/setup/action.yml, T-PLT-28 review B-2).
    action = (REPO_ROOT / ".github" / "actions" / "setup" / "action.yml").read_text("utf-8")
    assert f"run: {' '.join(PNPM_INSTALL)}" in action
    # Nothing installs around the lock: no npm/yarn, no other pnpm install nor `pnpm add`.
    for stage in frontend_stages.values():
        for args in stage.args("RUN"):
            assert not re.search(r"\b(npm|npx|yarn)\b", args), (stage.name, args)
        for command in pnpm_commands(stage):
            assert command[1] in {"install", "build"}, (stage.name, command)
            if command[1] == "install":
                assert command == PNPM_INSTALL, (stage.name, command)
    # runtime: a fresh base image, the standalone output only, run by the image's node user.
    runtime = frontend_stages["runtime"]
    assert runtime.image == frontend_stages["base"].image
    assert frontend_stages["base"].image.split("@")[0] == NODE_IMAGE
    assert [copy_from(args) for args in runtime.args("COPY")] == [
        ("builder", ["/repo/frontend/.next/standalone"]),
        ("builder", ["/repo/frontend/.next/static"]),
    ]
    assert runtime.args("USER") == ["node"]
    keywords = [kw for kw, _ in runtime.instructions]
    assert keywords.index("USER") < keywords.index("CMD")
    assert "RUN" not in keywords
    assert runtime.args("CMD") == ['["node", "server.js"]']
    assert runtime.env()["NODE_ENV"] == "production"
    assert runtime.args("ARG") == ["GIT_SHA"]
    assert runtime.args("LABEL") == ["org.opencontainers.image.revision=${GIT_SHA}"]


def test_AC_PLT_29_builder_checks_the_bundle_built_with_sentinels(
    frontend_stages: dict[str, Stage],
) -> None:
    script = (FRONTEND / "scripts" / "check-client-bundle.ts").read_text(encoding="utf-8")
    listed = re.search(r"SERVER_ONLY_VARIABLES: readonly string\[\] = \[([^\]]*)\]", script)
    assert listed, "SERVER_ONLY_VARIABLES not found"
    server_only = set(re.findall(r'"([A-Z][A-Z0-9_]*)"', listed[1]))
    assert server_only == {"BACKEND_INTERNAL_URL"}
    builder = frontend_stages["builder"]
    assert builder.image == "deps"
    env = builder.env()
    for name in sorted(server_only):
        # A sentinel under the reserved .invalid TLD: recognizable, never a real address.
        assert re.fullmatch(r"https?://bundle-sentinel-[a-z0-9-]+\.invalid(:\d+)?", env[name]), name
    assert builder.args("RUN") == ["pnpm build && node scripts/check-client-bundle.ts .next"]
    # The sentinels stay in the builder: runtime starts from a fresh image.
    for name in server_only:
        assert name not in frontend_stages["runtime"].env(), name


def test_RNF_PLT_01_frontend_pnpm_store_outside_the_project(
    frontend_stages: dict[str, Stage],
) -> None:
    # pnpm 12 reads pnpm_config_store_dir (not npm_config_*): else .pnpm-store/ lands in the
    # bind-mounted tree.
    assert frontend_stages["base"].env()["pnpm_config_store_dir"] == PNPM_STORE
    assert frontend_stages["base"].args("RUN") == ["corepack enable"]
    (install,) = frontend_stages["deps"].args("RUN")[1:]
    assert install.startswith(f"--mount=type=cache,target={PNPM_STORE} ")


def dockerignore_patterns(component: Path) -> list[str]:
    text = (component / ".dockerignore").read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip() and line[0] != "#"]


@pytest.mark.parametrize(
    ("component", "generated"),
    [
        (BACKEND, ("**/.venv", "**/__pycache__", "**/coverage", "**/node_modules", "**/.next")),
        (FRONTEND, ("**/node_modules", "**/.pnpm-store", "**/.next", "**/coverage")),
    ],
    ids=["backend", "frontend"],
)
def test_RNF_PLT_01_dockerignore_excludes_env_and_git(
    component: Path, generated: tuple[str, ...]
) -> None:
    patterns = dockerignore_patterns(component)
    assert "**/.env*" in patterns
    assert "**/.git" in patterns
    for expected in generated:
        assert expected in patterns, expected
    # No exception brings anything back, an .env.example included.
    assert [p for p in patterns if p.startswith("!")] == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "FROM a:1@sha256:x AS b\n# c\nRUN x \\\n  y\n",
            [("FROM", "a:1@sha256:x AS b"), ("RUN", "x y")],
        ),
        ("ENV A=1 \\\n    B=2\n", [("ENV", "A=1 B=2")]),
    ],
)
def test_AC_PLT_25_parser_joins_continuations(text: str, expected: list[tuple[str, str]]) -> None:
    assert instructions(text) == expected


def test_AC_PLT_25_parser_rejects_unnamed_stage() -> None:
    with pytest.raises(AssertionError, match="unnamed stage"):
        stages("FROM python:3.12\n")
