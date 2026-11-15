"""RN-TEN-01 and AC-TEN-10 on Django's registry (``tenant_model_rules``, design.md §9).

Every concrete model of ``apps/`` is a tenant model (or exempted), and every manager of a tenant
model fails closed. The real run reads ``django.apps.apps`` (no database); the synthetic models are
declared inside ``isolate_apps``, so they never reach the real registry nor the other tests.
"""

from __future__ import annotations

from django.apps import apps as registry
from django.db import models
from django.test.utils import isolate_apps

from apps.common.tenancy.models import TenantModel
from apps.common.tenancy.querysets import TenantManager
from tests.architecture.allowlists import TENANT_EXEMPT_MODELS
from tests.architecture.tenant_model_rules import (
    ManagerInfo,
    ModelInfo,
    manager_infos,
    model_infos,
    plain_tenant_managers,
    tenant_names,
    untenanted_models,
)

PROBE_APP = "tests.testapps.tenant_probe"
IDENTITY_MODELS = {
    "identity.User",
    "identity.AuthSession",
    "identity.RefreshToken",
    "identity.LoginAttempt",
}


def flagged(managers: list[ManagerInfo]) -> list[tuple[str, str]]:
    return [(v.path, v.symbol) for v in plain_tenant_managers(managers)]


def test_RN_TEN_01_every_business_model_is_a_tenant_model() -> None:
    found = model_infos(registry.get_models())
    assert {"tenancy.Organization", "tenancy.Membership"} <= {m.label for m in found if m.is_tenant}
    assert untenanted_models(found, TENANT_EXEMPT_MODELS) == []


def test_RN_TEN_01_identity_exemption_covers_only_the_known_models() -> None:
    """``identity`` is exempted as an app: a new model there has to be looked at on purpose."""
    labels = {m._meta.label for m in registry.get_models() if m._meta.app_label == "identity"}
    assert labels == IDENTITY_MODELS


def test_RN_TEN_01_rule_flags_a_model_without_tenant_model() -> None:
    found = [
        ModelInfo("charges.Charge", "apps.charges.models", is_tenant=False),
        ModelInfo("charges.Refund", "apps.charges.models", is_tenant=True),
        ModelInfo("identity.User", "apps.identity.models.user", is_tenant=False),
        ModelInfo("tenancy.Organization", "apps.tenancy.models.organization", is_tenant=True),
        ModelInfo("auth.Group", "django.contrib.auth.models", is_tenant=False),
    ]
    exempt = {"identity": "global"}
    assert [(v.path, v.symbol) for v in untenanted_models(found, exempt)] == [
        ("apps.charges.models", "charges.Charge")
    ]
    dead = {**exempt, "charges.Charge": "", "audit": "SPEC-10"}
    assert [(v.symbol, v.msg) for v in untenanted_models(found, dead)] == [
        ("audit", "dead exemption: no model"),
        ("charges.Charge", "exemption without a reason"),
    ]


def test_AC_TEN_10_every_manager_of_a_tenant_model_fails_closed() -> None:
    managers = manager_infos(registry.get_models())
    assert ("tenancy.Membership", "objects") in {(m.label, m.name) for m in managers}
    assert ("tenancy.Organization", "_default_manager") in {(m.label, m.name) for m in managers}
    assert flagged(managers) == []


@isolate_apps(PROBE_APP)
def test_AC_TEN_10_extra_plain_manager_on_a_tenant_model_fails() -> None:
    class Leaky(TenantModel):
        all_objects = models.Manager()

        class Meta:
            app_label = "tenant_probe"

    found = flagged(manager_infos([Leaky]))
    assert ("tenant_probe.Leaky", "all_objects") in found
    assert ("tenant_probe.Leaky", "objects") not in found
    tenant_models, managers = tenant_names([Leaky])
    assert ("Leaky" in tenant_models, "all_objects" in managers) == (True, True)


@isolate_apps(PROBE_APP)
def test_AC_TEN_10_overridden_objects_on_a_tenant_model_fails() -> None:
    class Overridden(TenantModel):
        objects = models.Manager()  # type: ignore[assignment]  # the override under test

        class Meta:
            app_label = "tenant_probe"

    assert flagged(manager_infos([Overridden])) == [
        ("tenant_probe.Overridden", "_default_manager"),
        ("tenant_probe.Overridden", "objects"),
    ]
    # Still a tenant model for the AST rule: inheritance decides, not the manager.
    assert "Overridden" in tenant_names([Overridden])[0]


@isolate_apps(PROBE_APP)
def test_AC_TEN_10_extra_tenant_manager_passes() -> None:
    class Twice(TenantModel):
        archived = TenantManager()

        class Meta:
            app_label = "tenant_probe"

    managers = manager_infos([Twice])
    assert {m.name for m in managers} == {"objects", "archived", "_default_manager"}
    assert flagged(managers) == []
