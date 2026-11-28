"""The credential set of one integration, encrypted at rest (RN-INT-04, RN-INT-06, ADR-0003).

A ``TenantModel``: its manager fails closed and ``save()`` writes only in the active organization
(AC-TEN-07, AC-TEN-11). This module stores the envelope of ADR-0003 §3 and never encrypts nor
decrypts (``domain/credential_cipher.py``, T-INT-05): the secret values exist only inside
``ciphertext`` (nonce ‖ ciphertext ‖ tag); ``public_fields`` keeps the non-secret fields of the set
and ``secret_field_names`` the names of the configured secret ones, to show "configured" (Q-405).
The constraints are the final net even if a service fails (ADR-0002 §2):

- ``credentialset_one_per_integration``: one set per integration; a replacement rewrites it and
  bumps ``version`` (RN-INT-06), ``credentialset_version_positive`` keeps it ``>= 1``;
- ``credentialset_format_v1``, ``credentialset_key_id_valid`` (the key ids of the keyring,
  ``^[a-z0-9-]{1,32}$``) and ``credentialset_ciphertext_min``: at least the 12-byte nonce and the
  16-byte tag;
- ``credentialset_integration_same_org`` (migration ``0002``, ``RunSQL``): the composite foreign
  key ``(organization_id, integration_id) -> integrations_integration (organization_id, id)``, so a
  set can only belong to an integration of its own organization, also for a row written without
  the ORM (RN-INT-13, design.md §5.1). Django 5.2 cannot declare it; the plain FK is for the ORM.

``credentialset_key_id`` serves the progress of a key rotation (ADR-0003 §5). Unlike the other
tables of the module a set is deleted when its integration is disconnected (RN-INT-24): no
``NoHardDeleteMixin``. Its ``str`` and ``repr`` carry only the id (RNF-INT-01).
"""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import F, Func, IntegerField, Q
from django.db.models.lookups import GreaterThanOrEqual

from apps.common.tenancy.models import TenantModel
from apps.integrations.models.integration import Integration

KEY_ID_MAX_LENGTH = 32
KEY_ID_PATTERN = r"^[a-z0-9-]{1,32}$"
FORMAT_VERSION = 1
# AES-GCM: 12-byte nonce + 16-byte tag around the ciphertext (ADR-0003 §1, §3).
CIPHERTEXT_MIN_BYTES = 28
# Name of the composite foreign key that migration 0002 creates by SQL (design.md §5.1).
SAME_ORG_CONSTRAINT = "credentialset_integration_same_org"


class CredentialSet(TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    integration = models.ForeignKey(Integration, on_delete=models.PROTECT, related_name="+")
    version = models.IntegerField()
    key_id = models.CharField(max_length=KEY_ID_MAX_LENGTH)
    format_version = models.SmallIntegerField()
    ciphertext = models.BinaryField()
    public_fields = models.JSONField(default=dict, blank=True)
    secret_field_names = models.JSONField(default=list, blank=True)
    credentials_updated_at = models.DateTimeField()
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reencrypted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["integration"], name="credentialset_one_per_integration"
            ),
            models.CheckConstraint(
                condition=Q(version__gte=1), name="credentialset_version_positive"
            ),
            models.CheckConstraint(
                condition=Q(format_version=FORMAT_VERSION), name="credentialset_format_v1"
            ),
            models.CheckConstraint(
                condition=Q(key_id__regex=KEY_ID_PATTERN), name="credentialset_key_id_valid"
            ),
            models.CheckConstraint(
                condition=GreaterThanOrEqual(
                    Func(F("ciphertext"), function="OCTET_LENGTH", output_field=IntegerField()),
                    CIPHERTEXT_MIN_BYTES,
                ),
                name="credentialset_ciphertext_min",
            ),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["key_id"], name="credentialset_key_id"),
        ]

    def __str__(self) -> str:
        """The id: a ``CredentialSet`` in a log carries no field of the set (RNF-INT-01)."""
        return str(self.pk)
