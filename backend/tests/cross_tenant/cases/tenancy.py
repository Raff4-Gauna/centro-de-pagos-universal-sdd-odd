"""SPEC-02's routes (``apps/tenancy/api/``).

Every ``TenantViewSet`` route of the module registers one ``CrossTenantCase`` per method here, in
the PR that adds it (DoD, ``tasks.md``). A route that runs without an active organization
(``GET /api/organizations/``, ``POST /api/invitations/accept/``, design.md §3.5) goes to ``EXEMPT``
with its reason; a ``GET`` behind the login also gives ``read``, the URL the suite reads as A's
member to check it is scoped to the person. Until a route exists, its entry would be stale: the
walker fails on both. The first one is ``GET /api/organizations/`` (T-TEN-12).

``/api/organizations/current/`` (T-TEN-13) names no object: the organization is the header's.
``SEEDS`` adds the organization's own editable row, so the suite sees an edit that lands on B, or
on A while it is suspended.

``/api/branches/`` (T-TEN-24): two branches in each organization, one of them inactive, so a
listing that leaks B's rows, active or not, carries B's ids. A ``POST`` names the organization it
is built for in the name of the new branch; it can only land in the active one. Built for B (the
suite's second organization, ``harness.build_world``), it also carries B's ``organization_id``
(AC-TEN-07): the strict body refuses it, and nothing lands in B. Built for A it does not, so the
creation in A answers ``2xx``.

``/api/branches/{id}/`` and its ``deactivate``/``reactivate`` (T-TEN-25) name B's branches by id
with A active (``404``, AC-TEN-01). Each one targets the branch it can change: the active one to
see, edit or deactivate, the inactive one to reactivate (its name is free).

``/api/invitations/mine/`` and ``/api/invitations/{id}/accept/`` (T-TEN-16, Q-124) are exempt:
the person has no membership in the invitation's organization yet. Each organization gets a
``pending`` invitation for somebody else's email, so "my invitations" that leaks B's carries B's
invitation id. Accepting by id is a ``POST``, so it gives no ``read``; its isolation is in
``tests/tenancy/api/test_my_invitations_api.py`` (another email answers like a missing id).

``/api/memberships/`` and ``/api/memberships/{id}/`` (T-TEN-22): each organization gets an
``admin`` colleague besides its owner, so a listing that leaks B's members carries B's membership
ids, and a ``PATCH`` names B's colleague by id with A active (``404``, AC-TEN-02). The rows are
every membership with its role and status: a role changed in B, or in A while it is suspended,
shows up.

``DELETE /api/memberships/{id}/`` and ``POST /api/memberships/me/leave/`` (T-TEN-23): the
``DELETE`` names B's colleague by id with A active (``404``) and revokes A's colleague on the last
step. Each organization also gets a second owner, so A's member is not the last one and may leave.
Leaving names no object: on the step that builds B's URL the request still goes to A, so A's member
leaves A there (B's rows must stay as they are). Its ``restore`` gives back, before every request,
the membership of whoever left A, so the last step has one to leave; the URL itself has no side
effects. Both reduce access: with A suspended the suite expects them to go through (Q-221).

``/api/invitations/`` (T-TEN-20): the ``pending`` invitation of each organization's ``Seed`` is what
a listing that leaks B's carries (B's invitation id). A ``POST`` invites a new email named after the
organization it is built for; built for B it also carries B's ``organization_id``: the strict body
refuses it and nothing lands in B. Built for A it creates the invitation in A (``201``).

``/api/invitations/{id}/resend/`` and ``revoke/`` (T-TEN-21) name that ``pending`` invitation by id:
B's with A active is ``404`` (AC-TEN-02), and a resend or revoke that lands in B changes the status
of B's row (or adds one). A resend with A suspended is ``409``; a revoke reduces access, so the
suite expects it to go through there (Q-221).
"""

from __future__ import annotations

from typing import Any

from apps.common.authz.roles import Role
from apps.common.tenancy.current import tenant_scope
from apps.tenancy.models import Branch, Invitation, Membership, Organization
from apps.tenancy.models.membership import EndedReason, MembershipStatus
from tests.cross_tenant.registry import CrossTenantCase, Exemption, Seed
from tests.tenancy.api.probe import PLATFORM, add_member, new_user, platform_ctx
from tests.tenancy.invitation_setup import issue

_MINE = (
    "ruta de alcance de usuario: las organizaciones de la persona, exenta de la organización activa"
    " (design.md §3.5)"
)
_ACCEPT = (
    "aceptar una invitación con su token: la persona todavía no es miembro; la organización es la "
    "de la invitación, no la del header (design.md §3.5, §4.4)"
)
_MY_INVITATIONS = (
    "ruta de alcance de usuario: las invitaciones pendientes del email de la persona, que todavía "
    "no es miembro de esas organizaciones (design.md §3.5, Q-124)"
)
_ACCEPT_MINE = (
    "aceptar desde la sesión una invitación del propio email: la persona todavía no es miembro; la "
    "organización es la de la invitación, no la del header (design.md §3.5, §4.4, Q-124)"
)
CURRENT = "api/organizations/current/"
_FIELDS = ("id", "name", "legal_name", "tax_id", "timezone", "status")
BRANCHES = "api/branches/"
BRANCH = "api/branches/(?P<id>[^/.]+)/"
# harness.build_world: the organization whose rows the suite must never see changed.
OTHER_ORGANIZATION = "B"
MEMBERSHIPS = "api/memberships/"
MEMBERSHIP = "api/memberships/(?P<id>[^/.]+)/"
LEAVE = "api/memberships/me/leave/"
INVITATIONS = "api/invitations/"


def _current(organization: Organization) -> str:
    return f"/{CURRENT}"


def _renamed(organization: Organization) -> dict[str, str]:
    return {"name": f"renamed-in-{organization.name}", "legal_name": "Razón social nueva"}


def _no_rows(organization: Organization) -> None:
    """The organization row already exists: the suite created it."""


def _organization_row(organization: Organization) -> frozenset[tuple[Any, ...]]:
    rows = Organization.objects.unscoped(PLATFORM).filter(pk=organization.pk)
    return frozenset(rows.values_list(*_FIELDS))


def _create_branches(organization: Organization) -> None:
    ctx = platform_ctx(organization)
    with tenant_scope(ctx):
        branches = Branch.objects.for_tenant(ctx)
        branches.create(name=f"{organization.name}-centro", code=f"{organization.name}-C01")
        branches.create(name=f"{organization.name}-norte", is_active=False)


def _branch_rows(organization: Organization) -> frozenset[tuple[Any, ...]]:
    ctx = platform_ctx(organization)
    with tenant_scope(ctx):
        rows = Branch.objects.for_tenant(ctx).values_list("id", "name", "code", "is_active")
        return frozenset(rows)


def _invite_a_guest(organization: Organization) -> None:
    issue(organization, f"guest-of-{organization.name.lower()}@hub.test")


def _invitation_rows(organization: Organization) -> frozenset[tuple[Any, ...]]:
    rows = Invitation.objects.unscoped(PLATFORM).filter(organization=organization)
    return frozenset(rows.values_list("id", "email", "role", "status"))


def _branches(organization: Organization) -> str:
    return f"/{BRANCHES}"


def _new_branch(organization: Organization) -> dict[str, str]:
    body = {"name": f"nueva-en-{organization.name}"}
    if organization.name == OTHER_ORGANIZATION:
        body["organization_id"] = str(organization.id)
    return body


def _branch_url(organization: Organization, *, active: bool, action: str = "") -> str:
    ctx = platform_ctx(organization)
    with tenant_scope(ctx):
        branch = Branch.objects.for_tenant(ctx).filter(is_active=active).get()
    return f"/{BRANCHES}{branch.pk}/{action}"


def _active_branch(organization: Organization) -> str:
    return _branch_url(organization, active=True)


def _to_deactivate(organization: Organization) -> str:
    return _branch_url(organization, active=True, action="deactivate/")


def _to_reactivate(organization: Organization) -> str:
    return _branch_url(organization, active=False, action="reactivate/")


def _renamed_branch(organization: Organization) -> dict[str, str]:
    return {"name": f"renombrada-en-{organization.name}", "address": "Calle 1"}


def _colleague_name(organization: Organization) -> str:
    return f"colleague-{organization.name.lower()}"


def _add_colleagues(organization: Organization) -> None:
    add_member(organization, new_user(_colleague_name(organization)), Role.ADMIN)
    add_member(organization, new_user(f"co-owner-{organization.name.lower()}"), Role.OWNER)


def _membership_rows(organization: Organization) -> frozenset[tuple[Any, ...]]:
    rows = Membership.objects.unscoped(PLATFORM).filter(organization=organization)
    return frozenset(rows.values_list("id", "user_id", "role", "status"))


def _memberships(organization: Organization) -> str:
    return f"/{MEMBERSHIPS}"


def _colleague(organization: Organization) -> str:
    email = f"{_colleague_name(organization)}@hub.test"
    rows = Membership.objects.unscoped(PLATFORM).filter(organization=organization)
    return f"/{MEMBERSHIPS}{rows.get(user__email=email).pk}/"


def _demoted(organization: Organization) -> dict[str, str]:
    return {"role": Role.VIEWER.value}


def _leave(organization: Organization) -> str:
    return f"/{LEAVE}"


def _rejoin(organization: Organization) -> None:
    """Whoever left ``organization`` and has no membership there gets a new one, as re-invited."""
    rows = Membership.objects.unscoped(PLATFORM).filter(organization=organization)
    active = set(rows.filter(status=MembershipStatus.ACTIVE.value).values_list("user", flat=True))
    left = rows.filter(ended_reason=EndedReason.LEFT.value).select_related("user")
    for gone in left:
        if gone.user_id not in active:
            add_member(organization, gone.user, Role(gone.role))
            active.add(gone.user_id)


def _invitations(organization: Organization) -> str:
    return f"/{INVITATIONS}"


def _guest_invitation(organization: Organization, action: str) -> str:
    email = f"guest-of-{organization.name.lower()}@hub.test"
    rows = Invitation.objects.unscoped(PLATFORM).filter(organization=organization, email=email)
    return f"/{INVITATIONS}{rows.get(status='pending').pk}/{action}/"


def _to_resend(organization: Organization) -> str:
    return _guest_invitation(organization, "resend")


def _to_revoke(organization: Organization) -> str:
    return _guest_invitation(organization, "revoke")


def _new_invitation(organization: Organization) -> dict[str, str]:
    body = {"email": f"invitee-of-{organization.name.lower()}@hub.test", "role": "viewer"}
    if organization.name == OTHER_ORGANIZATION:
        body["organization_id"] = str(organization.id)
    return body


CASES: tuple[CrossTenantCase, ...] = (
    CrossTenantCase(CURRENT, "GET", _current),
    CrossTenantCase(CURRENT, "PATCH", _current, body=_renamed),
    CrossTenantCase(BRANCHES, "GET", _branches),
    CrossTenantCase(BRANCHES, "POST", _branches, body=_new_branch),
    CrossTenantCase(BRANCH, "GET", _active_branch),
    CrossTenantCase(BRANCH, "PATCH", _active_branch, body=_renamed_branch),
    CrossTenantCase("api/branches/<str:id>/deactivate/", "POST", _to_deactivate),
    CrossTenantCase("api/branches/<str:id>/reactivate/", "POST", _to_reactivate),
    CrossTenantCase(MEMBERSHIPS, "GET", _memberships),
    CrossTenantCase(MEMBERSHIP, "PATCH", _colleague, body=_demoted),
    CrossTenantCase(MEMBERSHIP, "DELETE", _colleague),
    CrossTenantCase(LEAVE, "POST", _leave, restore=_rejoin),
    CrossTenantCase(INVITATIONS, "GET", _invitations),
    CrossTenantCase(INVITATIONS, "POST", _invitations, body=_new_invitation),
    CrossTenantCase("api/invitations/<str:id>/resend/", "POST", _to_resend),
    CrossTenantCase("api/invitations/<str:id>/revoke/", "POST", _to_revoke),
)
EXEMPT: tuple[Exemption, ...] = (
    Exemption("api/organizations/", _MINE, read=lambda organization: "/api/organizations/"),
    Exemption("api/invitations/accept/", _ACCEPT),
    Exemption("api/invitations/mine/", _MY_INVITATIONS, read=lambda _: "/api/invitations/mine/"),
    Exemption("api/invitations/<uuid:invitation_id>/accept/", _ACCEPT_MINE),
)
SEEDS: tuple[Seed, ...] = (
    Seed(create=_no_rows, rows=_organization_row),
    Seed(create=_create_branches, rows=_branch_rows),
    Seed(create=_invite_a_guest, rows=_invitation_rows),
    Seed(create=_add_colleagues, rows=_membership_rows),
)
