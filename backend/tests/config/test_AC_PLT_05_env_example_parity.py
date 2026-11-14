"""AC-PLT-05 (RN-PLT-03, RF-PLT-04): ``env.example`` lists exactly the platform variables.

Parity in both directions (design.md §3.2.2) between what the platform reads and the keys of the
root ``env.example`` (renamed from ``.env.example`` by the owner, Q-048):

* ``PlatformEnv.model_fields``: every variable the Django settings read (``env.py`` is the only
  reader, AC-PLT-06);
* ``COMPOSE_ONLY_VARS``: what only Compose interpolates (the ``db`` service credentials);
* ``FRONTEND_SERVER_VARS``: what the BFF reads on the server (``frontend/src/lib/server/env.ts``).

A variable read but not listed fails naming it, and so does a listed variable nobody reads. The
spike keys live apart in ``spikes/env.example`` and never in the root file (RN-PLT-04).

Both files are bind-mounted ``:ro`` into the dev ``backend`` container (``/repo/env.example``), so
these tests also run there. The two cross-checks against ``infra/docker-compose.yml`` and
``frontend/src`` need the whole checkout: they skip inside the container only, and fail in CI or in
a checkout where those files are missing (``_env_example.checkout_path``).
"""

from __future__ import annotations

import re

import pytest
from pydantic import Field

from config.settings.env import PlatformEnv
from tests.config import _env_example
from tests.config._env_example import (
    ENV_EXAMPLE,
    REPO_ROOT,
    checkout_path,
    parse_env_example,
    root_vars,
    spike_vars,
)

COMPOSE_FILE = REPO_ROOT / "infra" / "docker-compose.yml"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

# Interpolated by infra/docker-compose.yml for the db service only; no Hub setting reads them.
COMPOSE_ONLY_VARS = frozenset({"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"})
# Read by the BFF on the server only (Q-050: never a NEXT_PUBLIC_ variable).
FRONTEND_SERVER_VARS = frozenset(
    {"BACKEND_INTERNAL_URL", "HUB_BFF_CREDENTIAL", "HUB_APP_ORIGIN", "HUB_TRUSTED_PROXY_HOPS"}
)

PROVIDER_PATTERN = re.compile(r"^(MP|MERCADOPAGO|CLOVER|PAYWAY|DECIDIR|PRISMA)_", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"<ver \.env: (?P<name>[A-Z][A-Z0-9_]*)>")
# ${VAR...} interpolation; $${VAR} is an escaped literal for the container's shell.
_COMPOSE_VAR = re.compile(r"(?<!\$)\$\{([A-Z_][A-Z0-9_]*)")
_PROCESS_ENV = re.compile(
    r"process\.env(?:\.([A-Z_][A-Z0-9_]*)|\[\s*[\"']([A-Z_][A-Z0-9_]*)[\"']\s*\])"
)
# const { A, B: b, C = "x", ...rest } = process.env
_PROCESS_ENV_DESTRUCTURING = re.compile(r"\{([^{}]*)\}\s*=\s*process\.env\b")
_DESTRUCTURED_NAME = re.compile(r"\s*([A-Za-z_$][A-Za-z0-9_$]*)")


def platform_vars(env_class: type[PlatformEnv] = PlatformEnv) -> frozenset[str]:
    """Every variable the platform reads: settings fields, Compose-only and BFF server ones."""
    return frozenset(env_class.model_fields) | COMPOSE_ONLY_VARS | FRONTEND_SERVER_VARS


def parity_errors(expected: frozenset[str], listed: set[str]) -> list[str]:
    """One line per variable out of parity, in both directions, each naming the variable."""
    missing = [
        f"{name}: read by the platform but missing from env.example" for name in expected - listed
    ]
    unread = [f"{name}: in env.example but nothing reads it" for name in listed - expected]
    return sorted(missing + unread)


def bff_env_reads(source: str) -> set[str]:
    """Every ``process.env`` variable of a frontend source: ``.X``, ``["X"]`` and destructuring."""
    read = {dotted or indexed for dotted, indexed in _PROCESS_ENV.findall(source)}
    for group in _PROCESS_ENV_DESTRUCTURING.findall(source):
        for item in group.split(","):
            match = _DESTRUCTURED_NAME.match(item)
            if match and not item.strip().startswith("..."):
                read.add(match.group(1))
    return read


class _EnvWithNewSetting(PlatformEnv):
    """A settings change that adds a variable without editing env.example."""

    HUB_NEW_SETTING: str = Field(default="x")


def test_AC_PLT_05_setting_missing_from_env_example_fails_naming_it() -> None:
    errors = parity_errors(platform_vars(_EnvWithNewSetting), set(root_vars()))
    assert errors == ["HUB_NEW_SETTING: read by the platform but missing from env.example"]


def test_AC_PLT_05_env_example_var_not_read_fails_naming_it() -> None:
    listed = set(root_vars()) | {"HUB_LEFTOVER_VAR"}
    errors = parity_errors(platform_vars(), listed)
    assert errors == ["HUB_LEFTOVER_VAR: in env.example but nothing reads it"]


def test_AC_PLT_05_removed_setting_still_listed_fails_naming_it() -> None:
    expected = platform_vars() - {"LOG_LEVEL"}
    assert parity_errors(expected, set(root_vars())) == [
        "LOG_LEVEL: in env.example but nothing reads it"
    ]


def test_AC_PLT_05_real_env_example_in_parity() -> None:
    assert parity_errors(platform_vars(), set(root_vars())) == []


def test_AC_PLT_05_cross_check_source_missing_in_ci_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    with pytest.raises(pytest.fail.Exception, match=r"infra/missing.yml is missing"):
        checkout_path(REPO_ROOT / "infra" / "missing.yml")


def test_AC_PLT_05_cross_check_source_missing_in_a_checkout_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(_env_example, "CHECKOUT_MARKER", ENV_EXAMPLE)  # exists everywhere
    with pytest.raises(pytest.fail.Exception, match=r"infra/missing.yml is missing"):
        checkout_path(REPO_ROOT / "infra" / "missing.yml")


def test_AC_PLT_05_cross_check_skips_only_inside_the_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(_env_example, "CHECKOUT_MARKER", REPO_ROOT / "no-such-marker")
    with pytest.raises(pytest.skip.Exception):
        checkout_path(REPO_ROOT / "infra" / "missing.yml")


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("export DJANGO_DEBUG=false\n", "line 1: not a NAME=value line"),
        ("# ok\nlog_level=INFO\n", "line 2: not a NAME=value line"),
        ("LOG_LEVEL\n", "line 1: not a NAME=value line"),
        ("LOG_LEVEL=INFO\n\nLOG_LEVEL=DEBUG\n", "line 3: LOG_LEVEL is repeated"),
    ],
)
def test_AC_PLT_05_malformed_env_example_fails_naming_the_line(text: str, error: str) -> None:
    with pytest.raises(ValueError, match=f"^{error}$"):
        parse_env_example(text)


def test_AC_PLT_05_parser_reads_names_values_and_skips_comments() -> None:
    text = "# group\n\nA_VAR=\nB_VAR=x=y\n  # FEATURE_X=true\n"
    assert parse_env_example(text) == {"A_VAR": "", "B_VAR": "x=y"}


def test_RN_PLT_04_spike_keys_absent_from_root_env_example() -> None:
    spikes = set(spike_vars())
    assert spikes, "spikes/env.example lists no key"
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    # Not even in a comment: the root file is platform only.
    assert sorted(name for name in spikes if re.search(rf"\b{name}\b", text)) == []
    assert sorted(name for name in root_vars() if PROVIDER_PATTERN.match(name)) == []


def test_RN_PLT_04_spike_values_are_placeholders_only() -> None:
    # Never a value, real or fake: only <ver .env: SAME_NAME>, which gitleaks allows (RN-PLT-13).
    bad = []
    for name, value in spike_vars().items():
        match = _PLACEHOLDER.fullmatch(value)
        if match is None or match.group("name") != name:
            bad.append(name)
    assert bad == []


def test_RN_IDA_12_dev_bff_credential_is_one_django_accepts() -> None:
    # Copied to .env as is, the BFF's credential must open /api/auth/bff/* in dev.
    accepted = {value.strip() for value in root_vars()["IDENTITY_BFF_CREDENTIALS"].split(",")}
    assert root_vars()["HUB_BFF_CREDENTIAL"] in accepted


def test_AC_PLT_01_allowed_hosts_keep_localhost_and_backend() -> None:
    # localhost: the backend healthcheck; backend: the frontend BFF calls http://backend:8000 and,
    # without it, Django answers 400 DisallowedHost.
    hosts = {host.strip() for host in root_vars()["DJANGO_ALLOWED_HOSTS"].split(",")}
    assert sorted({"localhost", "backend"} - hosts) == []


def test_AC_PLT_01_every_compose_variable_is_in_env_example() -> None:
    # A clean clone with env.example copied to .env satisfies every ${VAR:?...} of the dev stack.
    compose = checkout_path(COMPOSE_FILE)
    interpolated = set(_COMPOSE_VAR.findall(compose.read_text(encoding="utf-8")))
    assert interpolated, "no interpolation found in infra/docker-compose.yml"
    assert sorted(interpolated - set(root_vars())) == []
    assert interpolated - set(PlatformEnv.model_fields) == COMPOSE_ONLY_VARS


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("process.env.BACKEND_INTERNAL_URL", {"BACKEND_INTERNAL_URL"}),
        ("process.env['A_VAR'] ?? process.env[\"B_VAR\"]", {"A_VAR", "B_VAR"}),
        (
            "const { A_VAR, B_VAR: b, C_VAR = 'x', ...rest } = process.env;",
            {"A_VAR", "B_VAR", "C_VAR"},
        ),
        ("const {\n  A_VAR,\n} = process.env", {"A_VAR"}),
        ("const { a } = other; const env = processEnv", set()),
    ],
)
def test_AC_PLT_05_bff_env_scanner_finds_every_form(source: str, expected: set[str]) -> None:
    assert bff_env_reads(source) == expected


def test_AC_PLT_05_frontend_server_vars_match_what_the_bff_reads() -> None:
    read: set[str] = set()
    for path in sorted(checkout_path(FRONTEND_SRC).rglob("*.ts*")):
        if ".test." in path.name:
            continue
        read |= bff_env_reads(path.read_text(encoding="utf-8"))
    # NODE_ENV is set by Next itself, never by env.example.
    assert read - {"NODE_ENV"} == FRONTEND_SERVER_VARS
