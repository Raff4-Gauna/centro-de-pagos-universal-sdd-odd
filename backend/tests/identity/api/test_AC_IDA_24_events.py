"""Every audit event of RN-IDA-17, and no event for a ``429`` (AC-IDA-24, Q-111, Q-117).

One run walks the whole catalog of ``domain/audit_events.py`` through the code that emits each
event: the callback over the BFF route (with the fake Google of ``login_flow.py``) and the services
of refresh, logout, "Seguridad" and the operator's commands. Then each event is checked for what
AC-IDA-24 asks: actor, result, reason, UTC date and organization (null but for the invitations).

``organization.created`` + ``invitation.created`` of the bootstrap belong to SPEC-02's catalog
(``tenancy_create_org``, design.md §6.5) and are tested there.
"""

from __future__ import annotations

import json
from datetime import UTC, timedelta

import pytest
from django.utils import timezone

from apps.identity.domain.audit_events import (
    AuditActorType,
    AuditResult,
    IdentityAuditAction,
    LoginRejectionReason,
    SessionRevocationReason,
)
from apps.identity.models import LoginAttempt, RevokeReason, User
from apps.identity.ports.audit import AuditEvent
from apps.identity.services.logout import logout
from apps.identity.services.refresh import RefreshRejectedError, refresh_session
from apps.identity.services.session_lifecycle import open_session
from apps.identity.services.sessions import revoke_other_sessions, revoke_own_session
from apps.identity.services.user_status import (
    PlatformOperator,
    UserTarget,
    deactivate_user,
    reactivate_user,
)
from tests.identity.api.login_flow import CODE, COMPLETE, EMAIL, START, Flow, make_user

pytestmark = pytest.mark.django_db

OPERATOR = PlatformOperator(name="Ops Team", os_user="deploy")
FAILURES = {
    IdentityAuditAction.LOGIN_REJECTED,
    IdentityAuditAction.REFRESH_REUSE_DETECTED,
    IdentityAuditAction.EMAIL_CHANGE_COLLISION,
}


def login_events(flow: Flow) -> list[AuditEvent]:
    """The callback's side of the catalog: success, the five rejections, invitations, email."""
    ana = make_user()
    make_user(sub="300000000000000000001", email="inactive@example.com", active=False)
    now = timezone.now()
    invitations = [flow.ports.invitations.invite("new@example.com", now=now) for _ in range(2)]

    assert flow.login().status_code == 200  # login_succeeded
    state, nonce = flow.begin()
    flow.google.next_id_token = flow.google.id_token(nonce=nonce)
    assert flow.finish(state).status_code == 200  # a second success
    assert flow.finish(state).status_code == 400  # google_auth_failed: the attempt is gone
    flow.login(sub="300000000000000000002", email="other@example.com", email_verified=False)
    flow.login(sub="300000000000000000003", email="nobody@example.com")  # not_invited
    flow.login(sub="300000000000000000001", email="inactive@example.com")  # user_inactive
    flow.login(sub="300000000000000000004", email=EMAIL)  # identity_conflict
    assert flow.login(sub="300000000000000000005", email="new@example.com").status_code == 200
    flow.login(email="ana.nueva@example.com")  # Ana's sub: email_changed
    flow.login(email="new@example.com")  # Ana's sub, someone else's email: the collision
    events = list(flow.ports.audit.events)

    invited = [e for e in events if e.action == IdentityAuditAction.USER_CREATED_BY_INVITATION]
    assert sorted(str(e.organization_id) for e in invited) == sorted(
        str(item.organization_id) for item in invitations
    )
    new_user = User.objects.get(google_sub="300000000000000000005")
    assert {e.actor_id for e in invited} == {new_user.pk}
    [inactive] = [e for e in events if e.reason == LoginRejectionReason.USER_INACTIVE]
    assert inactive.actor_type == AuditActorType.USER  # the error names the user
    assert ana.pk in {e.actor_id for e in events if e.action == IdentityAuditAction.EMAIL_CHANGED}
    return events


def session_events(flow: Flow) -> list[AuditEvent]:
    """Refresh reuse, logout, superseded, "Seguridad" and the operator's commands."""
    flow.ports.audit.events.clear()
    now = timezone.now()
    beto = make_user(sub="300000000000000000006", email="beto@example.com")
    opened = [open_session(beto, now=now) for _ in range(6)]

    rotated = refresh_session(opened[0].refresh_token, now=now)
    assert rotated.refresh_token is not None
    with pytest.raises(RefreshRejectedError):  # the used token, past the grace window
        refresh_session(opened[0].refresh_token, now=now + timedelta(minutes=1))
    assert logout(refresh_token=opened[1].refresh_token, now=now)
    assert logout(refresh_token=opened[2].refresh_token, reason=RevokeReason.SUPERSEDED, now=now)
    revoke_own_session(user_id=beto.pk, session_id=opened[3].session.pk, now=now)
    assert revoke_other_sessions(user_id=beto.pk, current_session_id=opened[4].session.pk, now=now)
    target = UserTarget(user_id=beto.pk)
    open_session(beto, now=now)
    deactivate_user(target=target, operator=OPERATOR, note=None, now=now)
    reactivate_user(target=target, operator=OPERATOR, note="back", now=now)
    return list(flow.ports.audit.events)


def test_AC_IDA_24_every_event_is_emitted(flow: Flow) -> None:
    events = login_events(flow) + session_events(flow)

    assert {event.action for event in events} == set(IdentityAuditAction)
    reasons = {(e.action, e.reason) for e in events}
    assert {r for a, r in reasons if a == IdentityAuditAction.LOGIN_REJECTED} == set(
        LoginRejectionReason
    )
    assert {r for a, r in reasons if a == IdentityAuditAction.SESSION_REVOKED} == set(
        SessionRevocationReason
    )
    for event in events:
        assert event.occurred_at.tzinfo is not None
        assert event.occurred_at.utcoffset() == timedelta(0)
        assert event.occurred_at.astimezone(UTC) == event.occurred_at
        expected = AuditResult.FAILURE if event.action in FAILURES else AuditResult.SUCCESS
        assert event.result == expected
        if event.action != IdentityAuditAction.USER_CREATED_BY_INVITATION:
            assert event.organization_id is None  # global events (Q-117)
        if event.actor_type == AuditActorType.USER:
            assert event.actor_id is not None
        elif event.actor_type == AuditActorType.PLATFORM_OPERATOR:
            assert (event.metadata["operator"], event.metadata["os_user"]) == ("Ops Team", "deploy")
        else:
            assert event.actor_id is None  # anonymous or system: nobody to name
        if event.action == IdentityAuditAction.LOGIN_REJECTED:
            text = repr(event)
            assert "@example.com" not in text  # Q-125: no email nor sub of the rejected
            assert "300000000000000000" not in text


def test_AC_IDA_24_429_is_not_audited(flow: Flow, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    body: dict[str, object] = {"login_binding": "b" * 43, "state": "s" * 43, "code": "c"}
    for path in (START, COMPLETE):
        answers = [flow.post(path, body).status_code for _ in range(10)]
        assert 429 not in answers
        audited, asked_google = len(flow.ports.audit.events), len(flow.gateway_calls)

        assert flow.post(path, body).status_code == 429

        # No event, and Google never asked (the throttle runs before the view).
        assert (len(flow.ports.audit.events), len(flow.gateway_calls)) == (audited, asked_google)

    # The metric of 429 per endpoint is the access log's route and status (RNF-IDA-04).
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    limited = [
        line["route"]
        for line in lines
        if line.get("message") == "http.request" and line.get("status") == 429
    ]
    assert limited == ["api/auth/bff/login/start/", "api/auth/bff/login/complete/"]


@pytest.mark.parametrize("binding", ["absent", None, ""])
def test_AC_IDA_24_callback_without_binding_is_audited(flow: Flow, binding: object) -> None:
    # Q-128 (owner, 2026-11-16): the BFF relays a callback without __Host-cpu_login, or with an
    # ambiguous one, and Django rejects it as step 2 of design.md §4.2: google_auth_failed, audited.
    state, _ = flow.begin()
    body: dict[str, object] = {"state": state, "code": CODE}
    if binding != "absent":
        body["login_binding"] = binding

    response = flow.post(COMPLETE, body)

    assert (response.status_code, response.json()["code"]) == (400, "google_auth_failed")
    assert state not in response.content.decode()
    assert CODE not in response.content.decode()
    [event] = flow.ports.audit.events
    assert (event.action, event.reason, event.actor_type, event.actor_id) == (
        IdentityAuditAction.LOGIN_REJECTED,
        LoginRejectionReason.GOOGLE_AUTH_FAILED,
        AuditActorType.ANONYMOUS,
        None,
    )
    assert flow.gateway_calls == []  # Google is never asked
    assert LoginAttempt.objects.count() == 1  # nobody else's attempt is spent by its state


def test_AC_IDA_24_flood_without_binding_meets_the_throttle(flow: Flow) -> None:
    body: dict[str, object] = {"state": "s" * 43, "code": CODE}
    answers = [flow.post(COMPLETE, body).status_code for _ in range(11)]

    assert answers == [400] * 10 + [429]
    assert len(flow.ports.audit.events) == 10  # the 429 is not audited (Q-111)
