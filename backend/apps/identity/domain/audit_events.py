"""Catalog of identity's audit events (RN-IDA-17, Q-117, design.md §7.4). Pure: no Django, no I/O.

Left out on purpose: ``429``, ``google_unavailable`` and ``login_cancelled`` go only to logs and
metrics (Q-111, design.md §4.2), and ``organization.created`` + ``invitation.created`` belong to
SPEC-02's catalog.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class IdentityAuditAction(StrEnum):
    LOGIN_SUCCEEDED = "identity.login_succeeded"
    LOGIN_REJECTED = "identity.login_rejected"
    USER_CREATED_BY_INVITATION = "identity.user_created_by_invitation"
    LOGOUT = "identity.logout"
    SESSION_REVOKED = "identity.session_revoked"
    REFRESH_REUSE_DETECTED = "identity.refresh_reuse_detected"
    USER_DEACTIVATED = "identity.user_deactivated"
    USER_REACTIVATED = "identity.user_reactivated"
    EMAIL_CHANGED = "identity.email_changed"
    EMAIL_CHANGE_COLLISION = "identity.email_change_collision"


class LoginRejectionReason(StrEnum):
    GOOGLE_AUTH_FAILED = "google_auth_failed"
    EMAIL_NOT_VERIFIED = "email_not_verified"
    NOT_INVITED = "not_invited"
    USER_INACTIVE = "user_inactive"
    IDENTITY_CONFLICT = "identity_conflict"


class SessionRevocationReason(StrEnum):
    """Revocations other than logout, which has an event of its own."""

    USER_REVOKED = "user_revoked"
    REVOKED_OTHERS = "revoked_others"
    USER_DEACTIVATED = "user_deactivated"
    REFRESH_REUSE = "refresh_reuse"
    SUPERSEDED = "superseded"


class AuditActorType(StrEnum):
    USER = "user"
    ANONYMOUS = "anonymous"
    PLATFORM_OPERATOR = "platform_operator"
    SYSTEM = "system"


class AuditResult(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


# The actions whose reason is a closed list: an event of these without one of its reasons is a bug.
AUDIT_REASONS: Mapping[IdentityAuditAction, frozenset[str]] = {
    IdentityAuditAction.LOGIN_REJECTED: frozenset(LoginRejectionReason),
    IdentityAuditAction.SESSION_REVOKED: frozenset(SessionRevocationReason),
}
