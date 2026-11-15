"""RN-TEN-01 and AC-TEN-10 checked on Django's registry, not on the AST (design.md §9).

A **tenant model** is a subclass of ``TenantModel`` or ``settings.TENANT_MODEL`` (the organization).
That is decided by inheritance, never by the manager: a model that overrides ``objects`` with a
plain ``Manager`` is still a tenant model, and that manager is what fails here.

- ``untenanted_models``: every concrete model of ``apps/`` is a tenant model, except the app or
  model labels of ``allowlists.TENANT_EXEMPT_MODELS``; an exemption without a reason or that matches
  nothing fails.
- ``plain_tenant_managers``: every manager of a tenant model (``_meta.managers`` and
  ``_default_manager``) builds a ``TenantQuerySet``, so it fails closed. A plain one
  (``all_objects = models.Manager()``, or ``objects = models.Manager()``) would read every
  organization, and Django would hand it to related managers and serializers as the default.
  ``_base_manager`` stays plain on purpose: Django's internals (forward FKs, ``save``) use it, and
  ``TenantModel`` guards those itself (T-TEN-03).

The rules are pure (``ModelInfo``/``ManagerInfo`` in, ``Violation`` out); ``model_infos``,
``manager_infos`` and ``tenant_names`` read the model classes, so tests can pass models of an
isolated registry (``django.test.utils.isolate_apps``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import models

from apps.common.tenancy.models import TenantModel
from apps.common.tenancy.querysets import TenantQuerySet
from tests.architecture.ast_rules import Violation

MODEL_RULE = "RN-TEN-01"
MANAGER_RULE = "AC-TEN-10/manager"


@dataclass(frozen=True)
class ModelInfo:
    label: str  # "tenancy.Organization"
    module: str  # "apps.tenancy.models.organization"
    is_tenant: bool


@dataclass(frozen=True)
class ManagerInfo:
    label: str  # "tenancy.Membership"
    name: str  # "objects", or "_default_manager"
    fails_closed: bool  # builds a TenantQuerySet


def is_tenant_model(model: type[models.Model]) -> bool:
    return issubclass(model, TenantModel) or model._meta.label == settings.TENANT_MODEL


def model_infos(found: Iterable[type[models.Model]]) -> list[ModelInfo]:
    return [ModelInfo(m._meta.label, m.__module__, is_tenant_model(m)) for m in found]


def manager_infos(found: Iterable[type[models.Model]]) -> list[ManagerInfo]:
    infos = []
    for model in found:
        if not is_tenant_model(model):
            continue
        named: list[tuple[str, Any]] = [(m.name, m) for m in model._meta.managers]
        named.append(("_default_manager", model._default_manager))
        infos += [
            ManagerInfo(model._meta.label, name, isinstance(m.get_queryset(), TenantQuerySet))
            for name, m in named
        ]
    return infos


def tenant_names(found: Iterable[type[models.Model]]) -> tuple[frozenset[str], frozenset[str]]:
    """Class names of the tenant models and the names of their managers, for the AST rule."""
    tenant = [m for m in found if is_tenant_model(m)]
    managers = {manager.name for m in tenant for manager in m._meta.managers}
    return frozenset(m.__name__ for m in tenant), frozenset(managers | {"objects"})


def plain_tenant_managers(managers: Iterable[ManagerInfo]) -> list[Violation]:
    return sorted(
        Violation(
            m.label, 0, MANAGER_RULE, m.name, "manager of a tenant model that does not fail closed"
        )
        for m in managers
        if not m.fails_closed
    )


def untenanted_models(models_: Iterable[ModelInfo], exempt: Mapping[str, str]) -> list[Violation]:
    """Concrete models of ``apps/`` that are not tenant models and are not exempted."""
    business = [m for m in models_ if m.module.split(".")[0] == "apps"]

    def covers(key: str, model: ModelInfo) -> bool:
        return key in (model.label, model.label.split(".")[0])

    violations = [
        Violation(m.module, 0, MODEL_RULE, m.label, "business model without TenantModel")
        for m in business
        if not m.is_tenant and not any(covers(key, m) for key in exempt)
    ]
    for key, reason in exempt.items():
        if not reason.strip():
            violations.append(Violation(key, 0, MODEL_RULE, key, "exemption without a reason"))
        elif not any(covers(key, m) for m in business):
            violations.append(Violation(key, 0, MODEL_RULE, key, "dead exemption: no model"))
    return sorted(violations)
