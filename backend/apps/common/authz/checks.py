"""Whether the actor of a ``TenantContext`` may run an action (RN-TEN-09, design.md §3.5, §3.8).

Deny by default. A ``UserActor`` passes when the role of its membership is in ``spec.roles``; an
``ApiKeyActor`` when the action declares an ``api_key_scope`` and the key holds it (SPEC-11); a
``SystemActor`` never: processes without a user do not go through the matrix (design.md §3.6).

Order of the errors (design.md §3.5): the role first (``403 forbidden``), then the suspension
(``409 organization_suspended`` for every kind outside ``SUSPENDED_ALLOWED_KINDS``). The checks that
depend on the target (roles of the membership or invitation, last owner) belong to each service.
"""

from __future__ import annotations

from collections.abc import Iterable

from apps.common.authz.actions import SUSPENDED_ALLOWED_KINDS, ActionSpec
from apps.common.tenancy.context import ApiKeyActor, TenantContext, UserActor
from apps.common.tenancy.errors import Forbidden, OrganizationSuspended


def require(ctx: TenantContext, spec: ActionSpec) -> None:
    """Raise ``Forbidden`` or ``OrganizationSuspended`` unless ``ctx`` may run ``spec``."""
    if not _actor_may(ctx, spec):
        raise Forbidden()
    if _blocked_by_suspension(ctx, spec):
        raise OrganizationSuspended()


def allowed_actions(ctx: TenantContext, specs: Iterable[ActionSpec]) -> list[str]:
    """Names of the actions ``require`` lets through, in the order given (for the UI)."""
    return [
        spec.name
        for spec in specs
        if _actor_may(ctx, spec) and not _blocked_by_suspension(ctx, spec)
    ]


def _actor_may(ctx: TenantContext, spec: ActionSpec) -> bool:
    actor = ctx.actor
    if isinstance(actor, UserActor):
        return actor.role in spec.roles
    if isinstance(actor, ApiKeyActor):
        return spec.api_key_scope is not None and spec.api_key_scope in actor.scopes
    return False


def _blocked_by_suspension(ctx: TenantContext, spec: ActionSpec) -> bool:
    return ctx.is_suspended and spec.kind not in SUSPENDED_ALLOWED_KINDS
