"""Page-number pagination of the API's lists (SPEC-02 design.md §6, adopted by SPEC-01 §6.2).

SPEC-00 fixes no pagination, so the lists use the fallback SPEC-02 adopted: ``?page=<n>`` with 50
items per page, ``?page_size=`` up to 200, and the envelope ``{count, next, previous, results}``.
It is opt-in per view (``pagination_class``), not ``DEFAULT_PAGINATION_CLASS``: a list that already
ships keeps its shape until its spec says otherwise.

``next`` and ``previous`` are relative (path and query): the browser reaches Django through the
BFF's proxy, so DRF's absolute links would name Django's internal host, which the browser cannot
reach and should not learn.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from rest_framework.pagination import PageNumberPagination

PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _relative(link: str | None) -> str | None:
    if link is None:
        return None
    parts = urlsplit(link)
    return urlunsplit(("", "", parts.path, parts.query, ""))


class HubPageNumberPagination(PageNumberPagination):
    page_size = PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = MAX_PAGE_SIZE

    def get_next_link(self) -> str | None:
        return _relative(super().get_next_link())

    def get_previous_link(self) -> str | None:
        return _relative(super().get_previous_link())

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        result = super().get_paginated_response_schema(schema)
        for name, example in (("next", "?page=4"), ("previous", "?page=2")):
            result["properties"][name] = {
                "type": "string",
                "nullable": True,
                "description": "Ruta relativa con la query de la página, o null.",
                "example": f"/api/recurso/{example}",
            }
        return result
