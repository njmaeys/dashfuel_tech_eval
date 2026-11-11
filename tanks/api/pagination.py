"""Limit/offset pagination: query params in, {count, limit, offset, results} envelope out.

Pagination happens in the repository (it returns a Page), so views never touch a queryset.
"""

from rest_framework import serializers

from tanks.domain import Page

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


class PaginationQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=MAX_LIMIT, default=DEFAULT_LIMIT)
    offset = serializers.IntegerField(min_value=0, default=0)


def paginated_response_data(page: Page, item_serializer_class: type[serializers.Serializer]) -> dict:
    return {
        "count": page.count,
        "limit": page.limit,
        "offset": page.offset,
        "results": item_serializer_class(page.items, many=True).data,
    }
