"""AC-PLT-23 (backend; RN-PLT-15, RF-PLT-14, ADR-0005): the OpenAPI contract.

Every operation answers ``4XX``/``5XX`` with the ``Problem`` component
(``application/problem+json``) unless it declares that range itself.
"""

from __future__ import annotations

from typing import Any

from django.urls import URLPattern, URLResolver, path
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.utils import OpenApiResponse, extend_schema
from drf_spectacular.validation import validate_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.api.problems import PROBLEM_CONTENT_TYPE

PROBLEM_REF = "#/components/schemas/Problem"


class Echo(serializers.Serializer[dict[str, Any]]):
    message = serializers.CharField()


class SampleView(APIView):
    """A documented view: the hook adds what it does not declare."""

    @extend_schema(responses={200: Echo, "4XX": OpenApiResponse(description="declared")})
    def get(self, request: Request) -> Response:
        return Response({"message": "ok"})

    @extend_schema(request=Echo, responses={201: Echo})
    def post(self, request: Request) -> Response:
        return Response({"message": "ok"}, status=201)


# This module is the URLconf of the hook test.
urlpatterns: list[URLPattern | URLResolver] = [path("api/sample/", SampleView.as_view())]


def test_AC_PLT_23_problem_component_on_4xx_5xx() -> None:
    generated = SchemaGenerator(urlconf=__name__).get_schema(request=None, public=True)
    validate_schema(generated)
    operations = generated["paths"]["/api/sample/"]
    for method in ("get", "post"):
        for status_range in ("4XX", "5XX"):
            response = operations[method]["responses"][status_range]
            if (method, status_range) == ("get", "4XX"):
                assert response == {"description": "declared"}  # never overwritten
                continue
            content = response["content"]
            assert content == {PROBLEM_CONTENT_TYPE: {"schema": {"$ref": PROBLEM_REF}}}
    problem = generated["components"]["schemas"]["Problem"]
    assert problem["required"] == ["type", "title", "status", "code", "request_id"]
    assert set(problem["properties"]) == {*problem["required"], "detail", "errors"}
    field_error = generated["components"]["schemas"]["ProblemFieldError"]
    assert field_error["required"] == ["field", "code", "message"]
    # T-PLT-15 review: detail and errors[].message may echo client input; text, never HTML.
    assert "HTML" in problem["properties"]["detail"]["description"]
    assert "HTML" in field_error["properties"]["message"]["description"]
