"""Role-based access control for the HaloVision admin system."""

from typing import List, Optional

ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"
ROLE_MODERATOR = "moderator"
ROLE_SUPPORT = "support"
ROLE_PREMIUM = "premium"
ROLE_FREE = "free"

ROLES = [
    ROLE_SUPER_ADMIN,
    ROLE_ADMIN,
    ROLE_MODERATOR,
    ROLE_SUPPORT,
    ROLE_PREMIUM,
    ROLE_FREE,
]

# Permission hierarchy for admin capabilities.
_ADMIN_POWER = {
    ROLE_SUPER_ADMIN: 6,
    ROLE_ADMIN: 5,
    ROLE_MODERATOR: 4,
    ROLE_SUPPORT: 3,
    ROLE_PREMIUM: 1,
    ROLE_FREE: 0,
}

ADMIN_ROLES = [ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_MODERATOR, ROLE_SUPPORT]


def role_power(role: Optional[str]) -> int:
    return _ADMIN_POWER.get((role or ROLE_FREE).lower(), 0)


def is_admin_role(role: Optional[str]) -> bool:
    return (role or ROLE_FREE).lower() in ADMIN_ROLES


def build_access(role: Optional[str]):
    """Super Admin gets unrestricted access; others are restricted per role."""
    return {
        "dashboard": role_power(role) >= 3,
        "users_view": role_power(role) >= 3,
        "users_write": role_power(role) >= 4,
        "users_delete": role_power(role) >= 5,
        "settings": role_power(role) >= 5,
        "feature_flags": role_power(role) >= 4,
        "activity": role_power(role) >= 3,
        "system": role_power(role) >= 6,
    }