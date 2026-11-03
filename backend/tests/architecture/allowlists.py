"""Exceptions to the architecture rules (RN-PLT-09; design.md §3.2.6).

Both lists start empty on purpose. An entry names one violation exactly (``path`` is the
"/"-separated path from ``backend/``, ``symbol`` the ``Violation.symbol`` it silences) and says why.
``ast_rules.apply_allowlist`` fails the run for an entry without a reason or that matches no
violation (a dead entry), so an exception can neither hide its motive nor outlive the code it was
written for. This module is data only: it imports nothing from the rules.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AllowEntry:
    path: str
    symbol: str
    reason: str


# C-09: imports of ``apps.integrations.providers.<x>`` from outside ``providers/<x>/``. SPEC-03 adds
# the provider registry here; nothing else is expected.
ADAPTER_IMPORT_ALLOWLIST: tuple[AllowEntry, ...] = ()

# C-01: raw manager access (``.objects``, ``._default_manager``, ``._base_manager``) in
# ``apps/<app>/services/``. SPEC-02 fills it when the tenant-aware managers exist.
ALLOWED_TENANT_MANAGERS: tuple[AllowEntry, ...] = ()
