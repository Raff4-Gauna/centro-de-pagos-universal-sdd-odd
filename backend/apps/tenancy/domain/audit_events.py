"""Catalog of SPEC-02's audit events (RNF-TEN-04, RN-TEN-17, Q-225). Pure: no Django, no I/O.

Exactly the list of RNF-TEN-04, the three of the approval gate included (``invitation.expired``,
``invitation.auto_revoked``, ``transition.rejected``). Support access and owner recovery have no
event of their own: ``invitation.created`` carries their ``purpose`` (Q-225). Denied attempts on
another organization are not here: operational log and metric (Q-217).

The closed lists of reasons (``invitation.rejected``, ``invitation.auto_revoked``) arrive with the
services that emit them.
"""

from __future__ import annotations

from enum import StrEnum


class TenancyAuditAction(StrEnum):
    ORGANIZATION_CREATED = "organization.created"
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
