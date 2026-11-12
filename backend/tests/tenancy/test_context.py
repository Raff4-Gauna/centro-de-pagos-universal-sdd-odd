"""RF-TEN-01 / RF-TEN-08 (design.md §3.1): the tenant context, its scope and its errors.

Pure where possible: no database (the organization model arrives with T-TEN-02). The middleware is
exercised through the real ``MIDDLEWARE`` chain with a fake inner view.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Iterator

import pytest
from django.http import HttpRequest, HttpResponse
from rest_framework.exceptions import APIException
from structlog.contextvars import bind_contextvars, get_contextvars

from apps.common.api.exceptions import problem_exception_handler
from apps.common.logging import context as log_context
from apps.common.tenancy.context import (
    ApiKeyActor,
    OrgStatus,
    SystemActor,
    SystemReason,
    TenantContext,
    UserActor,
)
from apps.common.tenancy.current import (
    activate_tenant,
    clear_tenant,
    current_tenant,
    require_current_tenant,
    tenant_scope,
)
from apps.common.tenancy.errors import (
    Forbidden,
    OrganizationNotFound,
    OrganizationRequired,
    OrganizationSuspended,
    TenantContextMissingError,
)
from apps.common.tenancy.middleware import TenantContextMiddleware

ORG_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
ORG_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def _ctx(organization_id: uuid.UUID = ORG_A) -> TenantContext:
    actor = UserActor(user_id=uuid.uuid4(), membership_id=uuid.uuid4(), role="owner")
    return TenantContext(
        organization_id=organization_id, organization_status=OrgStatus.ACTIVE, actor=actor
    )


@pytest.fixture(autouse=True)
def _empty_contexts() -> Iterator[None]:
    """No tenant nor log key from another test (``activate_tenant`` has no ``with`` to close it)."""
    clear_tenant()
    log_context.clear()
    yield
    clear_tenant()
    log_context.clear()


# --- TenantContext ---


def test_RF_TEN_01_context_is_frozen() -> None:
    ctx = _ctx()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.organization_id = ORG_B  # type: ignore[misc]
    assert isinstance(ctx.actor, UserActor)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.actor.role = "viewer"  # type: ignore[misc]


def test_RF_TEN_01_context_has_no_dict_to_smuggle_attributes() -> None:
    ctx = _ctx()
    assert not hasattr(ctx, "__dict__")
    with pytest.raises((AttributeError, TypeError)):
        ctx.extra = 1  # type: ignore[attr-defined]


def test_RF_TEN_01_context_rejects_a_non_uuid_organization() -> None:
    actor = SystemActor(reason=SystemReason.CELERY)
    with pytest.raises(TypeError):
        TenantContext(
            organization_id=str(ORG_A),  # type: ignore[arg-type]
            organization_status=OrgStatus.ACTIVE,
            actor=actor,
        )


def test_RF_TEN_01_context_rejects_an_unknown_status_or_actor() -> None:
    actor = SystemActor(reason=SystemReason.WEBHOOK)
    with pytest.raises(TypeError):
        TenantContext(organization_id=ORG_A, organization_status="active", actor=actor)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        TenantContext(organization_id=ORG_A, organization_status=OrgStatus.ACTIVE, actor="me")  # type: ignore[arg-type]


def test_RF_TEN_01_context_is_suspended_flag() -> None:
    actor = ApiKeyActor(key_id=uuid.uuid4(), scopes=frozenset({"charges:read"}))
    ctx = TenantContext(organization_id=ORG_A, organization_status=OrgStatus.SUSPENDED, actor=actor)
    assert ctx.is_suspended
    assert not _ctx().is_suspended


def test_RF_TEN_01_enum_values_are_the_contract() -> None:
    assert {s.value for s in OrgStatus} == {"active", "suspended"}
    assert {r.value for r in SystemReason} == {"webhook", "poller", "celery", "platform_command"}


# --- tenant_scope / current_tenant ---


def test_RF_TEN_01_no_context_outside_a_scope() -> None:
    assert current_tenant() is None
    with pytest.raises(TenantContextMissingError):
        require_current_tenant()


def test_RF_TEN_01_scope_exposes_the_context() -> None:
    ctx = _ctx()
    with tenant_scope(ctx) as active:
        assert active is ctx
        assert current_tenant() is ctx
        assert require_current_tenant() is ctx


def test_RF_TEN_01_scope_resets_on_exit() -> None:
    with tenant_scope(_ctx()):
        pass
    assert current_tenant() is None


def test_RF_TEN_01_scope_resets_on_exception() -> None:
    with pytest.raises(RuntimeError), tenant_scope(_ctx()):
        raise RuntimeError("boom")
    assert current_tenant() is None
    assert "organization_id" not in get_contextvars()


def test_RF_TEN_01_nested_scope_restores_the_outer_one() -> None:
    outer, inner = _ctx(ORG_A), _ctx(ORG_B)
    with tenant_scope(outer):
        with tenant_scope(inner):
            assert current_tenant() is inner
            assert get_contextvars()["organization_id"] == str(ORG_B)
        assert current_tenant() is outer
        assert get_contextvars()["organization_id"] == str(ORG_A)
    assert current_tenant() is None


@pytest.mark.parametrize("value", [None, ORG_A, str(ORG_A), object()])
def test_RF_TEN_08_scope_requires_a_tenant_context(value: object) -> None:
    with pytest.raises(TypeError), tenant_scope(value):  # type: ignore[arg-type]
        pass
    assert current_tenant() is None


# --- Logging (C-16) ---


def test_RF_TEN_01_organization_id_bound_to_logs() -> None:
    bind_contextvars(request_id="req-1")
    with tenant_scope(_ctx()):
        assert get_contextvars() == {"request_id": "req-1", "organization_id": str(ORG_A)}
    assert get_contextvars() == {"request_id": "req-1"}


def test_RF_TEN_01_scope_restores_an_organization_id_bound_before() -> None:
    log_context.bind_organization(ORG_B)
    with tenant_scope(_ctx(ORG_A)):
        assert get_contextvars()["organization_id"] == str(ORG_A)
    assert get_contextvars()["organization_id"] == str(ORG_B)


# --- Middleware ---


def _run_middleware(view_ctx: TenantContext | None) -> list[TenantContext | None]:
    seen: list[TenantContext | None] = []

    def view(request: HttpRequest) -> HttpResponse:
        seen.append(current_tenant())
        if view_ctx is not None:
            activate_tenant(view_ctx)  # what ResolveTenant does; the middleware clears it
            seen.append(current_tenant())
        return HttpResponse()

    TenantContextMiddleware(view)(HttpRequest())
    return seen


def test_RF_TEN_01_middleware_starts_each_request_without_tenant() -> None:
    activate_tenant(_ctx(ORG_B))  # a tenant leaked by a previous request on this thread
    seen = _run_middleware(None)
    assert seen == [None]
    assert current_tenant() is None


def test_RF_TEN_01_activate_binds_the_log_and_checks_the_type() -> None:
    activate_tenant(_ctx())
    assert get_contextvars()["organization_id"] == str(ORG_A)
    with pytest.raises(TypeError):
        activate_tenant(ORG_B)  # type: ignore[arg-type]
    active = current_tenant()
    assert active is not None
    assert active.organization_id == ORG_A


def test_RF_TEN_01_middleware_resets_the_context_at_the_end() -> None:
    ctx = _ctx()
    seen = _run_middleware(ctx)
    assert seen == [None, ctx]
    assert current_tenant() is None
    assert "organization_id" not in get_contextvars()


def test_RF_TEN_01_middleware_resets_even_if_the_view_fails() -> None:
    def view(request: HttpRequest) -> HttpResponse:
        activate_tenant(_ctx())
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        TenantContextMiddleware(view)(HttpRequest())
    assert current_tenant() is None
    assert "organization_id" not in get_contextvars()


def test_RF_TEN_01_middleware_is_registered_right_after_request_id(settings: object) -> None:
    from django.conf import settings as django_settings

    middleware = django_settings.MIDDLEWARE
    assert middleware[0] == "apps.common.middleware.request_id.RequestIdMiddleware"
    assert middleware[1] == "apps.common.tenancy.middleware.TenantContextMiddleware"


# --- Errors (problem+json, SPEC-00) ---


@pytest.mark.parametrize(
    ("exc_class", "status", "code"),
    [
        (OrganizationRequired, 400, "organization_required"),
        (OrganizationNotFound, 404, "organization_not_found"),
        (OrganizationSuspended, 409, "organization_suspended"),
        (Forbidden, 403, "forbidden"),
    ],
)
def test_RF_TEN_08_errors_map_to_problem_json(
    exc_class: type[APIException], status: int, code: str
) -> None:
    response = problem_exception_handler(exc_class(), {})
    assert response.status_code == status
    assert response.data["code"] == code
    assert response.data["type"] == f"urn:hub:problem:{code}"


def test_RF_TEN_01_organization_not_found_body_is_constant() -> None:
    first = problem_exception_handler(OrganizationNotFound(), {}).data
    second = problem_exception_handler(OrganizationNotFound(), {}).data
    assert first == second
    assert str(ORG_A) not in str(first)


def test_RF_TEN_08_missing_context_is_a_generic_500() -> None:
    response = problem_exception_handler(TenantContextMissingError(), {})
    assert response.status_code == 500
    assert response.data["code"] == "internal_error"
    assert "detail" not in response.data
