"""Accepting an invitation as the API reads and answers it (design.md §6, §7).

``InvitationAcceptSerializer`` takes the token ``write_only``: it is never part of a response, and
a wrong one is never echoed (its errors are fixed messages). Strict like every body of SPEC-02
(design.md §6): any other key is ``400 validation_error`` with ``unknown_field``
(``services/fields.py``), and nothing is accepted. ``TOKEN_MAX_LENGTH`` bounds what is
hashed; a real token is 43 characters (``secrets.token_urlsafe(32)``).
``AcceptedInvitationSerializer`` is the ``200`` of both accept routes: ``{organization:{id, name},
role, membership_id}``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.common.authz.roles import Role
from apps.tenancy.services.fields import unknown_field_errors
from apps.tenancy.services.invitation_accept import AcceptedInvitation

TOKEN_MAX_LENGTH = 128


class InvitationAcceptSerializer(serializers.Serializer[dict[str, Any]]):
    token = serializers.CharField(
        write_only=True, max_length=TOKEN_MAX_LENGTH, trim_whitespace=True
    )

    class Meta:
        ref_name = "InvitationAccept"

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if isinstance(data, Mapping) and (unknown := unknown_field_errors(data, self.fields)):
            raise ValidationError(unknown)
        validated: dict[str, Any] = super().to_internal_value(data)
        return validated


# The organization the person joined. A comment, not a docstring: drf-spectacular would publish it.
class JoinedOrganizationSerializer(serializers.Serializer[AcceptedInvitation]):
    id = serializers.UUIDField(source="organization_id", read_only=True)
    name = serializers.CharField(source="organization_name", read_only=True)

    class Meta:
        ref_name = "JoinedOrganization"


# The membership the accepted invitation created, and in which organization.
class AcceptedInvitationSerializer(serializers.Serializer[AcceptedInvitation]):
    organization = JoinedOrganizationSerializer(source="*", read_only=True)
    role = serializers.ChoiceField(choices=[r.value for r in Role], read_only=True)
    membership_id = serializers.UUIDField(read_only=True)

    class Meta:
        ref_name = "AcceptedInvitation"
