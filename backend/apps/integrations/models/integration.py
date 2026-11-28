"""An organization's connection to one provider account (RN-INT-01, RN-INT-03, design.md §5).

A ``TenantModel``: its manager fails closed and ``save()`` writes only in the active organization
(AC-TEN-07, AC-TEN-11). The services normalize what is stored (the name without spaces at both
ends, Q-426) and decide the transitions; the constraints below are the final net even if a service
fails (ADR-0002 §2):

- ``integration_unique_active_name``: among the active integrations of one organization a name
  appears once, without telling upper from lower case; an inactive or disconnected one frees it
  (RN-INT-01, Q-426);
- ``integration_account_reserved``: ``(provider_code, environment, account_id)`` once in the whole
  platform among the integrations that are not disconnected (RN-INT-19, Q-403, Q-423, Q-427). The
  only invariant that crosses organizations, kept by a unique index and never by a query: with RLS
  PostgreSQL still checks it against every row (RNF-INT-06, design.md §5.2);
- ``integration_webhook_route_key_uniq``: the webhook route key, once in the whole platform
  (RN-INT-27). A new row gets ``token_urlsafe(32)`` (256 bits): not guessable;
- the closed enums (status, environment, connection status) as ``varchar`` + ``CHECK``;
- ``integration_reason_coherent``: a ``reason`` exactly when the last check failed (RN-INT-21);
  ``integration_connected_has_account``: ``connected`` always knows its account;
- ``integration_active_coherent`` and ``integration_disconnected_coherent``: the dates follow the
  status, and a disconnected one is back to ``unverified`` (Q-425);
- ``integration_unconfirmed_coherent``: only a known account, not ``connected`` and not
  disconnected, can be unconfirmed (RN-INT-19, Q-430 a));
- ``integration_org_id_uniq``: ``(organization_id, id)``, the target of the composite foreign keys
  of the credential set and the branch link (ADR-0002 §1, RN-INT-13).

``integration_org_status_name`` serves the listing. ``account_id`` never changes once known: the
services keep it (design.md §11). The account id is the only data of the provider's account kept
here (RNF-INT-10). An integration is never deleted (``NoHardDeleteMixin``, Q-408); its ``str`` and
``repr`` carry only the id, never the name nor the webhook route key (``C-16``).
"""

from __future__ import annotations

import secrets
import uuid
from enum import StrEnum
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from apps.common.tenancy.models import NoHardDeleteMixin, TenantModel

PROVIDER_CODE_MAX_LENGTH = 32
NAME_MAX_LENGTH = 120
ACCOUNT_ID_MAX_LENGTH = 128
WEBHOOK_ROUTE_KEY_MAX_LENGTH = 64
WEBHOOK_ROUTE_KEY_BYTES = 32


class IntegrationStatus(StrEnum):
    """Activity status (Q-408)."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DISCONNECTED = "disconnected"


class IntegrationEnvironment(StrEnum):
    """Provider environment (RN-INT-03)."""

    TEST = "test"
    PRODUCTION = "production"


class IntegrationConnectionStatus(StrEnum):
    """Result of the last connection check (RN-INT-21, Q-406)."""

    UNVERIFIED = "unverified"
    CONNECTED = "connected"
    CONNECTION_ERROR = "connection_error"
    CREDENTIALS_INVALID = "credentials_invalid"


# The connection statuses without a ``reason``: nothing failed (RN-INT-21).
STATUSES_WITHOUT_REASON = (
    IntegrationConnectionStatus.UNVERIFIED.value,
    IntegrationConnectionStatus.CONNECTED.value,
)


def _values(enum: type[StrEnum]) -> list[str]:
    return [member.value for member in enum]


def new_webhook_route_key() -> str:
    """A webhook route key: 256 random bits, URL-safe (RN-INT-27, Q-415)."""
    return secrets.token_urlsafe(WEBHOOK_ROUTE_KEY_BYTES)


_ACTIVE = Q(status=IntegrationStatus.ACTIVE.value)
_DISCONNECTED = Q(status=IntegrationStatus.DISCONNECTED.value)
_CONNECTED = Q(connection_status=IntegrationConnectionStatus.CONNECTED.value)
_WITHOUT_REASON = Q(connection_status__in=STATUSES_WITHOUT_REASON)


class Integration(NoHardDeleteMixin, TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider_code = models.CharField(max_length=PROVIDER_CODE_MAX_LENGTH)
    name = models.CharField(max_length=NAME_MAX_LENGTH)
    environment = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default=IntegrationStatus.ACTIVE.value)
    connection_status = models.CharField(
        max_length=24, default=IntegrationConnectionStatus.UNVERIFIED.value
    )
    # NULL while nothing failed, as design.md §5 says (integration_reason_coherent).
    connection_reason = models.CharField(max_length=48, null=True, blank=True)  # noqa: DJ001
    connection_checked_at = models.DateTimeField(null=True, blank=True)
    # NULL while unknown (Q-403): a unique index ignores NULL, an unknown account reserves nothing.
    account_id = models.CharField(  # noqa: DJ001
        max_length=ACCOUNT_ID_MAX_LENGTH, null=True, blank=True
    )
    account_unconfirmed = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)
    webhook_route_key = models.CharField(
        max_length=WEBHOOK_ROUTE_KEY_MAX_LENGTH, default=new_webhook_route_key
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    disconnected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=Q(status__in=_values(IntegrationStatus)),
                name="integration_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(environment__in=_values(IntegrationEnvironment)),
                name="integration_environment_valid",
            ),
            models.CheckConstraint(
                condition=Q(connection_status__in=_values(IntegrationConnectionStatus)),
                name="integration_connection_status_valid",
            ),
            models.CheckConstraint(condition=~Q(name=""), name="integration_name_not_blank"),
            models.UniqueConstraint(
                F("organization"),
                Lower("name"),
                condition=_ACTIVE,
                name="integration_unique_active_name",
            ),
            models.UniqueConstraint(
                fields=["provider_code", "environment", "account_id"],
                condition=Q(account_id__isnull=False) & ~_DISCONNECTED,
                name="integration_account_reserved",
            ),
            models.CheckConstraint(
                condition=Q(account_id__isnull=True) | ~Q(account_id=""),
                name="integration_account_not_blank",
            ),
            models.CheckConstraint(
                condition=~_CONNECTED | Q(account_id__isnull=False),
                name="integration_connected_has_account",
            ),
            models.CheckConstraint(
                condition=(_WITHOUT_REASON & Q(connection_reason__isnull=True))
                | (~_WITHOUT_REASON & Q(connection_reason__isnull=False)),
                name="integration_reason_coherent",
            ),
            models.CheckConstraint(
                condition=(_ACTIVE & Q(deactivated_at__isnull=True))
                | (~_ACTIVE & Q(deactivated_at__isnull=False)),
                name="integration_active_coherent",
            ),
            models.CheckConstraint(
                condition=(
                    _DISCONNECTED
                    & Q(disconnected_at__isnull=False)
                    & Q(connection_status=IntegrationConnectionStatus.UNVERIFIED.value)
                )
                | (~_DISCONNECTED & Q(disconnected_at__isnull=True)),
                name="integration_disconnected_coherent",
            ),
            models.CheckConstraint(
                condition=Q(account_unconfirmed=False)
                | (Q(account_id__isnull=False) & ~_CONNECTED & ~_DISCONNECTED),
                name="integration_unconfirmed_coherent",
            ),
            models.UniqueConstraint(
                fields=["webhook_route_key"], name="integration_webhook_route_key_uniq"
            ),
            models.UniqueConstraint(fields=["organization", "id"], name="integration_org_id_uniq"),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["organization", "status", "name"], name="integration_org_status_name"
            ),
        ]

    def __str__(self) -> str:
        """The id: an ``Integration`` in a log carries neither its name nor its webhook key."""
        return str(self.pk)
