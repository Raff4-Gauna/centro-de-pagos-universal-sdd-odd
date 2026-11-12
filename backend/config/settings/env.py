"""The only module that reads the process environment (design.md §3.2.2, RN-PLT-02, Q-040).

``PlatformEnv`` declares every variable the settings use, with its validation. Nothing is read from
``.env`` files (``env_file=None``, dotenv and secrets-dir sources dropped): Compose or the hosting
inject the environment. ``load_env()`` turns a validation failure into ``ImproperlyConfigured``
whose message holds only variable names and error types, never a value, and raises it outside the
``except`` block so the pydantic error (which renders the inputs) is neither ``__context__`` nor
``__cause__``: no value reaches stderr or a log (AC-PLT-03, C-06). The variables that carry
credentials are ``SecretStr``/``Secret[...]``, masked in ``repr``, ``str`` and ``model_dump``.
``load_feature_flags()`` reads the ``FEATURE_*`` variables the same way (RF-PLT-19, §3.2.8), and
``load_bff_credentials()`` the one value every settings module takes alike, for ``base.py``.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Collection
from typing import Annotated, Any, Literal, Self
from urllib.parse import unquote

from django.core.exceptions import ImproperlyConfigured
from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    PostgresDsn,
    RedisDsn,
    Secret,
    SecretStr,
    ValidationError,
    model_validator,
)
from pydantic_core import PydanticCustomError
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from apps.identity.tokens.keys import is_public_key_of, load_private_key, load_public_key

# Custom error messages are never shown (only the type is), but they carry no value either.

FEATURE_PREFIX = "FEATURE_"
_BOOL_TEXTS = {"true", "false"}
MAX_BFF_CREDENTIALS = 2


def _strict_bool(value: object) -> object:
    """Only ``true``/``false`` (any case): a typo such as ``ture`` or ``1`` must not start."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in _BOOL_TEXTS:
        return value.lower() == "true"
    raise PydanticCustomError("bool_format", "expected true or false")


def _csv(value: object) -> object:
    """Comma-separated list without empty items (``a,,b`` or an empty string do not start)."""
    if not isinstance(value, str):
        return value
    items = [item.strip() for item in value.split(",")]
    if any(not item for item in items):
        raise PydanticCustomError("csv_empty_item", "empty item in a comma-separated list")
    return items


def _django_postgres_dsn(value: PostgresDsn) -> PostgresDsn:
    """Fail closed on anything ``databases()`` would drop or misread: driver suffixes in the scheme
    (``postgresql+asyncpg``), several hosts, a query string or fragment (``?sslmode=``), and a
    missing database name or one with ``/``."""
    if value.scheme not in {"postgres", "postgresql"}:
        raise PydanticCustomError("dsn_scheme", "only postgres:// or postgresql://")
    if len(value.hosts()) != 1:
        raise PydanticCustomError("dsn_multiple_hosts", "exactly one host is supported")
    if value.query or value.fragment:
        raise PydanticCustomError("dsn_options", "no query string nor fragment")
    name = unquote((value.path or "").removeprefix("/"))
    if not name:
        raise PydanticCustomError("dsn_database_missing", "the database name is missing")
    if "/" in name:
        raise PydanticCustomError("dsn_database_name", "the database name has a slash")
    return value


# DRF's "<requests>/<period>" (design.md §3.2.4); DRF only reads the period's first letter.
_THROTTLE_RATE = re.compile(r"[1-9][0-9]*/(s|sec|m|min|h|hour|d|day)")


def _throttle_rate(value: str) -> str:
    """``300/min``-like: a typo such as ``300/mni`` or ``0/min`` must not start."""
    if not _THROTTLE_RATE.fullmatch(value):
        raise PydanticCustomError("throttle_rate_format", "expected <requests>/<s|min|h|day>")
    return value


def _json_object(value: object) -> object:
    """A JSON object. Decoded here because pydantic-settings' own failure is no ValidationError:
    ``load_env`` would not catch it."""
    if not isinstance(value, str):
        return value
    try:
        decoded = json.loads(value)
    except ValueError:
        decoded = None
    if not isinstance(decoded, dict):
        raise PydanticCustomError("json_object", "expected a JSON object")
    return decoded


def _jwt_signing_key(value: SecretStr) -> SecretStr:
    """Empty is the default, which pydantic-settings validates too: no signer in this process."""
    try:
        if pem := value.get_secret_value():
            load_private_key(pem)
    except ValueError:
        raise PydanticCustomError("jwt_signing_key_format", "expected a P-256 PEM") from None
    return value


def _jwt_verification_keys(value: dict[str, str]) -> dict[str, str]:
    try:
        for pem in value.values():
            load_public_key(pem)
    except ValueError:
        raise PydanticCustomError("jwt_verification_key_format", "expected P-256 PEMs") from None
    return value


EnvBool = Annotated[bool, BeforeValidator(_strict_bool)]
# NoDecode: pydantic-settings would otherwise parse a list variable as JSON.
CsvList = Annotated[list[str], NoDecode, BeforeValidator(_csv)]
NonEmptyStr = Annotated[str, Field(min_length=1)]
DjangoPostgresDsn = Annotated[PostgresDsn, AfterValidator(_django_postgres_dsn)]
ThrottleRate = Annotated[str, AfterValidator(_throttle_rate)]
JwtSigningKey = Annotated[SecretStr, AfterValidator(_jwt_signing_key)]
JwtVerificationKeys = Annotated[
    dict[str, str],
    NoDecode,
    BeforeValidator(_json_object),
    AfterValidator(_jwt_verification_keys),
]


# Current and, during a rotation, previous (design.md §8.3).
BffCredentials = Annotated[
    list[SecretStr], NoDecode, BeforeValidator(_csv), Field(max_length=MAX_BFF_CREDENTIALS)
]


class HubEnv(BaseSettings):
    """Where the variables come from. Field names are the names (``case_sensitive=True``)."""

    model_config = SettingsConfigDict(
        env_file=None,
        # An empty variable counts as unset: optional ones fall back to their default and
        # required ones fail as missing.
        env_ignore_empty=True,
        case_sensitive=True,
        extra="ignore",
        frozen=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Process environment only: no .env file, no secrets directory.
        return (init_settings, env_settings)


class BffCredentialEnv(HubEnv):
    """Apart from ``PlatformEnv``: ``base.py`` loads it, and runs under every env class."""

    # Accepted in X-Hub-Bff-Credential (ADR-0004 §9). Empty: nobody is accepted, auth/bff/* is 404.
    IDENTITY_BFF_CREDENTIALS: BffCredentials = Field(default_factory=list)


class PlatformEnv(BffCredentialEnv):
    """Platform variables, the ones ``env.example`` lists (AC-PLT-05)."""

    DJANGO_SECRET_KEY: Annotated[SecretStr, Field(min_length=1)]
    DJANGO_DEBUG: EnvBool = False
    # Defaults for dev/test only; prod.py (ProdEnv) makes it required.
    DJANGO_ALLOWED_HOSTS: CsvList = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    # Both URLs may embed a password: masked like the secret key.
    DATABASE_URL: Secret[DjangoPostgresDsn]
    REDIS_URL: Secret[RedisDsn]
    APP_VERSION: NonEmptyStr = "unknown"
    # Root level of the JSON logs (design.md §3.2.3); exactly one of these, upper case.
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Global throttle for anonymous clients (RN-PLT-19, Q-038): generous on purpose.
    API_THROTTLE_ANON_RATE: ThrottleRate = "300/min"
    # Proxies in front of the backend that append to X-Forwarded-For (DRF's NUM_PROXIES). 0: the
    # throttle keys on REMOTE_ADDR and ignores the header, which any client can forge. Set with the
    # hosting (Q-020).
    TRUSTED_PROXY_COUNT: Annotated[int, Field(ge=0)] = 0
    # The Hub's access JWT (ADR-0004 sec. 5). Without keys the process starts and issuing or
    # verifying fails closed (apps.identity.tokens.keys).
    IDENTITY_JWT_ISSUER: NonEmptyStr = "centro-de-pagos"
    IDENTITY_JWT_AUDIENCE: NonEmptyStr = "centro-de-pagos-api"
    IDENTITY_JWT_SIGNING_KID: str = ""
    IDENTITY_JWT_SIGNING_KEY: JwtSigningKey = SecretStr("")
    # {kid: public PEM}: the active key and, during a rotation, the previous one.
    IDENTITY_JWT_VERIFICATION_KEYS: JwtVerificationKeys = Field(default_factory=dict)

    @model_validator(mode="after")
    def _jwt_signer_verifies_its_own_tokens(self) -> Self:
        """A signer without its ``kid``, or whose public key is not listed, would issue tokens the
        Hub itself rejects: it does not start. A process that only verifies has no signer."""
        kid = self.IDENTITY_JWT_SIGNING_KID
        key = self.IDENTITY_JWT_SIGNING_KEY.get_secret_value()
        if bool(kid) != bool(key):
            raise PydanticCustomError("jwt_signing_pair", "set both the kid and the key, or none")
        public_pem = self.IDENTITY_JWT_VERIFICATION_KEYS.get(kid)
        if key and (public_pem is None or not is_public_key_of(public_pem, key)):
            raise PydanticCustomError("jwt_signing_key_not_verifiable", "public key not listed")
        return self

    def databases(self) -> dict[str, dict[str, Any]]:
        """``DATABASES`` from ``DATABASE_URL``; ``connect_timeout=2`` so /readyz answers fast."""
        url = self.DATABASE_URL.get_secret_value()
        host = url.hosts()[0]
        return {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": unquote((url.path or "").removeprefix("/")),
                "USER": unquote(host["username"] or ""),
                "PASSWORD": unquote(host["password"] or ""),
                "HOST": host["host"] or "",
                "PORT": str(host["port"] or ""),
                "OPTIONS": {"connect_timeout": 2},
            }
        }


def describe_errors(env_class: type[HubEnv], error: ValidationError) -> str:
    """One line per invalid variable: ``- NAME: error_type``. Never the input nor the URL."""
    lines = []
    for item in error.errors(include_input=False, include_url=False, include_context=False):
        name = str(item["loc"][0]) if item["loc"] else "<environment>"
        lines.append(f"  - {name}: {item['type']}")
    header = f"Invalid environment for {env_class.__name__} (values are never shown):"
    return "\n".join([header, *sorted(set(lines))])


def load_env[EnvT: HubEnv](env_class: type[EnvT]) -> EnvT:
    """Validate the environment with ``env_class``; on failure, raise without any value."""
    try:
        return env_class()
    except ValidationError as error:
        message = describe_errors(env_class, error)
    # Raised outside the except block: the ValidationError is not even kept as __context__.
    raise ImproperlyConfigured(message)


def load_bff_credentials() -> tuple[SecretStr, ...]:
    """``IDENTITY_BFF_CREDENTIALS``, still masked: a setting is rendered by error reports."""
    return tuple(load_env(BffCredentialEnv).IDENTITY_BFF_CREDENTIALS)


def load_feature_flags(registry: Collection[str]) -> dict[str, bool]:
    """``FEATURE_<NAME>`` of every registered ``NAME`` (``apps.common.feature_flags.REGISTRY``).

    Off when unset or empty (empty counts as unset, as for ``PlatformEnv``). A ``FEATURE_*``
    variable whose name is not registered, or a value other than ``true``/``false`` (any case),
    raises ``ImproperlyConfigured`` naming the variables, never their values.
    """
    flags = dict.fromkeys(registry, False)
    lines = []
    for variable, raw in os.environ.items():
        if not variable.startswith(FEATURE_PREFIX) or not raw:
            continue
        name = variable.removeprefix(FEATURE_PREFIX)
        if name not in flags:
            lines.append(f"  - {variable}: feature_unregistered")
        elif raw.lower() not in _BOOL_TEXTS:
            lines.append(f"  - {variable}: bool_format")
        else:
            flags[name] = raw.lower() == "true"
    if lines:
        header = "Invalid environment for feature flags (values are never shown):"
        raise ImproperlyConfigured("\n".join([header, *sorted(lines)]))
    return flags
