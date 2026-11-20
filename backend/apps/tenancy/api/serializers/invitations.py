"""Accepting an invitation as the API reads and answers it (design.md §6, §7).

``InvitationAcceptSerializer`` takes the token ``write_only``: it is never part of a response, and
a wrong one is never echoed (its errors are fixed messages). Strict like every body of SPEC-02
(design.md §6): any other key is ``400 validation_error`` with ``unknown_field``
(``services/fields.py``), and nothing is accepted. ``TOKEN_MAX_LENGTH`` bounds what is
hashed; a real token is 43 characters (``secrets.token_urlsafe(32)``).
``AcceptedInvitationSerializer`` is the ``200`` of both accept routes: ``{organization:{id, name},
role, membership_id}``.

The invitations of the active organization (``GET``/``POST /api/invitations/``, design.md §6):
``InvitationCreateSerializer`` takes ``{email, role}``, strict as well, the email through
``services.invitations.normalized_email`` (normalized, ``EmailValidator``, at most 254).
``InvitationSerializer`` is one row: ``{id, email, role, status, purpose, expires_at, invited_by,
created_at, allowed_actions}``, never the token nor its hash; ``invited_by`` is the person who
issued it (``OrganizationMemberUser``) or ``null`` for the platform operator.
``invitation_view(invitation, ctx, actor_role=)`` adds ``allowed_actions``: ``invitation.resend``
and ``invitation.revoke`` when the matrix lets them through now (role and suspension) *and*
``decide_manage_invitation`` allows them on that invitation's role (an admin never manages an
``owner`` one, Q-202). ``CreatedInvitationSerializer`` is the ``201``: the row plus ``accept_url``,
the only response that ever carries the token (RNF-TEN-03, AC-TEN-24).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.common.authz.checks import allowed_actions
from apps.common.authz.roles import Role
from apps.common.tenancy.context import TenantContext, UserActor
from apps.common.tenancy.errors import Forbidden
from apps.tenancy.api.serializers.memberships import MemberUserSerializer
from apps.tenancy.domain.invitations import InvitationPurpose, InvitationStatus
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.domain.role_rules import Decision, decide_manage_invitation
from apps.tenancy.selectors.invitations import Inviter, OrganizationInvitation
from apps.tenancy.services.fields import unknown_field_errors
from apps.tenancy.services.invitation_accept import AcceptedInvitation
from apps.tenancy.services.invitations import INVALID_EMAIL, normalized_email

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


_ROLES = [r.value for r in Role]
_ROW_ACTIONS = (TenancyAction.INVITATION_RESEND, TenancyAction.INVITATION_REVOKE)


@dataclass(frozen=True, slots=True)
class InvitationView:
    id: uuid.UUID
    email: str
    role: Role
    status: InvitationStatus
    purpose: InvitationPurpose
    expires_at: datetime
    invited_by: Inviter | None
    created_at: datetime
    allowed_actions: list[str]


def invitation_view(
    invitation: OrganizationInvitation, ctx: TenantContext, *, actor_role: Role | None = None
) -> InvitationView:
    """``actor_role``: the actor's role read under the lock, when it is not the request's."""
    actor = ctx.actor
    if not isinstance(actor, UserActor):  # invitation.* has no API key scope: only a person
        raise Forbidden
    role = actor_role or actor.role
    actions: list[str] = []
    if invitation.status is InvitationStatus.PENDING:
        gated = set(allowed_actions(ctx, [TENANCY_ACTIONS[a] for a in _ROW_ACTIONS]))
        if decide_manage_invitation(role, invitation.role) is Decision.ALLOW:
            actions = [
                action.value
                for action in _ROW_ACTIONS
                if action.value in gated and role in TENANCY_ACTIONS[action].roles
            ]
    return InvitationView(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status=invitation.status,
        purpose=invitation.purpose,
        expires_at=invitation.expires_at,
        invited_by=invitation.invited_by,
        created_at=invitation.created_at,
        allowed_actions=actions,
    )


# Who to invite and with which role; no other key is accepted.
class InvitationCreateSerializer(serializers.Serializer[dict[str, Any]]):
    email = serializers.CharField(trim_whitespace=False)
    role = serializers.ChoiceField(choices=_ROLES)

    class Meta:
        ref_name = "InvitationCreate"

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if isinstance(data, Mapping) and (unknown := unknown_field_errors(data, self.fields)):
            raise ValidationError(unknown)
        validated: dict[str, Any] = super().to_internal_value(data)
        return validated

    def validate_email(self, value: str) -> str:
        email = normalized_email(value)
        if email is None:  # a fixed message: the value is never repeated
            raise ValidationError(INVALID_EMAIL, code="invalid")
        return email

    def invitee_email(self) -> str:
        return str(self.validated_data["email"])

    def invited_role(self) -> Role:
        return Role(self.validated_data["role"])


# One invitation of the active organization and what the person asking may do with it.
class InvitationSerializer(serializers.Serializer[InvitationView]):
    id = serializers.UUIDField(read_only=True)
    email = serializers.CharField(read_only=True)
    role = serializers.ChoiceField(choices=_ROLES, read_only=True)
    status = serializers.ChoiceField(choices=[s.value for s in InvitationStatus], read_only=True)
    purpose = serializers.ChoiceField(choices=[p.value for p in InvitationPurpose], read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)
    invited_by = MemberUserSerializer(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)
    allowed_actions = serializers.ListField(
        child=serializers.ChoiceField(choices=[a.value for a in TenancyAction]), read_only=True
    )

    class Meta:
        ref_name = "OrganizationInvitation"


# The invitation just created and its link with the token, shown this once: copy it now.
class CreatedInvitationSerializer(InvitationSerializer):
    accept_url = serializers.CharField(read_only=True)

    class Meta:
        ref_name = "CreatedInvitation"
