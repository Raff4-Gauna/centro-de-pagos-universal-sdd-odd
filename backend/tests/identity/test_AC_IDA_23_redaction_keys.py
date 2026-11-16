"""The log redaction knows identity's secrets (design.md §7.5, RN-IDA-16, AC-IDA-23, C-06).

The services never log these values (``api/test_AC_IDA_23_no_secrets.py``); this is the net under
that rule: a careless event that names one of them by its key, or a text that carries them as a
query string or a form body, loses the value. ``domain/redaction.py`` is pure, so no Django here.
"""

from __future__ import annotations

import pytest

from apps.common.domain.redaction import REDACTED, redact_mapping, redact_text

VALUE = "value-that-must-not-be-logged"

# design.md §7.5, as written there (the header names in their HTTP form).
DESIGN_KEYS = (
    "access_token",
    "refresh_token",
    "id_token",
    "code",
    "code_verifier",
    "state",
    "nonce",
    "login_binding",
    "authorization",
    "cookie",
    "set-cookie",
    "client_secret",
    "x-hub-bff-credential",
    "x-csrf-token",
)


@pytest.mark.parametrize("key", DESIGN_KEYS)
def test_AC_IDA_23_design_key_is_redacted(key: str) -> None:
    assert redact_mapping({key: VALUE}) == {key: REDACTED}


@pytest.mark.parametrize("key", ["nonce_hash", "binding_hash", "LOGIN_BINDING", "codeVerifier"])
def test_AC_IDA_23_key_holding_a_secret_part_is_redacted(key: str) -> None:
    assert redact_mapping({key: VALUE}) == {key: REDACTED}


@pytest.mark.parametrize(
    "text",
    [
        f"code={VALUE}&state={VALUE}",
        f"grant_type=authorization_code&code={VALUE}&code_verifier={VALUE}",
        f"nonce={VALUE}",
        f'{{"login_binding": "{VALUE}"}}',
    ],
)
def test_AC_IDA_23_form_or_query_text_loses_the_values(text: str) -> None:
    assert VALUE not in redact_text(text)


@pytest.mark.parametrize(
    "event",
    [
        # Only the exact ``code`` key is OAuth's: the statuses, the catalog codes under their own
        # names and the reason or decision of an auth event survive.
        {"status_code": 429},
        {"error_code": "token_invalid"},
        {"reason": "google_auth_failed"},
        {"decision": "rotate"},
        {"state_changed": True},
    ],
)
def test_AC_IDA_23_names_that_only_contain_code_or_state_are_kept(event: dict[str, object]) -> None:
    assert redact_mapping(event) == event


def test_AC_IDA_23_text_with_a_code_that_is_no_form_field_is_kept() -> None:
    # Only ``code=``/``state=`` in a text are a query string or a form; a JSON problem quoted in a
    # message or "exit code: 1" keep their value.
    for text in ('{"code": "rate_limited"}', "exit code: 1", "state: active"):
        assert redact_text(text) == text


@pytest.mark.parametrize(
    "key", ["oauth_code", "auth_code", "authorization_code", "oauth_state", "google_code"]
)
def test_AC_IDA_23_oauth_code_or_state_with_a_provider_prefix_is_redacted(key: str) -> None:
    assert redact_mapping({key: VALUE}) == {key: REDACTED}
    assert VALUE not in redact_text(f"{key}={VALUE}")


JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJlLW9mLXRoZS10b2tlbg"
REFRESH = "rt1.AAAAAAAAAAAAAAAAAAAAAA." + "B" * 43


@pytest.mark.parametrize("secret", [JWT, REFRESH])
def test_AC_IDA_23_bare_hub_token_in_free_text_is_redacted(secret: str) -> None:
    for text in (secret, f"refused {secret} again", f"('{secret}',)"):
        redacted = redact_text(text)
        assert secret not in redacted
        assert REDACTED in redacted
