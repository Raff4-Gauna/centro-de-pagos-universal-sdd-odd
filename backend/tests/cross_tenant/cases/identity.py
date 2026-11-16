"""SPEC-01's routes: none is tenant-scoped (design.md §3.5, "las de SPEC-00/01").

They act on the person, not on an organization: who they are (``/api/me/``), their own sessions
(global entities, SPEC-01 spec §9) and the BFF's login, refresh and logout, which run before or
outside any organization. The fake OIDC provider is mounted only with
``IDENTITY_OIDC_PROVIDER=fake`` (Q-122), so its routes are ``optional``. The two ``GET`` behind the
login give ``read``: the suite checks that they show nothing of another person or organization.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from tests.cross_tenant.registry import Exemption

if TYPE_CHECKING:
    from apps.tenancy.models import Organization

_ME = "la persona autenticada y sus organizaciones; sin organización activa (design.md §3.5)"
_SESSIONS = "sesiones propias de la persona: entidad global sin organization_id (SPEC-01 §9)"
_BFF = "solo el BFF (X-Hub-Bff-Credential); corre antes de que haya sesión u organización"
_FAKE_OIDC = "proveedor OIDC falso, solo dev/test (Q-122); no conoce usuarios ni organizaciones"


def _at(url: str) -> Callable[[Organization], str]:
    def read(organization: Organization) -> str:
        return url

    return read


EXEMPT = (
    Exemption("api/me/", _ME, read=_at("/api/me/")),
    Exemption("api/auth/sessions/", _SESSIONS, read=_at("/api/auth/sessions/")),
    Exemption("api/auth/sessions/revoke-others/", _SESSIONS),
    Exemption("api/auth/sessions/<uuid:session_id>/revoke/", _SESSIONS),
    Exemption("api/auth/bff/login/start/", _BFF),
    Exemption("api/auth/bff/login/complete/", _BFF),
    Exemption("api/auth/bff/refresh/", _BFF),
    Exemption("api/auth/bff/logout/", _BFF),
    Exemption("dev-oidc/authorize", _FAKE_OIDC, optional=True),
    Exemption("dev-oidc/token", _FAKE_OIDC, optional=True),
    Exemption("dev-oidc/jwks", _FAKE_OIDC, optional=True),
)
