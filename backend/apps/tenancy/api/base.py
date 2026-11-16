"""``TenantViewSet``: the base of every tenant-scoped route (RF-TEN-08, RN-TEN-09, design.md §3.5).

Its permissions run in the order of the errors (design.md §3.5): ``IsAuthenticated`` (SPEC-01,
``401``) → ``ResolveTenant`` (``400``/``404`` organization) → ``ActionPermission`` (``403`` role,
``409`` suspended). ``self.tenant`` is the validated ``TenantContext`` of the request.

``action_specs`` maps every action of the viewset (the standard ones it defines and each
``@action``) to its ``ActionSpec``. A subclass that leaves one out, or maps it to something that is
not an ``ActionSpec``, fails when the class is created (``ImproperlyConfigured``), so no route of
any module ships without a role list and an ``ActionKind`` (design.md §3.7: the suspension is
applied by the kind).

The schema declares ``X-Organization-Id`` as a required header of every operation (design.md §6),
so the frontend's generated types demand it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from django.core.exceptions import ImproperlyConfigured
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework import viewsets

from apps.common.authz.actions import ActionSpec
from apps.common.tenancy.context import TenantContext
from apps.identity.api.authentication import IsAuthenticated
from apps.tenancy.api.permissions import (
    TENANT_HEADER,
    ActionPermission,
    ResolveTenant,
    tenant_of,
)

STANDARD_ACTIONS = ("list", "create", "retrieve", "update", "partial_update", "destroy")

ORGANIZATION_HEADER = OpenApiParameter(
    name=TENANT_HEADER,
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Organización activa de la request (RN-TEN-03).",
)


class TenantAutoSchema(AutoSchema):
    def get_override_parameters(self) -> list[Any]:
        return [*super().get_override_parameters(), ORGANIZATION_HEADER]


def _actions_of(cls: type[viewsets.GenericViewSet[Any]]) -> list[str]:
    standard = [name for name in STANDARD_ACTIONS if callable(getattr(cls, name, None))]
    extra = [method.__name__ for method in cls.get_extra_actions()]
    return [*standard, *extra]


class TenantViewSet(viewsets.GenericViewSet):
    tenant_scoped: ClassVar[bool] = True
    permission_classes = [IsAuthenticated, ResolveTenant, ActionPermission]  # noqa: RUF012
    action_specs: ClassVar[Mapping[str, ActionSpec]] = {}
    schema = TenantAutoSchema()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        wrong = [
            name
            for name in _actions_of(cls)
            if not isinstance(cls.action_specs.get(name), ActionSpec)
        ]
        if wrong:
            raise ImproperlyConfigured(
                f"{cls.__name__}: actions without an ActionSpec in action_specs: {', '.join(wrong)}"
            )

    @property
    def tenant(self) -> TenantContext:
        return tenant_of(self.request)
