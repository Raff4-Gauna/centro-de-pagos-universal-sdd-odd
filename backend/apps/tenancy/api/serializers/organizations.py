"""The active organization as the API shows and edits it (RF-TEN-03, design.md §6).

``OrganizationUpdateSerializer`` is strict (design.md §6): a key that is not one of the four
editable fields (``status``, ``id``, ``organization_id``, a typo) is ``400 validation_error`` with
code ``unknown_field`` on that key, and nothing is written (AC-TEN-29). The service normalizes
and validates the values again (``services/organizations.py``): this only checks their shape.

``current_organization(organization, ctx)`` adds what the UI needs to decide what to show
(design.md §3.9, ``/configuracion/empresa``): the actor's role and membership, the actions of
SPEC-02 it may run now (``authz.checks.allowed_actions``: role and suspension) and the roles it may
invite with (none if it may not invite).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.common.authz.checks import allowed_actions
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus, TenantContext, UserActor
from apps.common.tenancy.errors import Forbidden
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.domain.role_rules import Decision, decide_invite
from apps.tenancy.models import Organization
from apps.tenancy.services.fields import unknown_field_errors
from apps.tenancy.services.organizations import (
    LEGAL_NAME_MAX_LENGTH,
    NAME_MAX_LENGTH,
)


@dataclass(frozen=True, slots=True)
class CurrentOrganization:
    id: uuid.UUID
    name: str
    legal_name: str
    tax_id: str
    timezone: str
    status: OrgStatus
    my_role: Role
    my_membership_id: uuid.UUID
    allowed_actions: list[str]
    invitable_roles: list[Role]


def current_organization(organization: Organization, ctx: TenantContext) -> CurrentOrganization:
    actor = ctx.actor
    if not isinstance(actor, UserActor):  # org.read has no API key scope: only a person gets here
        raise Forbidden
    allowed = allowed_actions(ctx, TENANCY_ACTIONS.values())
    may_invite = TenancyAction.INVITATION_CREATE.value in allowed
    return CurrentOrganization(
        id=organization.pk,
        name=organization.name,
        legal_name=organization.legal_name,
        tax_id=organization.tax_id,
        timezone=organization.timezone,
        status=OrgStatus(organization.status),
        my_role=actor.role,
        my_membership_id=actor.membership_id,
        allowed_actions=allowed,
        invitable_roles=[
            role
            for role in Role
            if may_invite and decide_invite(actor.role, role) is Decision.ALLOW
        ],
    )


# The active organization and what the person asking may do in it. A comment, not a docstring:
# drf-spectacular would publish a docstring as the component's description.
class CurrentOrganizationSerializer(serializers.Serializer[CurrentOrganization]):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    legal_name = serializers.CharField(read_only=True)
    tax_id = serializers.CharField(read_only=True)
    timezone = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=[s.value for s in OrgStatus], read_only=True)
    my_role = serializers.ChoiceField(choices=[r.value for r in Role], read_only=True)
    my_membership_id = serializers.UUIDField(read_only=True)
    allowed_actions = serializers.ListField(
        child=serializers.ChoiceField(choices=[a.value for a in TenancyAction]), read_only=True
    )
    invitable_roles = serializers.ListField(
        child=serializers.ChoiceField(choices=[r.value for r in Role]), read_only=True
    )

    class Meta:
        ref_name = "CurrentOrganization"


# Any of the four, alone or together; empty clears legal_name and tax_id. tax_id: 11 digits, plain
# or XX-XXXXXXXX-X, with a valid check digit; timezone: an IANA name.
class OrganizationUpdateSerializer(serializers.Serializer[dict[str, Any]]):
    name = serializers.CharField(required=False, max_length=NAME_MAX_LENGTH)
    legal_name = serializers.CharField(
        required=False, allow_blank=True, max_length=LEGAL_NAME_MAX_LENGTH
    )
    tax_id = serializers.CharField(required=False, allow_blank=True, max_length=13)
    timezone = serializers.CharField(required=False, max_length=64)

    class Meta:
        ref_name = "OrganizationUpdate"  # published as PatchedOrganizationUpdateRequest

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if isinstance(data, Mapping) and (unknown := unknown_field_errors(data, self.fields)):
            raise ValidationError(unknown)
        validated: dict[str, Any] = super().to_internal_value(data)
        return validated
