from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.account_tokens import consume_account_token, mint_account_token
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.dependencies import get_current_user, require_permission
from app.core.email import send_email
from app.core.limiter import limiter
from app.core.permissions import Permission
from app.core.security import (
    create_access_token,
    create_csrf_token,
    create_refresh_token,
    csrf_token_is_valid,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.datetime_utils import utc_now
from app.db.session import get_db_session
from app.models.user import User, UserRole
from app.models.user_account_token import AccountTokenPurpose
from app.schemas.auth import (
    AuthenticatedUserResponse,
    ForgotPasswordRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserRegisterRequest,
    UserRoleUpdateRequest,
    VerifyEmailRequest,
    authenticated_user_from_orm,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _app_settings(request: Request) -> Settings:
    s = getattr(request.app.state, "settings", None)
    return s if isinstance(s, Settings) else default_settings


def _set_refresh_cookie(response: Response, refresh_token: str, s: Settings) -> None:
    response.set_cookie(
        key=s.auth_refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=s.auth_cookie_secure_effective,
        samesite=s.auth_cookie_samesite,
        max_age=s.refresh_token_expire_minutes * 60,
        path="/",
    )


def _clear_refresh_cookie(response: Response, s: Settings) -> None:
    response.delete_cookie(key=s.auth_refresh_cookie_name, path="/")


def _extract_refresh_token(request: Request, payload: RefreshTokenRequest, s: Settings) -> str:
    if s.auth_refresh_cookie_enabled:
        cookie_tok = request.cookies.get(s.auth_refresh_cookie_name)
        if cookie_tok:
            if not csrf_token_is_valid(request.headers.get("X-CSRF-Token")):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF token missing or invalid",
                )
            return cookie_tok
    if payload.refresh_token is not None:
        return payload.refresh_token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing refresh token",
    )


def _require_logout_csrf_if_cookie(request: Request, s: Settings) -> None:
    if not s.auth_refresh_cookie_enabled:
        return
    if not request.cookies.get(s.auth_refresh_cookie_name):
        return
    if not csrf_token_is_valid(request.headers.get("X-CSRF-Token")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid",
        )


@router.post(
    "/register", response_model=AuthenticatedUserResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit(default_settings.auth_register_rate_limit)
async def register_user(
    request: Request,
    payload: Annotated[UserRegisterRequest, Body()],
    db_session: AsyncSession = Depends(get_db_session),
) -> AuthenticatedUserResponse:
    existing_user = await db_session.scalar(select(User).where(User.email == payload.email.lower()))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    s = _app_settings(request)
    verified_at = None if s.auth_require_email_verification else utc_now()
    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        is_active=True,
        role=UserRole.user,
        email_verified_at=verified_at,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    if s.auth_require_email_verification:
        raw = await mint_account_token(
            db_session,
            user_id=user.id,
            purpose=AccountTokenPurpose.email_verify,
            expire_minutes=s.email_verification_token_expire_minutes,
        )
        await send_email(
            settings=s,
            to_addr=user.email,
            subject="Verify your email",
            body_text=f"Use this token with POST /api/v1/auth/verify-email:\n\n{raw}\n",
        )
        await db_session.commit()

    return authenticated_user_from_orm(user)


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@limiter.limit(default_settings.auth_login_rate_limit)
async def login_user(
    request: Request,
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db_session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    s = _app_settings(request)
    normalized_email = form_data.username.lower()
    user = await db_session.scalar(select(User).where(User.email == normalized_email))
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    if s.auth_require_email_verification and user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified",
        )

    subject = str(user.id)
    access_token = create_access_token(subject=subject, token_version=user.token_version)
    refresh_token = create_refresh_token(subject=subject, token_version=user.token_version)
    user.refresh_token_hash = hash_password(refresh_token)

    await db_session.commit()

    if s.auth_refresh_cookie_enabled:
        _set_refresh_cookie(response, refresh_token, s)
        return TokenResponse(
            access_token=access_token,
            refresh_token=None,
            csrf_token=create_csrf_token(),
        )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, csrf_token=None)


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@limiter.limit(default_settings.auth_refresh_rate_limit)
async def refresh_token_pair(
    request: Request,
    response: Response,
    db_session: AsyncSession = Depends(get_db_session),
    payload: Annotated[RefreshTokenRequest | None, Body()] = None,
) -> TokenResponse:
    s = _app_settings(request)
    effective_payload = payload if payload is not None else RefreshTokenRequest()
    raw_refresh = _extract_refresh_token(request, effective_payload, s)

    try:
        token_payload = decode_token(raw_refresh)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    if token_payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token type"
        )

    subject = token_payload.get("sub")
    if subject is None or not subject.isdigit():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    token_version = token_payload.get("token_version")
    if not isinstance(token_version, int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    user = await db_session.scalar(select(User).where(User.id == int(subject)))
    if user is None or not user.is_active or user.refresh_token_hash is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    if s.auth_require_email_verification and user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified",
        )
    if user.token_version != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked"
        )

    is_valid_refresh_token = verify_password(raw_refresh, user.refresh_token_hash)
    if not is_valid_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    new_access_token = create_access_token(subject=str(user.id), token_version=user.token_version)
    new_refresh_token = create_refresh_token(subject=str(user.id), token_version=user.token_version)
    user.refresh_token_hash = hash_password(new_refresh_token)

    await db_session.commit()

    if s.auth_refresh_cookie_enabled:
        _set_refresh_cookie(response, new_refresh_token, s)
        return TokenResponse(
            access_token=new_access_token,
            refresh_token=None,
            csrf_token=create_csrf_token(),
        )
    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        csrf_token=None,
    )


@router.post(
    "/verify-email",
    response_model=AuthenticatedUserResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(default_settings.auth_verify_email_rate_limit)
async def verify_email(
    request: Request,
    payload: Annotated[VerifyEmailRequest, Body()],
    db_session: AsyncSession = Depends(get_db_session),
) -> AuthenticatedUserResponse:
    user = await consume_account_token(
        db_session,
        raw_token=payload.token,
        purpose=AccountTokenPurpose.email_verify,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )
    user.email_verified_at = utc_now()
    await db_session.commit()
    await db_session.refresh(user)
    return authenticated_user_from_orm(user)


@router.post(
    "/forgot-password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
@limiter.limit(default_settings.auth_forgot_password_rate_limit)
async def forgot_password(
    request: Request,
    payload: Annotated[ForgotPasswordRequest, Body()],
    db_session: AsyncSession = Depends(get_db_session),
) -> Response:
    s = _app_settings(request)
    normalized = payload.email.lower()
    user = await db_session.scalar(select(User).where(User.email == normalized))
    if user is not None and user.is_active:
        raw = await mint_account_token(
            db_session,
            user_id=user.id,
            purpose=AccountTokenPurpose.password_reset,
            expire_minutes=s.password_reset_token_expire_minutes,
        )
        await send_email(
            settings=s,
            to_addr=user.email,
            subject="Password reset",
            body_text=f"Use this token with POST /api/v1/auth/reset-password:\n\n{raw}\n",
        )
        await db_session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
@limiter.limit(default_settings.auth_reset_password_rate_limit)
async def reset_password(
    request: Request,
    payload: Annotated[ResetPasswordRequest, Body()],
    db_session: AsyncSession = Depends(get_db_session),
) -> Response:
    user = await consume_account_token(
        db_session,
        raw_token=payload.token,
        purpose=AccountTokenPurpose.password_reset,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    user.hashed_password = hash_password(payload.new_password)
    user.token_version += 1
    user.refresh_token_hash = None
    await db_session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=AuthenticatedUserResponse, status_code=status.HTTP_200_OK)
async def get_authenticated_user(
    user: User = Depends(get_current_user),
) -> AuthenticatedUserResponse:
    return authenticated_user_from_orm(user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def logout_user(
    request: Request,
    user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> Response:
    s = _app_settings(request)
    _require_logout_csrf_if_cookie(request, s)
    user.refresh_token_hash = None
    user.token_version += 1
    await db_session.commit()
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    if s.auth_refresh_cookie_enabled:
        _clear_refresh_cookie(resp, s)
    return resp


@router.patch(
    "/users/{user_id}/role",
    response_model=AuthenticatedUserResponse,
    status_code=status.HTTP_200_OK,
)
async def update_user_role(
    user_id: int,
    payload: Annotated[UserRoleUpdateRequest, Body()],
    db_session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission(Permission.USER_MANAGE_ROLES)),
) -> AuthenticatedUserResponse:
    user = await db_session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.role = payload.role
    await db_session.commit()
    await db_session.refresh(user)
    return authenticated_user_from_orm(user)
