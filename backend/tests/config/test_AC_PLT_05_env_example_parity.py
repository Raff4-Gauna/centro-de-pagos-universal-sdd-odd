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
``frontend/src`` need the whole checkout: they skip inside the container and run on the host and CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import Field

from config.settings.env import PlatformEnv

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / "env.example"
SPIKES_ENV_EXAMPLE = REPO_ROOT / "spikes" / "env.example"
COMPOSE_FILE = REPO_ROOT / "infra" / "docker-compose.yml"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

# Interpolated by infra/docker-compose.yml for the db service only; no Hub setting reads them.
COMPOSE_ONLY_VARS = frozenset({"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"})
# Read by the BFF on the server only (Q-050: never a NEXT_PUBLIC_ variable).
FRONTEND_SERVER_VARS = frozenset({"BACKEND_INTERNAL_URL"})

PROVIDER_PATTERN = re.compile(r"^(MP|MERCADOPAGO|CLOVER|PAYWAY|DECIDIR|PRISMA)_", re.IGNORECASE)
_LINE = re.compile(r"(?P<name>[A-Z][A-Z0-9_]*)=(?P<value>.*)")
_PLACEHOLDER = re.compile(r"<ver \.env: (?P<name>[A-Z][A-Z0-9_]*)>")
# ${VAR...} interpolation; $${VAR} is an escaped literal for the container's shell.
_COMPOSE_VAR = re.compile(r"(?<!\$)\$\{([A-Z_][A-Z0-9_]*)")
_PROCESS_ENV = re.compile(
    r"process\.env(?:\.([A-Z_][A-Z0-9_]*)|\[\s*[\"']([A-Z_][A-Z0-9_]*)[\"']\s*\])"
)


def parse_env_example(text: str) -> dict[str, str]:
    """``NAME=value`` per line; blank lines and ``#`` comments are skipped. Anything else (an
    ``export``, a lower-case name, a missing ``=``) or a repeated name raises, naming the line."""
    variables: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _LINE.fullmatch(line)
        if match is None:
            raise ValueError(f"line {number}: not a NAME=value line")
        name = match.group("name")
        if name in variables:
            raise ValueError(f"line {number}: {name} is repeated")
        variables[name] = match.group("value")
    return variables


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


def root_vars() -> dict[str, str]:
    return parse_env_example(ENV_EXAMPLE.read_text(encoding="utf-8"))


def spike_vars() -> dict[str, str]:
    return parse_env_example(SPIKES_ENV_EXAMPLE.read_text(encoding="utf-8"))


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


@pytest.mark.skipif(not COMPOSE_FILE.exists(), reason="infra/ is not mounted in the container")
def test_AC_PLT_01_every_compose_variable_is_in_env_example() -> None:
    # A clean clone with env.example copied to .env satisfies every ${VAR:?...} of the dev stack.
    interpolated = set(_COMPOSE_VAR.findall(COMPOSE_FILE.read_text(encoding="utf-8")))
    assert interpolated, "no interpolation found in infra/docker-compose.yml"
    assert sorted(interpolated - set(root_vars())) == []
    assert interpolated - set(PlatformEnv.model_fields) == COMPOSE_ONLY_VARS


@pytest.mark.skipif(not FRONTEND_SRC.exists(), reason="frontend/ is not mounted in the container")
def test_AC_PLT_05_frontend_server_vars_match_what_the_bff_reads() -> None:
    read: set[str] = set()
    for path in sorted(FRONTEND_SRC.rglob("*.ts*")):
        if ".test." in path.name:
            continue
        for dotted, indexed in _PROCESS_ENV.findall(path.read_text(encoding="utf-8")):
            read.add(dotted or indexed)
    # NODE_ENV is set by Next itself, never by env.example.
    assert read - {"NODE_ENV"} == FRONTEND_SERVER_VARS
