"""
Standardised pagination + response envelope used by all ViewSets.

Every successful response returns:
    {
        "success": true,
        "data":    { ... } | [ ... ],
        "meta":    {                  ← only on list responses
            "count":    150,
            "page":     2,
            "pages":    6,
            "per_page": 25,
            "next":     "https://…?page=3",
            "previous": "https://…?page=1"
        }
    }
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "per_page"
    max_page_size = 200
    page_query_param = "page"

    def get_paginated_response(self, data):
        return Response(
            {
                "success": True,
                "data": data,
                "meta": {
                    "count": self.page.paginator.count,
                    "page": self.page.number,
                    "pages": self.page.paginator.num_pages,
                    "per_page": self.get_page_size(self.request),
                    "next": self.get_next_link(),
                    "previous": self.get_previous_link(),
                },
            },
        )

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": schema,
                "meta": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "page": {"type": "integer"},
                        "pages": {"type": "integer"},
                        "per_page": {"type": "integer"},
                        "next": {"type": "string", "nullable": True},
                        "previous": {"type": "string", "nullable": True},
                    },
                },
            },
        }


def success_response(
    data=None,
    message: str | None = None,
    status_code: int = 200,
) -> dict:
    """
    Helper for single-object responses in views.
    Usage:
        return Response(success_response(serializer.data), status=201)
    """
    payload = {"success": True}
    if message:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return payload
