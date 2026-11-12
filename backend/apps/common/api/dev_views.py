"""Dev-only API views (Q-056, D-14): routed only by ``config.urls_dev`` (dev and test settings).

``POST /api/dev/diagnostic-task/`` enqueues ``diagnostic_ping`` and answers 202 with its ``task_id``
and the ``request_id`` of this request, which the task logs too (AC-PLT-11). No authentication: in
prod the route does not exist, so nobody can fill the queue through it. The API denies by default
since SPEC-01, so the view opens itself explicitly, as /healthz is open: it reads no credential.
"""

from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.logging import context
from apps.common.tasks import diagnostic_ping


class DiagnosticTaskView(APIView):
    # Anonymous in dev (00 design.md §6): no authentication, so even a bad Bearer cannot reject it.
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request: Request) -> Response:
        result = diagnostic_ping.delay()
        body = {"task_id": result.id, "request_id": context.current_request_id()}
        return Response(body, status=202)
