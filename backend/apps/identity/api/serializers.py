"""Shapes of the identity API (design.md §6.1, §6.2).

``/api/me/`` takes no input. ``MembershipSerializer`` mirrors ``MembershipSummary``, whose final
shape SPEC-02 fixes (``T-TEN-12``); identity passes the list along as the selector returns it.

The ``auth/bff/*`` ones are the BFF's, not the browser's (tag ``bff-internal``). Their errors never
echo the input (design.md §7.5): a length or type message names the limit, never the value.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.identity.domain.secrets_format import is_login_binding
from apps.identity.models import RevokeReason
from apps.identity.ports.memberships import MembershipSummary

BINDING_LENGTH = 43
# Bounds of what the BFF relays from Google's redirect: room for any real value, no more.
MAX_STATE_LENGTH = 512
MAX_CODE_LENGTH = 2048
MAX_ERROR_LENGTH = 256


class MembershipSerializer(serializers.Serializer[MembershipSummary]):
    organization_id = serializers.UUIDField(read_only=True)
    organization_name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)

    class Meta:
        ref_name = "Membership"


# The authenticated person (RN-IDA-18): identity plus active memberships. A comment, not a
# docstring: drf-spectacular would publish a docstring as the component's description.
class MeSerializer(serializers.Serializer[dict[str, Any]]):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    # Stored as '' when Google sends none or an unusable one; the contract says null.
    avatar_url = serializers.SerializerMethodField()
    memberships = MembershipSerializer(many=True, read_only=True)

    class Meta:
        ref_name = "Me"

    def get_avatar_url(self, me: dict[str, Any]) -> str | None:
        avatar_url: str = me["avatar_url"]
        return avatar_url or None


def _login_binding(value: str) -> None:
    if not is_login_binding(value):
        raise serializers.ValidationError("Formato inválido.", code="invalid")


def _binding_field() -> serializers.CharField:
    return serializers.CharField(
        min_length=BINDING_LENGTH,
        max_length=BINDING_LENGTH,
        trim_whitespace=False,
        validators=[_login_binding],
    )


# Comments, not docstrings: drf-spectacular would publish a docstring as the description.
# login_binding: 32 random bytes in base64url, created by the BFF (design.md §6.3).
# return_path: any text is accepted; one that is not an internal path is replaced, not refused.
class LoginStartRequestSerializer(serializers.Serializer[dict[str, Any]]):
    login_binding = _binding_field()
    return_path = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, trim_whitespace=False
    )

    class Meta:
        ref_name = "LoginStart"  # published as LoginStartRequest (split components)


class LoginStartResponseSerializer(serializers.Serializer[dict[str, Any]]):
    authorization_url = serializers.URLField(read_only=True)

    class Meta:
        ref_name = "LoginStartResponse"


# What Google's redirect brought to the BFF, plus the binding of __Host-cpu_login. A state that
# matches no attempt is google_auth_failed, not a validation error: an empty one too.
class LoginCompleteRequestSerializer(serializers.Serializer[dict[str, Any]]):
    state = serializers.CharField(
        max_length=MAX_STATE_LENGTH, allow_blank=True, trim_whitespace=False
    )
    login_binding = _binding_field()
    code = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=MAX_CODE_LENGTH,
        trim_whitespace=False,
    )
    error = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=MAX_ERROR_LENGTH,
        trim_whitespace=False,
    )

    class Meta:
        ref_name = "LoginComplete"  # published as LoginCompleteRequest (split components)


# The tokens go to the BFF only, which keeps them in __Host- cookies (design.md §7.1). Seconds.
class LoginCompleteResponseSerializer(serializers.Serializer[dict[str, Any]]):
    access_token = serializers.CharField(read_only=True)
    access_expires_in = serializers.IntegerField(read_only=True)
    refresh_token = serializers.CharField(read_only=True)
    session_id = serializers.UUIDField(read_only=True)
    session_expires_in = serializers.IntegerField(read_only=True)
    return_path = serializers.CharField(read_only=True)

    class Meta:
        ref_name = "LoginCompleteResponse"


# refresh_token: rt1.<sid>.<secret>, the one in __Host-cpu_rt (design.md §4.5).
class RefreshRequestSerializer(serializers.Serializer[dict[str, Any]]):
    refresh_token = serializers.CharField(trim_whitespace=False)

    class Meta:
        ref_name = "Refresh"  # published as RefreshRequest (split components)


# refresh_token is null in the grace window: the BFF then keeps the cookie it has (design.md §4.5).
# session_expires_in: seconds to the idle deadline, the Max-Age of __Host-cpu_rt (design.md §7.1).
class RefreshResponseSerializer(serializers.Serializer[dict[str, Any]]):
    access_token = serializers.CharField(read_only=True)
    access_expires_in = serializers.IntegerField(read_only=True)
    refresh_token = serializers.CharField(read_only=True, allow_null=True)
    session_expires_in = serializers.IntegerField(read_only=True)

    class Meta:
        ref_name = "RefreshResponse"


# Both optional: the BFF sends the cookies it has (design.md §4.6). access_token may be expired.
# reason: superseded only for the login over a previous session (ADR-0004 §13); logout by default.
class LogoutRequestSerializer(serializers.Serializer[dict[str, Any]]):
    refresh_token = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, trim_whitespace=False
    )
    access_token = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, trim_whitespace=False
    )
    reason = serializers.ChoiceField(
        choices=[RevokeReason.LOGOUT.value, RevokeReason.SUPERSEDED.value], required=False
    )

    class Meta:
        ref_name = "Logout"  # published as LogoutRequest (split components)
