"""Django settings for the DashFuel take-home. Local development only."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Local development only. A real deployment would load these from the environment.
SECRET_KEY = "django-insecure-cxu=^hg+2&^h_awiuzmv8^jf(f_vxoaq@^d4ra_6p7zct317yi"
DEBUG = True
ALLOWED_HOSTS = []

INSTALLED_APPS = [
    # Everything in this block exists to support the Django admin.
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "drf_spectacular",  # OpenAPI schema + Swagger UI
    # Local
    "tanks",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",  # trailing-slash redirects (APPEND_SLASH)
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Only used to render the admin's HTML pages; the API itself is JSON only.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# All timestamps are stored and returned in UTC.
TIME_ZONE = "UTC"
USE_TZ = True
USE_I18N = False

# Serves the admin's CSS/JS under runserver.
STATIC_URL = "static/"

REST_FRAMEWORK = {
    # JSON in, JSON out. Drops DRF's browsable HTML API and form parsers.
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # The API has no auth for this take-home (see README).
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    # Return Decimal fields (e.g. volume) as JSON numbers instead of strings.
    "COERCE_DECIMAL_TO_STRING": False,
    # Maps domain errors (TankNotFound, DuplicateTankVolume, ...) to 404/409 responses.
    "EXCEPTION_HANDLER": "tanks.api.exception_handler.domain_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# OpenAPI docs: /api/docs/ (Swagger UI) and /api/schema/ (OpenAPI 3 YAML, importable into
# Insomnia/Postman). The committed openapi.yaml is regenerated with:
#   python manage.py spectacular --file openapi.yaml
SPECTACULAR_SETTINGS = {
    "TITLE": "DashFuel Tank Analytics API",
    "DESCRIPTION": (
        "Gas station storage tanks and their volume readings. All timestamps are UTC (ISO 8601). "
        "Soft-deleted tanks return 404 on every route under them."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,  # don't list the schema endpoint inside the schema
}
