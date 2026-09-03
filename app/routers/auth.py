import asyncio
import logging
from typing import Annotated
from urllib.parse import urlencode

import markdown
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from pydantic import EmailStr

from app.config import SESSION_COOKIE_NAME, settings
from app.database import AsyncSessionLocal
from app.dependencies import (
    get_current_active_user,
    get_current_admin_user,
    get_current_user,
    get_password_reset_mailer,
    get_user_service,
    get_worldpop_service,
    verify_csrf,
)
from app.models.models import User
from app.schemas.schemas import TokenResponse
from app.services.exceptions import InactiveUserError, InvalidCredentialsError
from app.services.exceptions import (
    EmailAlreadyExistsError,
    InvalidResetCodeError,
    InvalidUserDataError,
    ProhibitedUserOperationError,
)
from app.services.email import PasswordResetMailer
from app.services.security import csrf_token
from app.services.users import UserService
from app.services.worldpop import TileNotFoundError, WorldPopService, parse_iso3_csv


router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")


def _template_context(request: Request, current_user: User | None) -> dict[str, object]:
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    return {
        "current_user": current_user,
        "csrf_token": csrf_token(session_token) if session_token else None,
        "app_name": settings.APP_NAME,
        "password_min_length": settings.PASSWORD_MIN_LENGTH,
        "password_max_length": settings.PASSWORD_MAX_LENGTH,
    }


async def _manage_users_error(
    request: Request,
    current_user: User,
    service: UserService,
    status_code: int,
) -> HTMLResponse:
    context = _template_context(request, current_user)
    context["users"] = await service.visible_users(current_user)
    context["error"] = "The requested user change could not be completed."
    return templates.TemplateResponse(
        request, "users.html", context, status_code=status_code
    )


async def _process_tile_cache_fill(iso3_codes: str) -> None:
    for iso3 in parse_iso3_csv(iso3_codes):
        try:
            async with AsyncSessionLocal() as session:
                if await WorldPopService(session).get_cached_tile_path(iso3):
                    continue

            file_path = await WorldPopService.download_tile_file(
                iso3, skip_missing=True
            )

            async with AsyncSessionLocal() as session, session.begin():
                await WorldPopService(session).cache_downloaded_tile(iso3, file_path)
        except TileNotFoundError:
            logging.info("Skipping missing tile %s during cache fill", iso3)
        except Exception:
            logging.exception("Tile cache fill task failed for country %s", iso3)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home(
    request: Request,
    current_user: Annotated[User | None, Depends(get_current_user)],
) -> HTMLResponse:
    if current_user is not None and not current_user.is_active:
        current_user = None
    context = _template_context(request, current_user)
    context["error"] = request.query_params.get("error")
    context["status"] = request.query_params.get("status")
    return templates.TemplateResponse(request, "index.html", context)


@router.post("/login", response_class=RedirectResponse, include_in_schema=False)
async def login(
    username: Annotated[EmailStr, Form()],
    password: Annotated[str, Form()],
    service: Annotated[UserService, Depends(get_user_service)],
) -> Response:
    try:
        user = await service.authenticate_password(str(username), password)
    except InvalidCredentialsError, InactiveUserError:
        return RedirectResponse(
            url="/?error=invalid_credentials",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    token = service.create_session_jwt(user)
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=settings.SESSION_EXPIRE_MINUTES * 60,
    )
    return response


@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: Annotated[UserService, Depends(get_user_service)],
) -> TokenResponse:
    user = await service.authenticate_password(form_data.username, form_data.password)
    return TokenResponse(access_token=service.create_access_jwt(user))


@router.post("/logout", response_class=RedirectResponse, include_in_schema=False)
async def logout(
    _current_user: Annotated[User, Depends(get_current_active_user)],
    _csrf: Annotated[None, Depends(verify_csrf)],
) -> Response:
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/manage-users", response_class=HTMLResponse, include_in_schema=False)
async def manage_users_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> HTMLResponse:
    context = _template_context(request, current_user)
    context["users"] = await service.visible_users(current_user)
    return templates.TemplateResponse(request, "users.html", context)


@router.post("/users/create", response_class=RedirectResponse, include_in_schema=False)
async def create_user_route(
    request: Request,
    email: Annotated[EmailStr, Form()],
    password: Annotated[
        str,
        Form(
            min_length=settings.PASSWORD_MIN_LENGTH,
            max_length=settings.PASSWORD_MAX_LENGTH,
        ),
    ],
    service: Annotated[UserService, Depends(get_user_service)],
    _current_user: Annotated[User, Depends(get_current_admin_user)],
    _csrf: Annotated[None, Depends(verify_csrf)],
    is_admin: Annotated[bool, Form()] = False,
) -> Response:
    try:
        await service.create_user(str(email), password, is_admin)
    except EmailAlreadyExistsError:
        return await _manage_users_error(
            request, _current_user, service, status.HTTP_409_CONFLICT
        )
    except InvalidUserDataError:
        return await _manage_users_error(
            request, _current_user, service, status.HTTP_400_BAD_REQUEST
        )
    return RedirectResponse("/manage-users", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/users/{user_id}/regen-token",
    response_class=RedirectResponse,
    include_in_schema=False,
)
async def regenerate_token(
    request: Request,
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
    _current_user: Annotated[User, Depends(get_current_admin_user)],
    _csrf: Annotated[None, Depends(verify_csrf)],
) -> Response:
    try:
        await service.regenerate_token(user_id)
    except ProhibitedUserOperationError:
        return await _manage_users_error(
            request, _current_user, service, status.HTTP_400_BAD_REQUEST
        )
    return RedirectResponse("/manage-users", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/users/{user_id}/toggle-active",
    response_class=RedirectResponse,
    include_in_schema=False,
)
async def toggle_active(
    request: Request,
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
    _csrf: Annotated[None, Depends(verify_csrf)],
) -> Response:
    try:
        await service.toggle_active(user_id, current_user)
    except ProhibitedUserOperationError:
        return await _manage_users_error(
            request, current_user, service, status.HTTP_400_BAD_REQUEST
        )
    return RedirectResponse("/manage-users", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/users/{user_id}/toggle-admin",
    response_class=RedirectResponse,
    include_in_schema=False,
)
async def toggle_admin(
    request: Request,
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
    _csrf: Annotated[None, Depends(verify_csrf)],
) -> Response:
    try:
        await service.toggle_admin(user_id, current_user)
    except ProhibitedUserOperationError:
        return await _manage_users_error(
            request, current_user, service, status.HTTP_400_BAD_REQUEST
        )
    return RedirectResponse("/manage-users", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/users/{user_id}/delete",
    response_class=RedirectResponse,
    include_in_schema=False,
)
async def delete_user(
    request: Request,
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
    _csrf: Annotated[None, Depends(verify_csrf)],
) -> Response:
    try:
        await service.delete_user(user_id, current_user)
    except ProhibitedUserOperationError:
        return await _manage_users_error(
            request, current_user, service, status.HTTP_400_BAD_REQUEST
        )
    return RedirectResponse("/manage-users", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/app-docs", response_class=HTMLResponse, include_in_schema=False)
async def app_docs(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> HTMLResponse:
    readme = await asyncio.to_thread(_read_repository_guide)
    context = _template_context(request, current_user)
    context["content"] = Markup(
        markdown.markdown(readme, extensions=["fenced_code", "tables"])
    )
    return templates.TemplateResponse(request, "app_docs.html", context)


def _read_repository_guide() -> str:
    with open("README.md", encoding="utf-8") as guide:
        return guide.read()


@router.get("/tile-cache", response_class=HTMLResponse, include_in_schema=False)
async def tile_cache_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    service: Annotated[WorldPopService, Depends(get_worldpop_service)],
) -> HTMLResponse:
    context = _template_context(request, current_user)
    context.update(
        {
            "tiles": await service.list_cached_tiles(),
            "status": request.query_params.get("status"),
            "message": request.query_params.get("message"),
        }
    )
    return templates.TemplateResponse(request, "tile_cache.html", context)


@router.get("/forgot-password", response_class=HTMLResponse, include_in_schema=False)
async def forgot_password_page(request: Request) -> HTMLResponse:
    context = _template_context(request, None)
    context["submitted"] = request.query_params.get("submitted") == "1"
    return templates.TemplateResponse(request, "forgot_password.html", context)


@router.post(
    "/forgot-password", response_class=RedirectResponse, include_in_schema=False
)
async def request_password_reset(
    request: Request,
    email: Annotated[EmailStr, Form()],
    service: Annotated[UserService, Depends(get_user_service)],
    mailer: Annotated[PasswordResetMailer, Depends(get_password_reset_mailer)],
) -> RedirectResponse:
    await service.request_password_reset(str(email), mailer)
    return RedirectResponse(
        "/forgot-password?submitted=1", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/reset-password", response_class=HTMLResponse, include_in_schema=False)
async def reset_password_page(request: Request) -> HTMLResponse:
    context = _template_context(request, None)
    context["error"] = None
    return templates.TemplateResponse(request, "reset_password.html", context)


@router.post(
    "/reset-password",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
async def reset_password(
    request: Request,
    code: Annotated[str, Form()],
    password: Annotated[str, Form()],
    service: Annotated[UserService, Depends(get_user_service)],
) -> HTMLResponse | RedirectResponse:
    try:
        await service.reset_password(code, password)
    except InvalidResetCodeError:
        context = _template_context(request, None)
        context["error"] = "The reset code is invalid or has expired."
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            context,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except InvalidUserDataError:
        context = _template_context(request, None)
        context["error"] = "Your password does not meet the required length."
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            context,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(
        "/?status=password_reset", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post(
    "/tile-cache/fill",
    response_class=RedirectResponse,
    include_in_schema=False,
)
async def fill_tile_cache(
    background_tasks: BackgroundTasks,
    iso3_codes: Annotated[str, Form()],
    _current_user: Annotated[User, Depends(get_current_admin_user)],
    _csrf: Annotated[None, Depends(verify_csrf)],
) -> RedirectResponse:
    try:
        iso3_list = parse_iso3_csv(iso3_codes)
    except ValueError as exc:
        query = urlencode({"status": "error", "message": str(exc)})
        return RedirectResponse(
            f"/tile-cache?{query}", status_code=status.HTTP_303_SEE_OTHER
        )
    background_tasks.add_task(_process_tile_cache_fill, ",".join(iso3_list))
    query = urlencode(
        {
            "status": "success",
            "message": f"Queued {len(iso3_list)} tile(s) for cache fill.",
        }
    )
    return RedirectResponse(
        f"/tile-cache?{query}", status_code=status.HTTP_303_SEE_OTHER
    )
