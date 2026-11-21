"""Catalog of SPEC-02's audit events (RNF-TEN-04, RN-TEN-17, Q-225). Pure: no Django, no I/O.

Exactly the list of RNF-TEN-04, the three of the approval gate included (``invitation.expired``,
``invitation.auto_revoked``, ``transition.rejected``), plus ``organization.create_repeated``
(Q-235: RN-IDA-23 audits every run of the operator's bootstrap command, a repeat too) and
``operator_command.rejected`` (Q-237: the refusals of the other operator commands, with an
``OperatorRefusal`` code). Support
access and owner recovery have no event of their own: ``invitation.created`` carries their
``purpose`` (Q-225). Denied attempts on another organization are not here: operational log and
metric (Q-217).

The closed lists of reasons (``invitation.rejected``, ``invitation.auto_revoked``) arrive with the
services that emit them; ``OperatorRefusal`` is the one of ``operator_command.rejected``.
"""

from __future__ import annotations

from enum import StrEnum


class TenancyAuditAction(StrEnum):
    ORGANIZATION_CREATED = "organization.created"
    # Q-235 (2026-11-20): every repeat of tenancy_create_org's --key, outcome no_change | conflict.
    ORGANIZATION_CREATE_REPEATED = "organization.create_repeated"
    ORGANIZATION_UPDATED = "organization.updated"
    ORGANIZATION_SUSPENDED = "organization.suspended"
    ORGANIZATION_REACTIVATED = "organization.reactivated"
    MEMBERSHIP_CREATED = "membership.created"
    MEMBERSHIP_ROLE_CHANGED = "membership.role_changed"
    MEMBERSHIP_REVOKED = "membership.revoked"
    MEMBERSHIP_LEFT = "membership.left"
    INVITATION_CREATED = "invitation.created"
    INVITATION_RESENT = "invitation.resent"
    INVITATION_REVOKED = "invitation.revoked"
    INVITATION_ACCEPTED = "invitation.accepted"
    INVITATION_REJECTED = "invitation.rejected"
    INVITATION_EXPIRED = "invitation.expired"
    INVITATION_AUTO_REVOKED = "invitation.auto_revoked"
    BRANCH_CREATED = "branch.created"
    BRANCH_UPDATED = "branch.updated"
    BRANCH_DEACTIVATED = "branch.deactivated"
    BRANCH_REACTIVATED = "branch.reactivated"
    OWNER_PROTECTION_REJECTED = "owner_protection.rejected"
    TRANSITION_REJECTED = "transition.rejected"
    # Q-237 (2026-11-21): a refusal of an operator command that changes nothing (exit 1).
    OPERATOR_COMMAND_REJECTED = "operator_command.rejected"


class OperatorRefusal(StrEnum):
    """Why an operator command was refused (Q-237): the event's ``reason``, never free text.

    A refusal by state is not here: it is ``transition.rejected`` (C-05, AC-TEN-37).
    """

    ORGANIZATION_NOT_FOUND = "organization_not_found"
    ORGANIZATION_HAS_OWNER = "organization_has_owner"
    ORGANIZATION_WITHOUT_OWNER = "organization_without_owner"
    NO_OWNER_INVITATION = "no_owner_invitation"
    ALREADY_MEMBER = "already_member"
    INVITATION_PENDING = "invitation_pending"
    NOT_CONFIGURED = "not_configured"
