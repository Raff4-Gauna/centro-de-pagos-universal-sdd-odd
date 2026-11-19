"""The ``tenancy_invitation`` table (design.md §5): RN-TEN-12, RNF-TEN-03, RNF-TEN-05, RNF-TEN-06.

Like ``test_membership.py``: rows go in through ``for_tenant(ctx).create``, which checks no business
rule, so what stops a bad row is PostgreSQL (ADR-0002 §2).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError

from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus, SystemActor, SystemReason, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.querysets import HardDeleteForbidden, TenantScopeError, UnscopedReason
from apps.identity.models import User
from apps.tenancy.domain.invitations import (
    InvitationPurpose,
    InvitationStatus,
    RevokedReason,
    expires_at_for,
    hash_token,
    new_token,
)
from apps.tenancy.models import Invitation, Membership, Organization

PLATFORM = UnscopedReason.PLATFORM_COMMAND
TABLE = "tenancy_invitation"
FAR = datetime(2100, 1, 1, tzinfo=UTC)


def new_org(name: str) -> TenantContext:
    organization = Organization.objects.unscoped(PLATFORM).create(
        name=name, created_by_operator="operator@hub.test"
    )
    return TenantContext(
        organization_id=organization.id,
        organization_status=OrgStatus.ACTIVE,
        actor=SystemActor(SystemReason.PLATFORM_COMMAND),
    )


def new_user(name: str) -> User:
    return User.objects.create_user(google_sub=f"sub-{name}", email=f"{name}@hub.test")


def invite(ctx: TenantContext, inviter: User | None, **values: Any) -> Invitation:
    defaults: dict[str, Any] = {
        "email": "x@dominio.com",
        "role": Role.OPERATOR,
        "token_hash": hash_token(new_token()),
        "expires_at": FAR,
    }
    if inviter is None:
        defaults["invited_by_operator"] = "operator@hub.test"
    else:
        defaults["invited_by_user"] = inviter
    with tenant_scope(ctx):
        return Invitation.objects.for_tenant(ctx).create(**{**defaults, **values})


def assert_rejected(
    constraint: str, ctx: TenantContext, inviter: User | None, **values: Any
) -> None:
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        invite(ctx, inviter, **values)


@pytest.fixture
def org() -> TenantContext:
    return new_org("A")


@pytest.fixture
def ana() -> User:
    return new_user("ana")


# --- RN-TEN-12: one pending per (organization, email) ---------------------------------------------


@pytest.mark.django_db
def test_one_pending_per_org_and_email(org: TenantContext, ana: User) -> None:
    invite(org, ana)

    assert_rejected("invitation_one_pending_per_org_email", org, ana)

    with tenant_scope(org):
        assert Invitation.objects.for_tenant(org).count() == 1


@pytest.mark.django_db
def test_one_pending_allows_history_and_other_orgs(org: TenantContext, ana: User) -> None:
    invite(org, ana, status=InvitationStatus.REVOKED, revoked_reason=RevokedReason.RESENT)
    invite(org, ana, status=InvitationStatus.EXPIRED)
    invite(org, ana)
    invite(new_org("B"), ana)

    assert Invitation.objects.unscoped(PLATFORM).count() == 4


# --- RNF-TEN-03: only the token hash is stored ----------------------------------------------------


@pytest.mark.django_db
def test_RNF_TEN_03_only_hash_is_stored(org: TenantContext, ana: User) -> None:
    token = new_token()
    invitation = invite(org, ana, token_hash=hash_token(token))

    with connection.cursor() as cursor:
        cursor.execute(f"SELECT * FROM {TABLE} WHERE id = %s", [invitation.pk])  # noqa: S608
        row = cursor.fetchone()

    assert hash_token(token) in row
    assert not any(isinstance(value, str) and token in value for value in row)
    assert token not in str(invitation)
    assert not any(field.name == "token" for field in Invitation._meta.get_fields())


@pytest.mark.django_db
@pytest.mark.parametrize(
    "token_hash",
    [
        pytest.param("raw-token-instead-of-its-hash", id="raw"),
        pytest.param("A" * 64, id="uppercase"),
        pytest.param("a" * 63, id="short"),
    ],
)
def test_RNF_TEN_03_token_hash_is_a_sha256_hex(
    org: TenantContext, ana: User, token_hash: str
) -> None:
    assert_rejected("invitation_token_hash_sha256", org, ana, token_hash=token_hash)


@pytest.mark.django_db
def test_RNF_TEN_03_token_hash_is_unique_across_orgs(org: TenantContext, ana: User) -> None:
    token_hash = hash_token(new_token())
    invite(org, ana, token_hash=token_hash)

    assert_rejected("token_hash", new_org("B"), ana, token_hash=token_hash, email="y@d.com")


# --- AC-TEN-35 / RNF-TEN-06: the stored email is the normalized one -------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("email", [" x@dominio.com", "X@Dominio.com", "x@dominio.com "])
def test_AC_TEN_35_stored_email_is_normalized(org: TenantContext, ana: User, email: str) -> None:
    assert_rejected("invitation_email_normalized", org, ana, email=email)


def test_RNF_TEN_06_only_the_email_of_the_invitee_is_kept() -> None:
    names = {field.name for field in Invitation._meta.concrete_fields}

    assert "email" in names
    assert not names & {"name", "first_name", "last_name", "full_name", "phone", "picture"}


# --- Enums and coherence (design.md §5) -----------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"status": "used"}, "invitation_status_valid"),
        ({"role": "superuser"}, "invitation_role_valid"),
        ({"purpose": "vip"}, "invitation_purpose_valid"),
        ({"status": InvitationStatus.REVOKED, "revoked_reason": "x"}, "invitation_revoked_reason"),
    ],
)
def test_RNF_TEN_05_closed_enums(
    org: TenantContext, ana: User, values: dict[str, Any], constraint: str
) -> None:
    assert_rejected(constraint, org, ana, **values)


@pytest.mark.django_db
def test_RNF_TEN_05_inviter_is_a_user_xor_the_operator(org: TenantContext, ana: User) -> None:
    assert_rejected("invitation_inviter_xor", org, ana, invited_by_operator="operator@hub.test")
    assert_rejected("invitation_inviter_xor", org, None, invited_by_operator="")

    assert invite(org, None, purpose=InvitationPurpose.FIRST_OWNER).invited_by_user is None


@pytest.mark.django_db
@pytest.mark.parametrize("purpose", [InvitationPurpose.SUPPORT, InvitationPurpose.OWNER_RECOVERY])
def test_RNF_TEN_05_operator_purposes_need_a_reason(
    org: TenantContext, purpose: InvitationPurpose
) -> None:
    assert_rejected("invitation_operator_reason", org, None, purpose=purpose)

    assert invite(org, None, purpose=purpose, reason="ticket 42").reason == "ticket 42"


@pytest.mark.django_db
def test_RNF_TEN_05_accepted_is_coherent(org: TenantContext, ana: User) -> None:
    at = datetime(2026, 11, 19, tzinfo=UTC)
    assert_rejected("invitation_accepted_coherent", org, ana, status=InvitationStatus.ACCEPTED)
    assert_rejected("invitation_accepted_coherent", org, ana, accepted_by=ana, accepted_at=at)

    accepted = invite(org, ana, status=InvitationStatus.ACCEPTED, accepted_by=ana, accepted_at=at)
    assert accepted.accepted_by == ana


@pytest.mark.django_db
def test_RNF_TEN_05_expiry_is_after_creation(org: TenantContext, ana: User) -> None:
    assert_rejected("invitation_expiry_after_creation", org, ana, expires_at=datetime.now(UTC))

    issued = datetime.now(UTC)
    assert invite(org, ana, expires_at=expires_at_for(issued)).expires_at > issued


@pytest.mark.django_db
def test_RNF_TEN_05_a_new_invitation_is_pending_and_standard(org: TenantContext, ana: User) -> None:
    invitation = invite(org, ana)

    assert invitation.status == InvitationStatus.PENDING
    assert invitation.purpose == InvitationPurpose.STANDARD
    assert invitation.revoked_reason is None


# --- Isolation and history ------------------------------------------------------------------------


@pytest.mark.django_db
def test_invitation_fails_closed_and_is_never_deleted(org: TenantContext, ana: User) -> None:
    invitation = invite(org, ana)

    with pytest.raises(TenantScopeError):
        Invitation.objects.filter(email="x@dominio.com").exists()
    with tenant_scope(org):
        with pytest.raises(HardDeleteForbidden):
            invitation.delete()
        with pytest.raises(HardDeleteForbidden):
            Invitation.objects.for_tenant(org).delete()
    with pytest.raises(ProtectedError):
        ana.delete()


@pytest.mark.django_db
def test_resend_chain_points_to_the_replaced_one(org: TenantContext, ana: User) -> None:
    old = invite(org, ana, status=InvitationStatus.REVOKED, revoked_reason=RevokedReason.RESENT)
    new = invite(org, ana, replaces=old, expires_at=FAR + timedelta(days=1))

    assert new.replaces == old


# --- Membership.source_invitation: one membership per invitation (RN-TEN-12) ----------------------


@pytest.mark.django_db
def test_source_invitation_is_unique(org: TenantContext, ana: User) -> None:
    invitation = invite(org, ana)
    with tenant_scope(org):
        Membership.objects.for_tenant(org).create(
            user=ana, role=Role.OPERATOR, source_invitation=invitation
        )
        with pytest.raises(IntegrityError, match="source_invitation"), transaction.atomic():
            Membership.objects.for_tenant(org).create(
                user=new_user("bea"), role=Role.OPERATOR, source_invitation=invitation
            )


# --- Schema (RNF-TEN-05) --------------------------------------------------------------------------


def table_constraints() -> dict[str, dict[str, Any]]:
    with connection.cursor() as cursor:
        return connection.introspection.get_constraints(cursor, TABLE)


@pytest.mark.django_db
def test_RNF_TEN_05_constraints_are_the_ones_of_the_design() -> None:
    constraints = table_constraints()

    assert {
        "invitation_one_pending_per_org_email",
        "invitation_email_normalized",
        "invitation_status_valid",
        "invitation_role_valid",
        "invitation_purpose_valid",
        "invitation_inviter_xor",
        "invitation_operator_reason",
        "invitation_accepted_coherent",
        "invitation_expiry_after_creation",
        "invitation_org_status_created",
        "invitation_pending_email",
    } <= set(constraints)
    assert constraints["invitation_one_pending_per_org_email"]["columns"] == [
        "organization_id",
        "email",
    ]


@pytest.mark.django_db
def test_RNF_TEN_05_pending_email_index_is_partial() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexdef FROM pg_indexes WHERE tablename = %s AND indexname = %s",
            [TABLE, "invitation_pending_email"],
        )
        (definition,) = cursor.fetchone()

    assert "(email)" in definition
    assert "WHERE ((status)::text = 'pending'::text)" in definition
