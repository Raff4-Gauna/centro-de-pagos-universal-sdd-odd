"""The branches as the API shows them and the shape of what it takes (RF-TEN-06, design.md §6).

``BranchSerializer`` is the branch of every response. ``BranchCreateSerializer`` and
``BranchUpdateSerializer`` document the bodies of ``POST /api/branches/`` and
``PATCH /api/branches/{id}/`` for the contract only: ``services/branches.py`` validates each body
itself, strictly (an unknown key is ``unknown_field``, AC-TEN-07), so the API and any other caller
follow one rule. Their fields and limits come from the service (``CREATE_FIELDS``), and a test
keeps them in step. ``BranchListQuerySerializer`` reads ``?is_active=true|false``.

Comments instead of docstrings on the classes: drf-spectacular would publish a docstring as the
component's description.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.tenancy.models import Branch
from apps.tenancy.services.branches import CREATE_FIELDS


# One branch of the active organization; an inactive one carries when it was deactivated.
class BranchSerializer(serializers.Serializer[Branch]):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    address = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    deactivated_at = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta:
        ref_name = "Branch"


# name: required, not empty after removing spaces at both ends. code and address: optional, empty
# is "not informed". No other key is accepted.
class BranchCreateSerializer(serializers.Serializer[dict[str, Any]]):
    name = serializers.CharField(max_length=CREATE_FIELDS["name"])
    code = serializers.CharField(required=False, allow_blank=True, max_length=CREATE_FIELDS["code"])
    address = serializers.CharField(
        required=False, allow_blank=True, max_length=CREATE_FIELDS["address"]
    )

    class Meta:
        ref_name = "BranchCreate"


# Any of name, code and address; name, when present, not empty. No other key is accepted: the
# state changes only through deactivate and reactivate.
class BranchUpdateSerializer(BranchCreateSerializer):
    name = serializers.CharField(required=False, max_length=CREATE_FIELDS["name"])

    class Meta:
        ref_name = "BranchUpdate"


IS_ACTIVE_CHOICES = {"true": True, "false": False}


class BranchListQuerySerializer(serializers.Serializer[dict[str, Any]]):
    is_active = serializers.ChoiceField(
        choices=sorted(IS_ACTIVE_CHOICES),
        required=False,
        help_text="true: solo las activas · false: solo las inactivas · sin el parámetro: todas.",
    )

    def is_active_filter(self) -> bool | None:
        value = self.validated_data.get("is_active")
        return None if value is None else IS_ACTIVE_CHOICES[value]
