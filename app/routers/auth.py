from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user, require_permission
from app.core.limiter import limiter
from app.core.permissions import Permission
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db_session
from app.models.user import User, UserRole
from app.schemas.auth import (
    AuthenticatedUserResponse,
    RefreshTokenRequest,
    TokenResponse,
    UserRegisterRequest,
    UserRoleUpdateRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=AuthenticatedUserResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit(settings.auth_register_rate_limit)
async def register_user(
    request: Request,
    payload: UserRegisterRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> AuthenticatedUserResponse:
    existing_user = await db_session.scalar(select(User).where(User.email == payload.email.lower()))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        is_active=True,
        role=UserRole.user,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return AuthenticatedUserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@limiter.limit(settings.auth_login_rate_limit)
async def login_user(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db_session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    normalized_email = form_data.username.lower()
    user = await db_session.scalar(select(User).where(User.email == normalized_email))
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    subject = str(user.id)
    access_token = create_access_token(subject=subject, token_version=user.token_version)
    refresh_token = create_refresh_token(subject=subject, token_version=user.token_version)
    user.refresh_token_hash = hash_password(refresh_token)

    await db_session.commit()
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@limiter.limit(settings.auth_refresh_rate_limit)
async def refresh_token_pair(
    request: Request,
    payload: RefreshTokenRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    try:
        token_payload = decode_token(payload.refresh_token)
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
    if user.token_version != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked"
        )

    is_valid_refresh_token = verify_password(payload.refresh_token, user.refresh_token_hash)
    if not is_valid_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    new_access_token = create_access_token(subject=str(user.id), token_version=user.token_version)
    new_refresh_token = create_refresh_token(subject=str(user.id), token_version=user.token_version)
    user.refresh_token_hash = hash_password(new_refresh_token)

    await db_session.commit()
    return TokenResponse(access_token=new_access_token, refresh_token=new_refresh_token)


@router.get("/me", response_model=AuthenticatedUserResponse, status_code=status.HTTP_200_OK)
async def get_authenticated_user(
    user: User = Depends(get_current_user),
) -> AuthenticatedUserResponse:
    return AuthenticatedUserResponse.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_user(
    response: Response,
    user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> None:
    user.refresh_token_hash = None
    user.token_version += 1
    await db_session.commit()
    response.status_code = status.HTTP_204_NO_CONTENT


@router.patch(
    "/users/{user_id}/role",
    response_model=AuthenticatedUserResponse,
    status_code=status.HTTP_200_OK,
)
async def update_user_role(
    user_id: int,
    payload: UserRoleUpdateRequest,
    db_session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission(Permission.USER_MANAGE_ROLES)),
) -> AuthenticatedUserResponse:
    user = await db_session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.role = payload.role
    await db_session.commit()
    await db_session.refresh(user)
    return AuthenticatedUserResponse.model_validate(user)
