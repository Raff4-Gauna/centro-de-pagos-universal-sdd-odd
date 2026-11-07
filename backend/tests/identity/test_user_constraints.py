"""The ``users`` table (design.md §5): RN-IDA-04, RNF-IDA-05 and D-03.

The constraints are checked on PostgreSQL through ``objects.create``, which normalizes nothing:
what stops a bad row there is the database and not ``create_user``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.identity.domain.profile import clamp_display_name, clean_avatar_url
from apps.identity.models import User

DEACTIVATED_AT = datetime(2026, 11, 6, tzinfo=UTC)
TOO_LONG_NAME = "n" * 151
TOO_LONG_URL = "https://example.com/" + "a" * 481


def row(**overrides: Any) -> dict[str, Any]:
    return {"google_sub": "sub-1", "email": "ana@x.com", **overrides}


def assert_rejected(constraint: str, **values: Any) -> None:
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        User.objects.create(**row(**values))


# --- Without database ---------------------------------------------------------------------------


def test_RN_IDA_04_username_field_is_the_google_sub() -> None:
    assert settings.AUTH_USER_MODEL == "identity.User"
    assert get_user_model() is User
    assert User._meta.db_table == "users"
    assert User.USERNAME_FIELD == "google_sub"


def test_D_03_no_django_contrib_app_is_installed() -> None:
    assert not [app for app in settings.INSTALLED_APPS if app.startswith("django.contrib.")]


def test_RNF_IDA_05_manager_has_no_create_superuser() -> None:
    assert not hasattr(User.objects, "create_superuser")


def test_RNF_IDA_05_only_the_declared_columns_exist() -> None:
    assert sorted(field.column for field in User._meta.concrete_fields) == [
        "avatar_url",
        "created_at",
        "deactivated_at",
        "display_name",
        "email",
        "google_sub",
        "id",
        "is_active",
        "last_login_at",
        "password",
    ]


def test_RNF_IDA_05_password_cannot_be_set() -> None:
    with pytest.raises(NotImplementedError):
        User().set_password("hunter2")


def test_RNF_IDA_05_str_shows_neither_sub_nor_email() -> None:
    user = User(**row())
    assert str(user) == str(user.pk)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Ana", "Ana"), ("", ""), (None, ""), ("n" * 150, "n" * 150), (TOO_LONG_NAME, "n" * 150)],
)
def test_RNF_IDA_05_display_name_is_clamped(raw: str | None, expected: str) -> None:
    assert clamp_display_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.com/a.png", "https://example.com/a.png"),
        ("https://example.com/" + "a" * 480, "https://example.com/" + "a" * 480),
        (TOO_LONG_URL, ""),
        ("http://example.com/a.png", ""),
        ("javascript:alert(1)", ""),
        ("https://", ""),
        ("https://[bad", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_RNF_IDA_05_avatar_is_https_and_short(raw: str | None, expected: str) -> None:
    assert clean_avatar_url(raw) == expected


# --- PostgreSQL ---------------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.django_db
def test_RN_IDA_04_google_sub_is_unique() -> None:
    User.objects.create(**row())
    assert_rejected("users_google_sub_key", email="otra@x.com")


@pytest.mark.integration
@pytest.mark.django_db
def test_RN_IDA_04_email_is_unique() -> None:
    User.objects.create(**row())
    assert_rejected("users_email_key", google_sub="sub-2")


@pytest.mark.integration
@pytest.mark.django_db
@pytest.mark.parametrize("email", ["Ana@x.com", " ana@x.com", "ana@x.com "])
def test_AC_IDA_31_database_rejects_a_non_normalized_email(email: str) -> None:
    assert_rejected("users_email_normalized", email=email)


@pytest.mark.integration
@pytest.mark.django_db
@pytest.mark.parametrize(("is_active", "deactivated_at"), [(True, DEACTIVATED_AT), (False, None)])
def test_RN_IDA_25_is_active_must_match_deactivated_at(
    is_active: bool, deactivated_at: datetime | None
) -> None:
    assert_rejected("users_active_matches", is_active=is_active, deactivated_at=deactivated_at)


@pytest.mark.integration
@pytest.mark.django_db
def test_RN_IDA_25_deactivated_user_is_a_valid_row() -> None:
    user = User.objects.create(**row(is_active=False, deactivated_at=DEACTIVATED_AT))
    assert user.deactivated_at == DEACTIVATED_AT


@pytest.mark.integration
@pytest.mark.django_db
def test_RNF_IDA_05_no_usable_password() -> None:
    for user in (
        User.objects.create(**row()),
        User.objects.create_user(google_sub="sub-2", email="otra@x.com"),
    ):
        user.refresh_from_db()
        assert not user.has_usable_password()
        assert not user.check_password("")
        assert not user.check_password(user.password)


@pytest.mark.integration
@pytest.mark.django_db
def test_RNF_IDA_05_create_user_normalizes_what_comes_from_google() -> None:
    user = User.objects.create_user(
        google_sub="sub-1",
        email=" Ana@X.com ",
        display_name=TOO_LONG_NAME,
        avatar_url="http://example.com/a.png",
    )
    user.refresh_from_db()
    assert user.email == "ana@x.com"
    assert user.display_name == "n" * 150
    assert user.avatar_url == ""
    assert user.is_active
    assert user.deactivated_at is None
    assert user.last_login_at is None
