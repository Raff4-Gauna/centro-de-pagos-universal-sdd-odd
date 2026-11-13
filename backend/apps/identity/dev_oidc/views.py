"""The fake OIDC provider of dev and test (Q-122, RN-IDA-01, ADR-0004 §14, design.md §3.1).

Logging in without Google, where nobody can reach it: the same code flow ``GoogleGateway`` and
``IdTokenVerifier`` speak to Google (PKCE S256, ``client_secret_post``, RS256 ID token with
``nonce``), on ``/dev-oidc/*``. It authenticates nobody: whoever fills the form *is* that email.
That is why it answers only with ``IDENTITY_OIDC_PROVIDER=fake`` where the settings allow it, the
URLs are mounted only by ``config.urls_dev``, and a prod process with it does not start.

* ``GET /dev-oidc/authorize``: without ``email``, a form; with it, back to the registered
  ``redirect_uri`` with ``code`` and ``state``; with ``cancel``, ``error=access_denied`` like
  Google. Another client or ``redirect_uri`` is a plain ``400``, never a redirect.
* ``POST /dev-oidc/token``: the code is signed (``django.core.signing``) and carries the claims,
  the ``nonce`` and the PKCE challenge; it lives 10 minutes and is single use (cache).
* ``GET /dev-oidc/jwks``: the public half of the signing key.

The ``sub`` is derived from the normalized email, so the same person is the same user again. The
RSA key lives in the cache (Redis in dev), shared by every worker of the process group; it is a
development key, generated on first use, never in the repo.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, Final
from urllib.parse import urlencode

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
    JsonResponse,
)
from django.utils.crypto import constant_time_compare
from django.utils.html import format_html, format_html_join
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from jwt.algorithms import RSAAlgorithm

from apps.identity.domain.emails import normalize_email
from apps.identity.domain.secrets_format import code_challenge_s256, hash_secret
from apps.identity.oidc.provider import fake_issuer, fake_oidc_active

CODE_SALT: Final = "apps.identity.dev_oidc.code"
CODE_LIFETIME_SECONDS: Final = 600
ID_TOKEN_LIFETIME_SECONDS: Final = 3600
_KEY_CACHE: Final = "identity:dev_oidc:signing_key"
_USED_CODE_CACHE: Final = "identity:dev_oidc:used_code:"
_AUTHORIZE_PARAMS: Final = (
    "client_id",
    "redirect_uri",
    "response_type",
    "scope",
    "state",
    "nonce",
    "code_challenge",
    "code_challenge_method",
)
_NO_STORE: Final = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def _fake_only[ResponseT: HttpResponse](
    view: Callable[[HttpRequest], ResponseT],
) -> Callable[[HttpRequest], ResponseT]:
    """404 before anything else, the method included, unless the fake provider is on."""

    @wraps(view)
    def guarded(request: HttpRequest) -> ResponseT:
        if not fake_oidc_active():
            raise Http404
        return view(request)

    return guarded


def _signing_key() -> rsa.RSAPrivateKey:
    pem = cache.get(_KEY_CACHE)
    if pem is None:
        new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        new_pem = new_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        # add, not set: two workers racing keep the first key, and both sign with it.
        cache.add(_KEY_CACHE, new_pem, timeout=None)
        pem = cache.get(_KEY_CACHE, new_pem)
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)  # noqa: S101 - only this module writes the entry
    return key


def _kid(key: rsa.RSAPrivateKey) -> str:
    der = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(der).hexdigest()[:16]


def _back_to(redirect_uri: str, **params: str) -> HttpResponseRedirect:
    separator = "&" if "?" in redirect_uri else "?"
    response = HttpResponseRedirect(f"{redirect_uri}{separator}{urlencode(params)}")
    for name, value in _NO_STORE.items():
        response[name] = value
    return response


def _form(params: dict[str, str]) -> HttpResponse:
    hidden = format_html_join(
        "", '<input type="hidden" name="{}" value="{}">', sorted(params.items())
    )
    body = format_html(
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        "<title>Proveedor OIDC falso</title></head><body>"
        "<h1>Proveedor OIDC falso (solo desarrollo y test)</h1>"
        '<form method="get">{}'
        '<p><label>Email <input name="email" type="email" required></label></p>'
        '<p><label>Nombre <input name="name"></label></p>'
        '<p><label>Email verificado <select name="email_verified">'
        '<option value="true">sí</option><option value="false">no</option></select></label></p>'
        '<p><button type="submit">Ingresar</button> '
        '<button type="submit" name="cancel" value="1" formnovalidate>Cancelar</button></p>'
        "</form></body></html>",
        hidden,
    )
    return HttpResponse(body, content_type="text/html; charset=utf-8", headers=_NO_STORE)


@_fake_only
@require_GET
def authorize(request: HttpRequest) -> HttpResponse:
    params = {name: request.GET.get(name, "") for name in _AUTHORIZE_PARAMS}
    redirect_uri = settings.IDENTITY_GOOGLE_REDIRECT_URI
    if not redirect_uri or (params["client_id"], params["redirect_uri"]) != (
        settings.IDENTITY_GOOGLE_CLIENT_ID,
        redirect_uri,
    ):
        return HttpResponseBadRequest("unknown client_id or redirect_uri")
    state = params["state"]
    if request.GET.get("cancel"):
        return _back_to(redirect_uri, error="access_denied", state=state)
    well_formed = params["response_type"] == "code" and params["code_challenge_method"] == "S256"
    if not (well_formed and state and params["nonce"] and params["code_challenge"]):
        return _back_to(redirect_uri, error="invalid_request", state=state)
    email = request.GET.get("email", "").strip()
    if not email:
        return _form(params)
    claims = {
        "sub": "dev-" + hash_secret(normalize_email(email))[:24],
        "email": email,
        "email_verified": request.GET.get("email_verified", "true") == "true",
        "name": request.GET.get("name", "").strip(),
    }
    grant = {"claims": claims, "nonce": params["nonce"], "challenge": params["code_challenge"]}
    code = signing.dumps(grant, salt=CODE_SALT, compress=True)
    return _back_to(redirect_uri, code=code, state=state)


def _oauth_error(error: str, status: int) -> JsonResponse:
    return JsonResponse({"error": error}, status=status, headers=_NO_STORE)


def _verifier_matches(verifier: str, challenge: object) -> bool:
    try:
        computed = code_challenge_s256(verifier)
    except UnicodeEncodeError:
        return False
    return isinstance(challenge, str) and constant_time_compare(computed, challenge)


def _grant_of(code: str) -> dict[str, Any] | None:
    try:
        grant = signing.loads(code, salt=CODE_SALT, max_age=CODE_LIFETIME_SECONDS)
    except signing.BadSignature:
        return None
    return grant if isinstance(grant, dict) else None


@csrf_exempt
@_fake_only
@require_POST
def token(request: HttpRequest) -> JsonResponse:
    form = request.POST
    if form.get("grant_type") != "authorization_code":
        return _oauth_error("unsupported_grant_type", 400)
    client_id = settings.IDENTITY_GOOGLE_CLIENT_ID
    secret = settings.IDENTITY_GOOGLE_CLIENT_SECRET
    if not (
        secret
        and constant_time_compare(form.get("client_id", ""), client_id)
        and constant_time_compare(form.get("client_secret", ""), secret)
    ):
        return _oauth_error("invalid_client", 401)
    code = form.get("code", "")
    grant = _grant_of(code)
    if (
        grant is None
        or form.get("redirect_uri") != settings.IDENTITY_GOOGLE_REDIRECT_URI
        or not _verifier_matches(form.get("code_verifier", ""), grant.get("challenge"))
        # Single use, like Google's: the second exchange of a code is invalid_grant.
        or not cache.add(_USED_CODE_CACHE + hash_secret(code), True, CODE_LIFETIME_SECONDS)
    ):
        return _oauth_error("invalid_grant", 400)
    now = int(time.time())
    claims = {
        **grant["claims"],
        "iss": fake_issuer(),
        "aud": client_id,
        "nonce": grant["nonce"],
        "iat": now,
        "exp": now + ID_TOKEN_LIFETIME_SECONDS,
    }
    key = _signing_key()
    id_token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": _kid(key)})
    body = {"id_token": id_token, "token_type": "Bearer", "expires_in": ID_TOKEN_LIFETIME_SECONDS}
    return JsonResponse(body, headers=_NO_STORE)


@_fake_only
@require_GET
def jwks(request: HttpRequest) -> JsonResponse:
    key = _signing_key()
    jwk = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return JsonResponse({"keys": [{**jwk, "kid": _kid(key), "use": "sig", "alg": "RS256"}]})
