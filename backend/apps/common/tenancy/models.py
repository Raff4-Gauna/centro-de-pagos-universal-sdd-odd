"""Model mixins of the tenant base (design.md §3.1, §3.4, ADR-0002).

``NoHardDeleteMixin``: ``Organization``, ``Membership``, ``Invitation`` and ``Branch`` are
deactivated or revoked, never deleted. ``Model.delete()`` raises here and ``QuerySet.delete()`` in
``TenantQuerySet`` (it reads ``hard_delete_forbidden``); every FK to these tables is ``PROTECT``.
``TenantModel`` arrives with T-TEN-03.
"""

from __future__ import annotations

from typing import Any, ClassVar

from apps.common.tenancy.querysets import HardDeleteForbidden


class NoHardDeleteMixin:
    hard_delete_forbidden: ClassVar[bool] = True

    def delete(self, using: Any = None, keep_parents: bool = False) -> tuple[int, dict[str, int]]:
        raise HardDeleteForbidden(type(self).__name__)
