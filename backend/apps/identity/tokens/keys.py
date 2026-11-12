"""The keys of the Hub's access JWT (ADR-0004 sec. 5, RN-IDA-16, RNF-IDA-01).

Each PEM is parsed once and kept in memory, so verifying needs neither a parse nor the network. The
loaders are also what ``config.settings.env`` validates a key with at start; a failed load says
nothing about the input (C-06). Which key is active is read from the settings on every call, so
a rotation is only a deploy (design.md sec. 10). Unset keys fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import (
    SECP256R1,
    EllipticCurvePrivateKey,
    EllipticCurvePublicKey,
)
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True, slots=True)
class SigningKey:
    kid: str
    key: EllipticCurvePrivateKey = field(repr=False)


@lru_cache(maxsize=8)
def load_private_key(pem: str) -> EllipticCurvePrivateKey:
    """The P-256 private key in ``pem``; ``ValueError`` for anything else (ES256 means P-256)."""
    try:
        key = serialization.load_pem_private_key(pem.encode(), password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm):
        key = None
    if not isinstance(key, EllipticCurvePrivateKey) or not isinstance(key.curve, SECP256R1):
        raise ValueError("not a P-256 private key")
    return key


@lru_cache(maxsize=16)
def load_public_key(pem: str) -> EllipticCurvePublicKey:
    """The P-256 public key in ``pem``; ``ValueError`` for anything else."""
    try:
        key = serialization.load_pem_public_key(pem.encode())
    except (ValueError, UnsupportedAlgorithm):
        key = None
    if not isinstance(key, EllipticCurvePublicKey) or not isinstance(key.curve, SECP256R1):
        raise ValueError("not a P-256 public key")
    return key


def is_public_key_of(public_pem: str, private_pem: str) -> bool:
    return load_public_key(public_pem) == load_private_key(private_pem).public_key()


def active_signing_key() -> SigningKey:
    kid, pem = settings.IDENTITY_JWT_SIGNING_KID, settings.IDENTITY_JWT_SIGNING_KEY
    if not kid or not pem:
        raise ImproperlyConfigured("IDENTITY_JWT_SIGNING_KID and _KEY are not set")
    return SigningKey(kid=kid, key=load_private_key(pem))


def verification_key(kid: str) -> EllipticCurvePublicKey | None:
    """The public key of ``kid``, or ``None`` if it is not one of the Hub's."""
    keys = settings.IDENTITY_JWT_VERIFICATION_KEYS
    if not keys:
        raise ImproperlyConfigured("IDENTITY_JWT_VERIFICATION_KEYS is not set")
    pem = keys.get(kid)
    return None if pem is None else load_public_key(pem)
