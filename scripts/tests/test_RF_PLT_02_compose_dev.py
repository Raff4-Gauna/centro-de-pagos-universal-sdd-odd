"""RF-PLT-02, RN-PLT-01, RN-PLT-04 (T-PLT-26, design.md §3.4.1, D-04): the dev Compose, statically.

``infra/docker-compose.yml`` has the five backend-side services (``frontend`` arrives with
T-PLT-36), each with a healthcheck; every ``depends_on`` waits for ``service_healthy``; ``migrate``
runs only in ``backend``; ``beat`` is a single replica whose schedule lives in the container's own
filesystem (not a ``tmpfs``: ``dbm.gnu`` writes through mmap and on a tmpfs its writes never update
the mtime the healthcheck reads) and whose healthcheck reads that same file; published ports
listen on ``127.0.0.1`` only. The environment is explicit per service (no ``env_file:``), so a
variable in ``.env`` reaches a container only if it is listed; required ones fail fast
(``${VAR:?…}``). ``db``/``redis`` use the same ``tag@sha256`` as the services of the CI ``tests``
job. Running it (``up --wait``, Redis stopped) is the manual verification of the task and, later,
``smoke_stack.py`` (T-PLT-38).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "infra" / "docker-compose.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

SERVICES = {"db", "redis", "backend", "worker", "beat"}
BACKEND_IMAGE_USERS = {"backend", "worker", "beat"}
# design.md §3.4.1: (interval, timeout, retries, start_period) and the healthy dependencies.
HEALTH_TIMINGS = {
    "db": ("5s", "3s", 10, "10s"),
    "redis": ("5s", "3s", 10, "5s"),
    "backend": ("10s", "3s", 5, "30s"),
    "worker": ("30s", "10s", 3, "30s"),
    "beat": ("60s", "5s", 3, "90s"),
}
DEPENDS_ON = {
    "db": set(),
    "redis": set(),
    "backend": {"db", "redis"},
    "worker": {"db", "redis", "backend"},
    "beat": {"redis", "backend"},
}
PUBLISHED_PORTS = {"db": "127.0.0.1:5432:5432", "backend": "127.0.0.1:8000:8000"}
REQUIRED_VARIABLES = {
    "db": {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"},
    "backend": {"DJANGO_SECRET_KEY", "DATABASE_URL", "REDIS_URL"},
    "worker": {"DJANGO_SECRET_KEY", "DATABASE_URL", "REDIS_URL"},
    "beat": {"DJANGO_SECRET_KEY", "DATABASE_URL", "REDIS_URL"},
}
BEAT_DIR = "/tmp/beat"  # noqa: S108 - container-private, outside the bind-mounted code
BEAT_SCHEDULE = f"{BEAT_DIR}/schedule"
# Only ${NAME:?message} (required, fail fast) or ${NAME:-default} (optional); a bare $NAME or
# ${NAME} silently becomes empty. `$$` is Compose's escape for a literal `$` (shell in container).
INTERPOLATION = re.compile(r"\$(?:\{(?P<braced>[^}]*)\}|(?P<bare>[A-Za-z_]\w*))")
ALLOWED_INTERPOLATION = re.compile(r"(?P<name>[A-Z][A-Z0-9_]*):(?:\?[^}]+|-[^}]*)")
# RN-PLT-04 / AC-PLT-06: provider credentials are never platform configuration.
PROVIDER_PREFIX = re.compile(r"^(MP|MERCADOPAGO|CLOVER|PAYWAY|DECIDIR|PRISMA)_")


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    loaded = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture(scope="module")
def services(compose: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = compose["services"]
    assert isinstance(result, dict)
    return result


def words(value: str | list[str]) -> str:
    """A command or healthcheck as one string (list form joined), for substring checks."""
    return " ".join(value) if isinstance(value, list) else value


def healthcheck_command(service: dict[str, Any]) -> str:
    test = service["healthcheck"]["test"]
    assert isinstance(test, list), "healthcheck.test in exec form (CMD or CMD-SHELL)"
    assert test[0] in {"CMD", "CMD-SHELL"}
    return words(test[1:])


def strip_escapes(text: str) -> str:
    return text.replace("$$", "")


def test_RF_PLT_02_compose_project_and_services(compose: dict[str, Any]) -> None:
    assert compose["name"] == "centro-pagos"
    assert set(compose["services"]) == SERVICES


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_RF_PLT_02_every_service_has_healthcheck(
    services: dict[str, dict[str, Any]], name: str
) -> None:
    check = services[name]["healthcheck"]
    assert healthcheck_command(services[name]).strip()
    timings = (check["interval"], check["timeout"], check["retries"], check["start_period"])
    assert timings == HEALTH_TIMINGS[name]
    assert not check.get("disable", False)


def test_RF_PLT_02_healthchecks_probe_the_real_thing(services: dict[str, dict[str, Any]]) -> None:
    # TCP (-h): during initdb the entrypoint's temporary server listens on the socket only.
    db = healthcheck_command(services["db"])
    assert "pg_isready -h 127.0.0.1 -U $$POSTGRES_USER -d $$POSTGRES_DB" in db
    assert "redis-cli ping | grep -q PONG" in healthcheck_command(services["redis"])
    backend = healthcheck_command(services["backend"])
    assert "urllib.request" in backend
    assert "http://localhost:8000/readyz" in backend
    assert "celery -A config inspect ping -d celery@$$HOSTNAME" in healthcheck_command(
        services["worker"]
    )


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_RF_PLT_02_depends_on_service_healthy(
    services: dict[str, dict[str, Any]], name: str
) -> None:
    depends_on = services[name].get("depends_on", {})
    assert isinstance(depends_on, dict), "long form: a list cannot carry a condition"
    assert set(depends_on) == DEPENDS_ON[name]
    for dependency, spec in depends_on.items():
        assert spec["condition"] == "service_healthy", f"{name} -> {dependency}"


def test_RF_PLT_02_no_migrate_in_worker_or_beat(services: dict[str, dict[str, Any]]) -> None:
    backend = words(services["backend"]["command"])
    assert "python manage.py migrate --noinput && exec gunicorn" in backend
    assert "-c config/gunicorn.conf.py" in backend
    for name in sorted(SERVICES - {"backend"}):
        command = words(services[name].get("command", ""))
        assert "migrate" not in command, name
        assert "migrate" not in services[name].get("entrypoint", ""), name


def test_RF_PLT_02_backend_hot_reload_by_polling(services: dict[str, dict[str, Any]]) -> None:
    # Bind mounts from Windows deliver no inotify events: gunicorn polls (infra/README.md).
    assert "--reload --reload-engine poll" in words(services["backend"]["command"])
    assert "../backend:/repo/backend" in services["backend"]["volumes"]


def test_RF_PLT_02_worker_and_beat_reuse_the_backend_image(
    services: dict[str, dict[str, Any]],
) -> None:
    backend = services["backend"]
    assert backend["build"] == {"context": "../backend", "target": "dev"}
    for name in sorted(BACKEND_IMAGE_USERS - {"backend"}):
        assert services[name]["image"] == backend["image"], name
        assert "build" not in services[name], name
        assert "../backend:/repo/backend" in services[name]["volumes"], name


def test_RF_PLT_02_single_beat_replica(services: dict[str, dict[str, Any]]) -> None:
    beat = services["beat"]
    assert beat["deploy"]["replicas"] == 1
    assert "scale" not in beat
    # No tmpfs (see the module docstring): the schedule goes in the writable layer, recreated
    # with the container, never in the bind-mounted tree.
    assert "tmpfs" not in beat
    assert not any(BEAT_DIR in str(volume) for volume in beat["volumes"])
    command = words(beat["command"])
    assert command.startswith(f"sh -c mkdir -p {BEAT_DIR} && exec celery -A config -q beat")
    assert f"--schedule {BEAT_SCHEDULE}" in command
    assert "--max-interval 60" in command
    check = healthcheck_command(beat)
    assert "python -m apps.common.health.beat_alive" in check
    assert f"--schedule {BEAT_SCHEDULE}" in check


def test_RF_PLT_02_worker_command(services: dict[str, dict[str, Any]]) -> None:
    command = words(services["worker"]["command"])
    assert "celery -A config -q worker -l INFO --concurrency 2" in command


def test_RF_PLT_02_redis_without_persistence(services: dict[str, dict[str, Any]]) -> None:
    assert words(services["redis"]["command"]) == 'redis-server --save "" --appendonly no'
    assert "volumes" not in services["redis"]


def test_RF_PLT_02_pgdata_volume(compose: dict[str, Any]) -> None:
    assert set(compose["volumes"]) == {"pgdata"}
    assert "pgdata:/var/lib/postgresql/data" in compose["services"]["db"]["volumes"]


def test_RN_PLT_04_compose_uses_explicit_environment_without_env_file(
    compose: dict[str, Any], services: dict[str, dict[str, Any]]
) -> None:
    assert "env_file" not in compose
    for name, service in services.items():
        assert "env_file" not in service, name
        environment = service.get("environment", {})
        assert isinstance(environment, dict), f"{name}: environment as a mapping"
        for variable in environment:
            assert not PROVIDER_PREFIX.match(variable), f"{name}: {variable}"
    for name, required in REQUIRED_VARIABLES.items():
        environment = services[name]["environment"]
        for variable in sorted(required):
            assert re.fullmatch(rf"\$\{{{variable}:\?[^}}]+\}}", str(environment[variable])), (
                f"{name}: {variable} must be ${{{variable}:?…}}"
            )


def test_RN_PLT_04_every_interpolation_is_required_or_defaulted() -> None:
    text = strip_escapes(COMPOSE_FILE.read_text(encoding="utf-8"))
    found = list(INTERPOLATION.finditer(text))
    assert found
    for match in found:
        assert match["bare"] is None, f"bare ${match['bare']}"
        assert ALLOWED_INTERPOLATION.fullmatch(match["braced"]), match.group(0)


def test_RN_PLT_04_environment_values_come_from_their_own_variable(
    services: dict[str, dict[str, Any]],
) -> None:
    """``DATABASE_URL: ${DATABASE_URL:?…}``, never another variable's value (no cross-wiring)."""
    for name, service in services.items():
        for variable, value in service.get("environment", {}).items():
            names = {m["name"] for m in ALLOWED_INTERPOLATION.finditer(str(value))}
            assert names <= {variable}, f"{name}: {variable}"


def test_RF_PLT_02_ports_bound_to_localhost(services: dict[str, dict[str, Any]]) -> None:
    published = {name: service["ports"] for name, service in services.items() if "ports" in service}
    assert published == {name: [port] for name, port in PUBLISHED_PORTS.items()}
    for name, service in services.items():
        for port in service.get("ports", []):
            assert isinstance(port, str), f"{name}: short syntax, host IP first"
            assert port.startswith("127.0.0.1:"), f"{name}: {port}"
        assert service.get("network_mode") != "host", name


def test_RF_PLT_02_db_and_redis_images_match_ci_services(
    services: dict[str, dict[str, Any]],
) -> None:
    ci_services = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["tests"][
        "services"
    ]
    digest = re.compile(r"^[^@\s]+:[^@\s:/]+@sha256:[0-9a-f]{64}$")
    for compose_name, ci_name in (("db", "postgres"), ("redis", "redis")):
        image = services[compose_name]["image"]
        assert digest.match(image), f"{compose_name}: tag@sha256 of the multi-arch index"
        assert image == ci_services[ci_name]["image"], compose_name
