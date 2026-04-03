from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import User, UserRole


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str | None = None

    @field_validator("refresh_token")
    @classmethod
    def refresh_min_length(cls, value: str | None) -> str | None:
        if value is not None and len(value) < 20:
            raise ValueError("refresh_token is too short")
        return value


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    csrf_token: str | None = None


class AuthenticatedUserResponse(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    role: UserRole
    email_verified: bool


def authenticated_user_from_orm(user: User) -> AuthenticatedUserResponse:
    return AuthenticatedUserResponse(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        role=user.role,
        email_verified=user.email_verified_at is not None,
    )


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    new_password: str = Field(min_length=8, max_length=128)


class UserRoleUpdateRequest(BaseModel):
    role: UserRole
