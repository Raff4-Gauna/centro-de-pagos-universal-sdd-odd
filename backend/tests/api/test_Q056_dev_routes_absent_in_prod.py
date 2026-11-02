"""Q-056 (D-14, ADR-0005): the dev-only routes exist in dev and test, never in prod.

``/api/dev/*`` lives only in ``config.urls_dev`` (the ``ROOT_URLCONF`` of dev and test); prod uses
``config.urls``, where those paths answer the problem+json 404 of any unknown ``/api/`` route. The
diagnostic task enqueues work without authentication: in prod it would let anyone fill the queue.
T-PLT-18 adds ``/api/dev/schema/`` and ``/api/dev/docs/`` to ``DEV_ROUTES``.
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import Resolver404, resolve

from tests.config.test_AC_PLT_03_missing_required_var import PROD, VALID_PROD_ENV
from tests.conftest import RunDjango

DEV_ROUTES = ("/api/dev/diagnostic-task/",)

# Run in a prod process: the URLconf prod settings point at, and whether each dev route resolves.
_PROD_PROBE = """
import django
from django.conf import settings
from django.urls import Resolver404, resolve
django.setup()
found = []
for path in {routes!r}:
    try:
        resolve(path)
        found.append(path)
    except Resolver404:
        pass
print(settings.ROOT_URLCONF, found)
"""


@pytest.mark.urls("config.urls")
@pytest.mark.parametrize("path", DEV_ROUTES)
def test_Q056_dev_routes_absent_in_prod(client: Client, path: str) -> None:
    with pytest.raises(Resolver404):
        resolve(path)
    for method in (client.get, client.post):
        response = method(path)
        assert response.status_code == 404
        assert response["Content-Type"] == "application/problem+json"


def test_Q056_prod_settings_use_the_public_urlconf(run_django: RunDjango) -> None:
    probe = _PROD_PROBE.format(routes=DEV_ROUTES)
    result = run_django("-c", probe, settings_module=PROD, values=VALID_PROD_ENV)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "config.urls []"


@pytest.mark.parametrize("urlconf", ["config.urls_dev"])
@pytest.mark.parametrize("path", DEV_ROUTES)
def test_Q056_dev_routes_exist_in_dev_and_test(urlconf: str, path: str) -> None:
    assert resolve(path, urlconf=urlconf).route == path.lstrip("/")
