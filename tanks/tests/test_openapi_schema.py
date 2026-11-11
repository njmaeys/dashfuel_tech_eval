"""OpenAPI schema tests: keep /api/docs/ and the committed openapi.yaml honest.

No DB needed: schema generation only inspects URLs, views, and serializers.
"""

from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.renderers import OpenApiYamlRenderer

COMMITTED_SCHEMA_PATH = Path(settings.BASE_DIR) / "openapi.yaml"
REGENERATE_COMMAND = "python manage.py spectacular --file openapi.yaml"


def test_schema_is_valid_and_generates_without_warnings():
    # --fail-on-warn: any endpoint whose request/response types can't be resolved fails here.
    # --validate: the output must be valid OpenAPI 3.
    call_command(
        "spectacular", "--validate", "--fail-on-warn", stdout=StringIO(), stderr=StringIO()
    )


def test_committed_openapi_yaml_is_up_to_date():
    """Fails when the API changed but openapi.yaml wasn't regenerated."""
    schema = SchemaGenerator().get_schema(request=None, public=True)
    generated_schema = OpenApiYamlRenderer().render(schema, renderer_context={}).decode()

    assert COMMITTED_SCHEMA_PATH.exists(), f"openapi.yaml is missing. Run: {REGENERATE_COMMAND}"
    committed_schema = COMMITTED_SCHEMA_PATH.read_text(encoding="utf-8")
    # Normalize line endings so a Windows checkout (CRLF) still compares equal.
    assert committed_schema.replace("\r\n", "\n") == generated_schema.replace("\r\n", "\n"), (
        f"openapi.yaml is out of date. Run: {REGENERATE_COMMAND}"
    )
