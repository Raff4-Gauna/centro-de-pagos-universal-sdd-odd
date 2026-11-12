"""Reads of ``users`` for the callback (design.md §3.1, RN-IDA-04, RN-IDA-21).

Users are global entities (spec §9): no ``organization_id`` to filter by, so each read goes by
one of the two unique keys, the ``sub`` (who the person is) or the normalized email (who else may
hold it). ``for_update`` locks the row until the caller's transaction ends; it needs one.
"""

from __future__ import annotations

from apps.identity.models import User


def get_by_sub(sub: str, *, for_update: bool = False) -> User | None:
    users = User.objects.select_for_update() if for_update else User.objects.all()
    return users.filter(google_sub=sub).first()


def get_by_email(email_normalized: str, *, for_update: bool = False) -> User | None:
    users = User.objects.select_for_update() if for_update else User.objects.all()
    return users.filter(email=email_normalized).first()
