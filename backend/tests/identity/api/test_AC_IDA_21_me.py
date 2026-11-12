"""``GET /api/me/`` (RF-IDA-06, RN-IDA-18, RN-IDA-22; AC-IDA-21, AC-IDA-22, AC-IDA-30 API).

The first authenticated route of the public URLconf, end to end: the Hub's Bearer, the session
behind it and the person it names, nothing else. The memberships are whatever the selector of
SPEC-02 returns (``EmptyMembershipSelector`` until ``T-TEN-12``); the isolation between
organizations is that selector's test, in SPEC-02.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
import yaml
from django.test import Client
from django.utils import timezone
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity.domain.errors import IdentityErrorCode
from apps.identity.models import User
from apps.identity.ports.memberships import MembershipSummary
from apps.identity.services.session_lifecycle import open_session
from apps.identity.tokens.access_token import issue_access_token
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT

pytestmark = pytest.mark.django_db

ME = "/api/me/"
CHALLENGE = 'Bearer realm="hub"'
ORGANIZATION = UUID("6d1f3c8e-0000-4000-8000-000000000001")


class _OneMembershipSelector:
    """Stands in for SPEC-02's selector: one membership, for the user it is asked about only."""

    asked: ClassVar[list[UUID]] = []

    def list_active_memberships(self, user_id: UUID) -> list[MembershipSummary]:
        self.asked.append(user_id)
        return [MembershipSummary(ORGANIZATION, "Ferretería Sur", "owner")]


def make_user(sub: str, email: str, **profile: str) -> User:
    return User.objects.create_user(google_sub=sub, email=email, **profile)


def bearer_of(user: User) -> dict[str, str]:
    session = open_session(user, now=timezone.now()).session
    token = issue_access_token(user_id=user.pk, session_id=session.pk)
    return {"Authorization": f"Bearer {token}"}


def assert_401(response: Any, code: IdentityErrorCode) -> None:
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == CHALLENGE
    assert response["Content-Type"] == "application/problem+json"
    assert json.loads(response.content)["code"] == code.value


@pytest.fixture
def ana() -> User:
    return make_user(
        "sub-ana",
        "ana@example.com",
        display_name="Ana Pérez",
        avatar_url="https://lh3.googleusercontent.com/a/ana",
    )


@pytest.fixture
def beto() -> User:
    return make_user("sub-beto", "beto@example.com", display_name="Beto")


def test_AC_IDA_21_returns_only_own_data(client: Client, ana: User, beto: User) -> None:
    headers = bearer_of(ana)
    # No user identifier is taken (RN-IDA-18): asking for another person still answers your own.
    for url in (ME, f"{ME}?user_id={beto.pk}", f"{ME}?id={beto.pk}&email={beto.email}"):
        response = client.get(url, headers=headers)
        assert response.status_code == 200, url
        assert response.json() == {
            "id": str(ana.pk),
            "email": "ana@example.com",
            "display_name": "Ana Pérez",
            "avatar_url": "https://lh3.googleusercontent.com/a/ana",
            "memberships": [],
        }
    assert client.get(ME, headers=bearer_of(beto)).json()["id"] == str(beto.pk)


def test_AC_IDA_21_personal_data_is_not_cached(client: Client, ana: User) -> None:
    assert client.get(ME, headers=bearer_of(ana))["Cache-Control"] == "no-store"


def test_AC_IDA_21_no_avatar_is_null(client: Client, beto: User) -> None:
    assert client.get(ME, headers=bearer_of(beto)).json()["avatar_url"] is None


def test_AC_IDA_21_memberships_as_the_selector_returns_them(
    client: Client, settings: SettingsWrapper, ana: User
) -> None:
    settings.IDENTITY_MEMBERSHIP_SELECTOR = f"{__name__}._OneMembershipSelector"
    _OneMembershipSelector.asked = []
    response = client.get(ME, headers=bearer_of(ana))
    assert response.status_code == 200
    assert response.json()["memberships"] == [
        {
            "organization_id": str(ORGANIZATION),
            "organization_name": "Ferretería Sur",
            "role": "owner",
        }
    ]
    assert _OneMembershipSelector.asked == [ana.pk]


def test_AC_IDA_21_anonymous_is_401_unauthenticated(client: Client) -> None:
    assert_401(client.get(ME), IdentityErrorCode.UNAUTHENTICATED)


def test_AC_IDA_21_unknown_token_is_401(client: Client) -> None:
    token = issue_access_token(user_id=uuid4(), session_id=uuid4())
    response = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert_401(response, IdentityErrorCode.SESSION_REVOKED)


@pytest.mark.parametrize(
    ("headers", "code"),
    [
        ({"Authorization": "Api-Key erp-key-1234"}, IdentityErrorCode.UNAUTHENTICATED),
        ({"X-Api-Key": "erp-key-1234"}, IdentityErrorCode.UNAUTHENTICATED),
        ({"Authorization": "Bearer erp-key-1234"}, IdentityErrorCode.TOKEN_INVALID),
    ],
    ids=["api-key-scheme", "api-key-header", "api-key-as-bearer"],
)
def test_AC_IDA_22_api_key_on_me(
    client: Client, headers: dict[str, str], code: IdentityErrorCode
) -> None:
    assert_401(client.get(ME, headers=headers), code)


def test_AC_IDA_30_no_memberships_returns_empty_list(client: Client, ana: User) -> None:
    # Active user, live session, no active membership (RN-IDA-22): 200, never 403.
    response = client.get(ME, headers=bearer_of(ana))
    assert response.status_code == 200
    assert response.json()["memberships"] == []


def test_RF_IDA_06_contract_documents_me_behind_the_bearer() -> None:
    contract = yaml.safe_load(CONTRACT.read_bytes())
    operation = contract["paths"][ME]["get"]
    assert list(contract["paths"][ME]) == ["get"]
    assert "parameters" not in operation  # no user identifier, not even optional (RN-IDA-18)
    assert operation["security"] == [{"HubBearer": []}]
    scheme = contract["components"]["securitySchemes"]["HubBearer"]
    assert scheme == {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    body = operation["responses"]["200"]["content"]["application/json"]["schema"]
    me = contract["components"]["schemas"][body["$ref"].rsplit("/", 1)[1]]
    assert set(me["required"]) == {"id", "email", "display_name", "avatar_url", "memberships"}
    assert me["properties"]["avatar_url"]["nullable"] is True
    membership = contract["components"]["schemas"]["Membership"]
    assert set(membership["required"]) == {"organization_id", "organization_name", "role"}
