"""
admin_panel/auth.py
───────────────────
JWT token helpers and the IsAdminAuthenticated permission class.
Nothing here talks to views or business logic.
"""

from rest_framework import permissions
from rest_framework_simplejwt.tokens import Token
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework_simplejwt.settings import api_settings

from .models import Admin


# ─── Custom Token Classes ──────────────────────────────────────────────────────

class AdminRefreshToken(Token):
    """Custom refresh token for admins — no Django user_id required."""
    token_type = 'refresh'
    lifetime   = api_settings.REFRESH_TOKEN_LIFETIME


class AdminAccessToken(Token):
    """Custom access token for admins — no Django user_id required."""
    token_type = 'access'
    lifetime   = api_settings.ACCESS_TOKEN_LIFETIME


# ─── Token Factory ─────────────────────────────────────────────────────────────

def get_tokens_for_admin(admin):
    """Return a {'refresh': ..., 'access': ...} dict for the given Admin."""
    refresh = AdminRefreshToken()
    refresh['admin_id']     = str(admin.id)
    refresh['access_level'] = admin.access_level
    refresh['is_admin']     = True

    access = AdminAccessToken()
    access['admin_id']     = str(admin.id)
    access['access_level'] = admin.access_level
    access['is_admin']     = True

    return {
        'refresh': str(refresh),
        'access':  str(access),
    }


# ─── Permission Class ──────────────────────────────────────────────────────────

class IsAdminAuthenticated(permissions.BasePermission):
    """
    Validates the 'Authorization: Bearer <token>' header.
    On success, attaches the Admin instance to request.admin.
    """

    def has_permission(self, request, view):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False

        raw_token = auth_header.split(' ', 1)[1]
        try:
            from rest_framework_simplejwt.tokens import UntypedToken
            token = UntypedToken(raw_token)
            if not token.get('is_admin'):
                return False
            admin_id      = token.get('admin_id')
            request.admin = Admin.objects.get(pk=admin_id, deleted_at__isnull=True)
            return True
        except (TokenError, InvalidToken, Admin.DoesNotExist, Exception):
            return False