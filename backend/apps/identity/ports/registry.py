"""Resolves each port from its dotted path in settings (design.md §6.4).

No cache: the implementations hold no state, and swapping one takes only a setting.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string

from apps.identity.ports.audit import AuditPort
from apps.identity.ports.invitations import InvitationPort
from apps.identity.ports.memberships import MembershipSelectorPort


def _resolve(dotted_path: str) -> Any:
    return import_string(dotted_path)()


def get_invitation_port() -> InvitationPort:
    port: InvitationPort = _resolve(settings.IDENTITY_INVITATION_PORT)
    return port


def get_membership_selector() -> MembershipSelectorPort:
    selector: MembershipSelectorPort = _resolve(settings.IDENTITY_MEMBERSHIP_SELECTOR)
    return selector


def get_audit_port() -> AuditPort:
    port: AuditPort = _resolve(settings.IDENTITY_AUDIT_PORT)
    return port
