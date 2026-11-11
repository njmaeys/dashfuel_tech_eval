"""Maps domain errors to HTTP responses so views don't need try/except.

Registered as REST_FRAMEWORK["EXCEPTION_HANDLER"] in config/settings.py.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from tanks.exceptions import DuplicateTankVolume, TankNotFound, TankVolumeNotFound

STATUS_CODE_BY_DOMAIN_ERROR = {
    TankNotFound: status.HTTP_404_NOT_FOUND,
    TankVolumeNotFound: status.HTTP_404_NOT_FOUND,
    DuplicateTankVolume: status.HTTP_409_CONFLICT,
}


def domain_exception_handler(exc: Exception, context: dict) -> Response | None:
    for domain_error_type, status_code in STATUS_CODE_BY_DOMAIN_ERROR.items():
        if isinstance(exc, domain_error_type):
            return Response({"detail": str(exc)}, status=status_code)
    # Validation errors, unsupported media type, etc. Anything unhandled becomes a 500.
    return exception_handler(exc, context)
