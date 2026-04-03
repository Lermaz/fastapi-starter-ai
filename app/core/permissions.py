from enum import StrEnum

from app.models.user import UserRole


class Permission(StrEnum):
    VIDEOGAME_READ = "videogame:read"
    VIDEOGAME_WRITE = "videogame:write"
    USER_MANAGE_ROLES = "user:manage_roles"


PERMISSIONS_BY_ROLE: dict[UserRole, frozenset[Permission]] = {
    UserRole.admin: frozenset(Permission),
    UserRole.user: frozenset({Permission.VIDEOGAME_READ}),
}


def permissions_for(role: UserRole) -> frozenset[Permission]:
    return PERMISSIONS_BY_ROLE[role]
