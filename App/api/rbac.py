# =============================================================================
# FILE: App/api/rbac.py
# ROLE: Role-Based Access Control — defines role hierarchy and permissions.
#
# WHAT THIS FILE DOES:
#   Defines the role hierarchy (super_admin > admin > moderator > support > premium > free)
#   and maps each role to a set of permissions for the admin panel.
#
# WHO USES THIS:
#   - admin.py: uses is_admin_role() and build_access() for authorization
#   - migrations.py: uses ROLE_SUPER_ADMIN for seeding the initial admin
#
# ROLE HIERARCHY:
#   super_admin (power 6) → full system access
#   admin (power 5)       → user management, settings
#   moderator (power 4)   → user writes, feature flags
#   support (power 3)     → dashboard, user views, activity log
#   premium (power 1)     → basic access (not admin)
#   free (power 0)        → no admin access
# =============================================================================

"""Role-based access control for the HaloVision admin system."""

from typing import List, Optional

# Role constants
ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"
ROLE_MODERATOR = "moderator"
ROLE_SUPPORT = "support"
ROLE_PREMIUM = "premium"
ROLE_FREE = "free"

# Ordered list of all roles (highest to lowest)
ROLES = [
    ROLE_SUPER_ADMIN,
    ROLE_ADMIN,
    ROLE_MODERATOR,
    ROLE_SUPPORT,
    ROLE_PREMIUM,
    ROLE_FREE,
]

# Power levels for each role — higher power = more permissions
_ADMIN_POWER = {
    ROLE_SUPER_ADMIN: 6,
    ROLE_ADMIN: 5,
    ROLE_MODERATOR: 4,
    ROLE_SUPPORT: 3,
    ROLE_PREMIUM: 1,
    ROLE_FREE: 0,
}

# Roles that have admin panel access
ADMIN_ROLES = [ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_MODERATOR, ROLE_SUPPORT]


def role_power(role: Optional[str]) -> int:
    """Get the power level for a role. Unknown roles get power 0."""
    return _ADMIN_POWER.get((role or ROLE_FREE).lower(), 0)


def is_admin_role(role: Optional[str]) -> bool:
    """Check if a role has admin panel access."""
    return (role or ROLE_FREE).lower() in ADMIN_ROLES


def build_access(role: Optional[str]):
    """Build a permission map for a given role.
    Returns a dict of feature → boolean (granted or not).

    Used by admin.py to check if a specific admin action is allowed.
    Super Admin gets unrestricted access; others are restricted per role."""
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
