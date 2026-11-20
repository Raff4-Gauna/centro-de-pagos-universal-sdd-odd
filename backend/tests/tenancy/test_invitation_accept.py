"""Accept an invitation (``services/invitation_accept.py``): AC-TEN-17/18/19/25/35, RN-TEN-11/12.

The service is called the way each entry point calls it: ``accept_by_token`` (T-TEN-15) and
``accept_invitation`` with the reference of a row (T-TEN-16). The concurrent double accept lives
in ``test_invitation_accept_race.py`` (``transaction=True``); the route, in ``api/``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.common.audit.port import AuditActor, AuditActorKind, get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.common.tenancy.current import current_tenant
from apps.common.tenancy.errors import OrganizationSuspended
from apps.common.tenancy.querysets import TenantScopeError
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.invitations import InvalidReason, InvitationStatus, hash_token
from apps.tenancy.models import Invitation, Organization
from apps.tenancy.selectors.invitations import InvitationRef, find_by_token
from apps.tenancy.services.audit import AUDIT_TRIGGERS
from apps.tenancy.services.invitation_accept import (
    AlreadyMember,
    InvitationInvalid,
    accept_by_token,
    accept_invitation,
)
from tests.tenancy.api.probe import PLATFORM, add_member, new_org, new_user
from tests.tenancy.invitation_setup import invitee, issue, memberships, set_status, status_of

pytestmark = pytest.mark.django_db


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


def refused(token: str, who: object, reason: InvalidReason, **kwargs: object) -> None:
    with pytest.raises(InvitationInvalid) as raised:
        accept_by_token(token, who, **kwargs)  # type: ignore[arg-type]
    assert raised.value.problem_reason == reason.value


def actions(sink: RecordingSink) -> list[str]:
    return [event.action for event in sink.events]


# --- AC-TEN-17 -----------------------------------------------------------------------------------


def test_AC_TEN_17_accept_creates_membership(recorded: RecordingSink) -> None:
    org = new_org("A")
    invitation, token = issue(org, "x@dominio.com", Role.OPERATOR)
    user = new_user("x")
    user.email = "x@dominio.com"
    user.save(update_fields=["email"])

    accepted = accept_by_token(token, invitee(user))

    [(organization_id, role, status, source)] = memberships(user)
    assert (organization_id, role, status, source) == (org.id, "operator", "active", invitation.id)
    assert (accepted.organization_id, accepted.organization_name) == (org.id, "A")
    assert accepted.role is Role.OPERATOR
    assert status_of(invitation) == InvitationStatus.ACCEPTED
    assert actions(recorded) == ["membership.created", "invitation.accepted"]
    person = AuditActor(kind=AuditActorKind.USER, id=user.pk)
    for event in recorded.events:
        assert (event.actor, event.organization_id) == (person, org.id)
        assert event.metadata["membership_id"] == str(accepted.membership_id)
    assert current_tenant() is None  # the scope of the invitation's organization was closed


def test_AC_TEN_17_second_use_of_the_token_is_used() -> None:
    org = new_org("A")
    _, token = issue(org, "ana@hub.test")
    ana = new_user("ana")
    accept_by_token(token, invitee(ana))

    refused(token, invitee(ana), InvalidReason.USED)
    assert len(memberships(ana)) == 1


def test_AC_TEN_17_audit_triggers_point_at_the_shared_service() -> None:
    for action in (
        TenancyAuditAction.INVITATION_ACCEPTED,
        TenancyAuditAction.MEMBERSHIP_CREATED,
        TenancyAuditAction.INVITATION_REJECTED,
    ):
        assert AUDIT_TRIGGERS[action] is accept_invitation


def test_AC_TEN_17_unknown_token_is_not_found(recorded: RecordingSink) -> None:
    refused("not-a-token-anyone-issued", invitee(new_user("ana")), InvalidReason.NOT_FOUND)
    assert recorded.events == []


# --- AC-TEN-18 -----------------------------------------------------------------------------------


def test_AC_TEN_18_other_email_keeps_pending(recorded: RecordingSink) -> None:
    org = new_org("A")
    invitation, token = issue(org, "x@dominio.com")
    beto = new_user("beto")

    refused(token, invitee(beto), InvalidReason.EMAIL_MISMATCH)

    assert memberships(beto) == []
    assert status_of(invitation) == InvitationStatus.PENDING
    [event] = recorded.events
    assert event.action == "invitation.rejected"
    assert (event.reason, event.organization_id) == ("email_mismatch", org.id)
    assert event.actor == AuditActor(kind=AuditActorKind.USER, id=beto.pk)
    assert event.metadata == {"invitation_id": str(invitation.id)}  # no email of anyone


def test_AC_TEN_18_from_the_session_other_email_answers_not_found(
    recorded: RecordingSink,
) -> None:
    """T-TEN-16's contract has no ``email_mismatch``: the same service, ``mismatch=NOT_FOUND``."""
    org = new_org("A")
    invitation, _ = issue(org, "x@dominio.com")
    ref = InvitationRef(invitation.id, org.id)

    with pytest.raises(InvitationInvalid) as raised:
        accept_invitation(ref, invitee(new_user("beto")), mismatch=InvalidReason.NOT_FOUND)

    assert raised.value.problem_reason == "not_found"
    assert [e.reason for e in recorded.events] == ["email_mismatch"]  # the audit says what it was
    with pytest.raises(ValueError, match="email_mismatch or not_found"):
        accept_invitation(ref, invitee(new_user("ana")), mismatch=InvalidReason.USED)


# --- AC-TEN-19 -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (InvitationStatus.EXPIRED, InvalidReason.EXPIRED),
        (InvitationStatus.REVOKED, InvalidReason.REVOKED),
    ],
)
def test_AC_TEN_19_expired_or_revoked(
    status: InvitationStatus, reason: InvalidReason, recorded: RecordingSink
) -> None:
    org = new_org("A")
    invitation, token = issue(org, "ana@hub.test")
    set_status(invitation, status)
    ana = new_user("ana")

    refused(token, invitee(ana), reason)

    assert memberships(ana) == []
    assert status_of(invitation) == status
    assert recorded.events == []


# --- AC-TEN-25 -----------------------------------------------------------------------------------


def test_AC_TEN_25_at_seven_days(recorded: RecordingSink) -> None:
    org = new_org("A")
    issued = timezone.now()
    ana, beto = new_user("ana"), new_user("beto")
    early, early_token = issue(org, "ana@hub.test", expires_at=issued + timedelta(days=7))
    late, late_token = issue(org, "beto@hub.test", expires_at=issued + timedelta(days=7))

    accept_by_token(early_token, invitee(ana), now=early.expires_at - timedelta(minutes=1))
    refused(late_token, invitee(beto), InvalidReason.EXPIRED, now=late.expires_at)

    assert len(memberships(ana)) == 1
    assert memberships(beto) == []
    assert status_of(late) == InvitationStatus.EXPIRED  # committed, not rolled back with the 400
    expired = [e for e in recorded.events if e.action == "invitation.expired"]
    assert [e.actor.kind for e in expired] == [AuditActorKind.SYSTEM]  # Q-225
    assert expired[0].metadata == {"invitation_id": str(late.id)}
    refused(late_token, invitee(beto), InvalidReason.EXPIRED)  # and stays so


# --- AC-TEN-35 -----------------------------------------------------------------------------------


def test_AC_TEN_35_case_and_alias() -> None:
    org = new_org("A")
    invitation, token = issue(org, " X@Dominio.com ")
    alias, x = new_user("alias"), new_user("x")

    refused(token, invitee(alias, "x+1@dominio.com"), InvalidReason.EMAIL_MISMATCH)
    refused(token, invitee(alias, "x.@dominio.com"), InvalidReason.EMAIL_MISMATCH)
    assert status_of(invitation) == InvitationStatus.PENDING

    accept_by_token(token, invitee(x, " x@DOMINIO.com"))
    assert [row[3] for row in memberships(x)] == [invitation.id]


# --- What the database cannot stop: the organization of the invitation (review of PR #119) ------


def test_RN_TEN_12_membership_lands_in_the_invitations_organization() -> None:
    """Ana is a member of A and accepts B's invitation: the membership is B's, A is untouched."""
    a, b = new_org("A"), new_org("B")
    ana = new_user("ana")
    add_member(a, ana, Role.OWNER)
    invitation, token = issue(b, "ana@hub.test", Role.VIEWER)

    accept_by_token(token, invitee(ana))

    rows = memberships(ana)
    assert [(r[0], r[1], r[3]) for r in rows] == [
        (a.id, "owner", None),
        (b.id, "viewer", invitation.id),
    ]


def test_RN_TEN_12_reference_with_another_organization_is_not_found() -> None:
    """A reference that pairs B's invitation with A finds nothing under A's scope: no membership
    in A nor in B, and B's invitation stays ``pending``."""
    a, b = new_org("A"), new_org("B")
    invitation, _ = issue(b, "ana@hub.test")
    ana = new_user("ana")

    with pytest.raises(InvitationInvalid) as raised:
        accept_invitation(InvitationRef(invitation.id, a.id), invitee(ana))

    assert raised.value.problem_reason == "not_found"
    assert memberships(ana) == []
    assert status_of(invitation) == InvitationStatus.PENDING


# --- RN-TEN-07 and RN-TEN-18: already a member, suspended ---------------------------------------


def test_RN_TEN_07_already_member_keeps_pending() -> None:
    org = new_org("A")
    ana = new_user("ana")
    add_member(org, ana, Role.ADMIN)
    invitation, token = issue(org, "ana@hub.test")

    with pytest.raises(AlreadyMember):
        accept_by_token(token, invitee(ana))

    assert status_of(invitation) == InvitationStatus.PENDING
    assert [r[1] for r in memberships(ana)] == ["admin"]


def test_RN_TEN_18_suspended_organization_refuses_and_keeps_pending() -> None:
    org = new_org("A")
    invitation, token = issue(org, "ana@hub.test")
    Organization.objects.unscoped(PLATFORM).filter(pk=org.pk).update(
        status=OrgStatus.SUSPENDED.value
    )
    ana = new_user("ana")

    with pytest.raises(OrganizationSuspended):
        accept_by_token(token, invitee(ana))

    assert memberships(ana) == []
    assert status_of(invitation) == InvitationStatus.PENDING


# --- RNF-TEN-03: the token is looked up by its hash only ----------------------------------------


def test_RNF_TEN_03_find_by_token_reads_by_hash() -> None:
    org = new_org("A")
    invitation, token = issue(org)
    assert find_by_token(token) == InvitationRef(invitation.id, org.id)
    assert find_by_token(token + "x") is None


@pytest.mark.parametrize(
    "value", ["", "ABC", "a" * 63, "A" * 64, "g" * 64, 123], ids=lambda v: f"{v!r}"[:12]
)
def test_RNF_TEN_03_by_token_hash_takes_a_hash_only(value: object) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        Invitation.objects.by_token_hash(value)  # type: ignore[arg-type]


def test_AC_TEN_10_by_token_hash_is_read_only() -> None:
    org = new_org("A")
    invitation, token = issue(org)
    rows = Invitation.objects.by_token_hash(hash_token(token))
    assert list(rows.values_list("id", flat=True)) == [invitation.id]
    with pytest.raises(TenantScopeError):
        rows.update(status=InvitationStatus.REVOKED.value)
    with pytest.raises(TenantScopeError):
        rows.delete()
    assert status_of(invitation) == InvitationStatus.PENDING
