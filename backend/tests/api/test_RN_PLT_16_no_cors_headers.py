"""RN-PLT-16 (Q-050): the backend sends no CORS headers (T-PLT-15).

The browser talks only to the BFF (same origin); ERP and webhooks call the backend server to
server. So no response, simple or preflight, success or error, allows another origin.
"""

from __future__ import annotations

import pytest
from django.test import Client

ORIGIN = "https://other-origin.example"

pytestmark = pytest.mark.urls("tests.api.urls_test")


@pytest.mark.parametrize("path", ["/healthz", "/api/test/problems", "/api/missing"])
def test_RN_PLT_16_backend_sends_no_cors_headers(client: Client, path: str) -> None:
    simple = client.get(path, HTTP_ORIGIN=ORIGIN)
    preflight = client.options(
        path,
        HTTP_ORIGIN=ORIGIN,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization, content-type",
    )
    for response in (simple, preflight):
        cors = [name for name in response.headers if name.lower().startswith("access-control-")]
        assert cors == [], (path, response.status_code)
