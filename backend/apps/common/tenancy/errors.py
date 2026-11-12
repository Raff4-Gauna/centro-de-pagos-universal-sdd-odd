"""Errors of the tenant resolution and authorization (spec §11, design.md §3.1, §3.5).

DRF ``APIException`` subclasses, so SPEC-00's handler turns them into ``application/problem+json``
with their ``code`` (ADR-0005: a published code is a contract). Each ``detail`` is fixed: it never
names the requested organization, so ``organization_not_found`` has the same body for an unknown
organization, one without membership and a revoked membership (AC-TEN-03/04, Q-219).

``TenantContextMissingError`` is not an API error: business code reached without a tenant is a
bug, and the handler answers any non-API exception with a generic ``500 internal_error``.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import APIException


class OrganizationRequired(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "organization_required"
    default_detail = "Falta la organización activa."


class OrganizationNotFound(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "organization_not_found"
    default_detail = "La organización no existe o no tenés acceso."


class OrganizationSuspended(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "organization_suspended"
    default_detail = "La organización está suspendida."


class Forbidden(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "forbidden"
    default_detail = "Tu rol no permite esta acción."


class TenantContextMissingError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("no tenant context is active")
