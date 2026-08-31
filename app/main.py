import html
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.config import SESSION_COOKIE_NAME, settings
from app.dependencies import get_current_active_user
from app.models.models import User
from app.routers import api, auth
from app.services.exceptions import DomainError
from app.services.security import csrf_token
from app.services.worldpop import (
    CoordinatesOutsideCountryError,
    GeoJSONOutsideCountryError,
    TileNotFoundError,
)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.APP_NAME,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        swagger_ui_parameters={"persistAuthorization": True},
    )
    application.include_router(auth.router)
    application.include_router(api.router)
    application.add_exception_handler(DomainError, _domain_error_handler)
    application.add_exception_handler(
        CoordinatesOutsideCountryError, _unprocessable_domain_error_handler
    )
    application.add_exception_handler(
        GeoJSONOutsideCountryError, _unprocessable_domain_error_handler
    )
    application.add_exception_handler(TileNotFoundError, _not_found_error_handler)
    application.add_exception_handler(Exception, _unexpected_error_handler)

    @application.middleware("http")
    async def add_security_headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @application.get("/docs", response_class=HTMLResponse, include_in_schema=False)
    async def protected_swagger(
        request: Request,
        user: User = Depends(get_current_active_user),
    ) -> HTMLResponse:
        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        form_csrf_token = csrf_token(session_token) if session_token else ""
        persistent_token = user.bearer_token if not user.is_admin else None
        swagger = get_swagger_ui_html(
            openapi_url="/openapi.json",
            title=f"{settings.APP_NAME} - Swagger UI",
            swagger_js_url=(
                "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
            ),
            swagger_css_url=(
                "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"
            ),
            swagger_ui_parameters=application.swagger_ui_parameters,
        )
        body = bytes(swagger.body).decode("utf-8")
        body = body.replace(
            "</head>",
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/'
            'bootstrap@5.3.3/dist/css/bootstrap.min.css"></head>',
        )
        body = body.replace(
            "<body>", f"<body>{_swagger_navigation(user, form_csrf_token)}", 1
        )
        if persistent_token:
            encoded_token = json.dumps(persistent_token)
            body = body.replace(
                "</body>",
                "<script>window.addEventListener('load', () => {"
                "const waitForSwagger = window.setInterval(() => {"
                "if (window.ui) { window.clearInterval(waitForSwagger); "
                f"window.ui.preauthorizeApiKey('BearerAuth', {encoded_token});"
                "}}, 100);});</script></body>",
            )
        return HTMLResponse(body, status_code=swagger.status_code)

    @application.get("/openapi.json", include_in_schema=False)
    async def protected_openapi(
        _user: User = Depends(get_current_active_user),
    ) -> JSONResponse:
        return JSONResponse(application.openapi())

    return application


async def _domain_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    domain_error = exc
    status_code = getattr(domain_error, "status_code", 400)
    return JSONResponse({"detail": str(domain_error)}, status_code=status_code)


async def _unprocessable_domain_error_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    return JSONResponse(
        {"detail": str(exc)}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
    )


async def _not_found_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)


async def _unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unexpected request failure: method=%s path=%s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        {"detail": "Internal server error"},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _swagger_navigation(user: User, form_csrf_token: str) -> str:
    admin_link = (
        '<li class="nav-item"><a class="nav-link" href="/tile-cache">'
        "Tile Cache</a></li>"
        if user.is_admin
        else ""
    )
    return f"""
<nav class="navbar navbar-expand-lg bg-dark navbar-dark">
  <div class="container">
    <a class="navbar-brand" href="/">{html.escape(settings.APP_NAME)}</a>
    <ul class="navbar-nav ms-auto flex-row gap-3">
      <li class="nav-item"><a class="nav-link" href="/docs">API</a></li>
      <li class="nav-item"><a class="nav-link" href="/app-docs">Guide</a></li>
      <li class="nav-item"><a class="nav-link" href="/manage-users">Users</a></li>
      {admin_link}
      <li class="nav-item">
        <form action="/logout" method="post">
          <input type="hidden" name="csrf_token" value="{html.escape(form_csrf_token)}">
          <button class="btn btn-link nav-link" type="submit">Sign out</button>
        </form>
      </li>
    </ul>
  </div>
</nav>
"""


app = create_app()
