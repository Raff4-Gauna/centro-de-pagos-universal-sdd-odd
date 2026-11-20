"""The memberships as the API shows them and the shape of what it takes (RF-TEN-04, design.md §6).

``member_view(member, ctx, owners=, actor_role=)`` adds what the UI needs to decide what to offer
on each row (design.md §3.9, Colaboradores), and nothing it could act on by itself: the service
decides again under the lock. ``allowed_actions`` are the actions of SPEC-02 on that membership
that the matrix lets through now (``authz.checks.allowed_actions``: role and suspension) *and* that
``domain.role_rules`` allows on that target with ``owners`` active owners: ``member.change_role``
when some role can be assigned, ``member.revoke`` on someone else's, ``member.leave`` on one's own.
``assignable_roles`` are the roles ``decide_role_change`` allows (never the current one). A
``revoked`` membership gets neither. ``actor_role`` is the actor's role when it is no longer the one
the request resolved (it just changed its own); on its own row the row's role rules.

``MembershipRoleSerializer`` is strict (design.md §6): a key other than ``role`` is
``400 validation_error`` with ``unknown_field`` (AC-TEN-07), and the role is one of ``Role``.

Comments instead of docstrings on the serializer classes: drf-spectacular would publish a docstring
as the component's description.
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
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.domain.role_rules import (
    Decision,
    decide_leave,
    decide_revoke,
    decide_role_change,
)
from apps.tenancy.models.membership import EndedReason, MembershipStatus
from apps.tenancy.selectors.memberships import Member
from apps.tenancy.services.fields import unknown_field_errors

_ROW_ACTIONS = (
    TenancyAction.MEMBER_CHANGE_ROLE,
    TenancyAction.MEMBER_REVOKE,
    TenancyAction.MEMBER_LEAVE,
)


@dataclass(frozen=True, slots=True)
class MemberUser:
    id: uuid.UUID
    email: str
    name: str


@dataclass(frozen=True, slots=True)
class MemberView:
    id: uuid.UUID
    user: MemberUser
    role: Role
    status: MembershipStatus
    ended_reason: EndedReason | None
    created_at: datetime
    allowed_actions: list[str]
    assignable_roles: list[Role]


def member_view(
    member: Member, ctx: TenantContext, *, owners: int, actor_role: Role | None = None
) -> MemberView:
    actor = ctx.actor
    if not isinstance(actor, UserActor):  # member.list has no API key scope: only a person
        raise Forbidden
    actions: list[str] = []
    assignable: list[Role] = []
    if member.status is MembershipStatus.ACTIVE:
        is_self = member.id == actor.membership_id
        role = member.role if is_self else (actor_role or actor.role)
        gated = set(allowed_actions(ctx, [TENANCY_ACTIONS[a] for a in _ROW_ACTIONS]))
        if TenancyAction.MEMBER_CHANGE_ROLE.value in gated:
            assignable = [
                new
                for new in Role
                if decide_role_change(role, member.role, new, is_self=is_self, active_owners=owners)
                is Decision.ALLOW
            ]
        if assignable:
            actions.append(TenancyAction.MEMBER_CHANGE_ROLE.value)
        if is_self:
            leave = decide_leave(role, active_owners=owners)
            if TenancyAction.MEMBER_LEAVE.value in gated and leave is Decision.ALLOW:
                actions.append(TenancyAction.MEMBER_LEAVE.value)
        elif TenancyAction.MEMBER_REVOKE.value in gated:
            revoke = decide_revoke(role, member.role, active_owners=owners)
            if revoke is Decision.ALLOW:
                actions.append(TenancyAction.MEMBER_REVOKE.value)
    return MemberView(
        id=member.id,
        user=MemberUser(member.user_id, member.email, member.name),
        role=member.role,
        status=member.status,
        ended_reason=member.ended_reason,
        created_at=member.created_at,
        allowed_actions=actions,
        assignable_roles=assignable,
    )


_ROLES = [r.value for r in Role]


# The person of a membership: their id, Google email and display name (owner and admin only).
class MemberUserSerializer(serializers.Serializer[MemberUser]):
    id = serializers.UUIDField(read_only=True)
    email = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)

    class Meta:
        ref_name = "OrganizationMemberUser"


# One membership of the active organization and what the person asking may do with it.
class MembershipSerializer(serializers.Serializer[MemberView]):
    id = serializers.UUIDField(read_only=True)
    user = MemberUserSerializer(read_only=True)
    role = serializers.ChoiceField(choices=_ROLES, read_only=True)
    status = serializers.ChoiceField(choices=[s.value for s in MembershipStatus], read_only=True)
    ended_reason = serializers.ChoiceField(
        choices=[r.value for r in EndedReason], read_only=True, allow_null=True
    )
    created_at = serializers.DateTimeField(read_only=True)
    allowed_actions = serializers.ListField(
        child=serializers.ChoiceField(choices=[a.value for a in TenancyAction]), read_only=True
    )
    assignable_roles = serializers.ListField(
        child=serializers.ChoiceField(choices=_ROLES), read_only=True
    )

    class Meta:
        ref_name = "OrganizationMember"  # "Membership" is SPEC-01's /api/me summary


# The new role of the membership; no other key is accepted.
class MembershipRoleSerializer(serializers.Serializer[dict[str, Any]]):
    role = serializers.ChoiceField(choices=_ROLES)

    class Meta:
        ref_name = "MembershipRoleUpdate"  # published as PatchedMembershipRoleUpdateRequest

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if isinstance(data, Mapping) and (unknown := unknown_field_errors(data, self.fields)):
            raise ValidationError(unknown)
        validated: dict[str, Any] = super().to_internal_value(data)
        return validated

    def new_role(self) -> Role:
        return Role(self.validated_data["role"])


# ?status=active (default) or revoked.
class MembershipListQuerySerializer(serializers.Serializer[dict[str, Any]]):
    status = serializers.ChoiceField(
        choices=[s.value for s in MembershipStatus],
        required=False,
        default=MembershipStatus.ACTIVE.value,
        help_text="active (por defecto): las vigentes · revoked: las revocadas o abandonadas.",
    )

    def membership_status(self) -> MembershipStatus:
        return MembershipStatus(self.validated_data["status"])
