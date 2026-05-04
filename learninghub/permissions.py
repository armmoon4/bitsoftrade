from rest_framework import permissions
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.contrib.auth import get_user_model
from admin_panel.models import Admin

User = get_user_model()


class IsAdminOrUserReadOnly(permissions.BasePermission):
    """
    GET  → user JWT OR admin JWT
    POST/PUT/PATCH/DELETE → admin JWT only
    No subscription check — open to all active users.
    """
    def has_permission(self, request, view):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False
        raw_token = auth_header.split(' ', 1)[1]
        try:
            token = UntypedToken(raw_token)
            if token.get('is_admin'):
                request.admin = Admin.objects.get(
                    pk=token.get('admin_id'), deleted_at__isnull=True
                )
                return True
            if request.method in permissions.SAFE_METHODS:
                user_id = token.get('user_id')
                if user_id:
                    request.user = User.objects.get(pk=user_id, is_active=True)
                    return True
            return False
        except (TokenError, InvalidToken, Admin.DoesNotExist, User.DoesNotExist, Exception):
            return False


class IsAdminOrLearningSubscriber(permissions.BasePermission):
    """
    GET  → user JWT with active learning/both subscription OR admin JWT
    POST/PUT/PATCH/DELETE → admin JWT only
    """
    message = {
        'error': 'subscription_required',
        'detail': 'Active Learning or Both plan required.'
    }

    def has_permission(self, request, view):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False
        raw_token = auth_header.split(' ', 1)[1]
        try:
            token = UntypedToken(raw_token)
            if token.get('is_admin'):
                request.admin = Admin.objects.get(
                    pk=token.get('admin_id'), deleted_at__isnull=True
                )
                return True
            if request.method in permissions.SAFE_METHODS:
                user_id = token.get('user_id')
                if user_id:
                    user = User.objects.get(pk=user_id, is_active=True)
                    request.user = user
                    if not user.has_learning_access:  #  subscription check
                        return False
                    return True
            return False
        except (TokenError, InvalidToken, Admin.DoesNotExist, User.DoesNotExist, Exception):
            return False


class IsAdminOrAuthenticatedUser(permissions.BasePermission):
    """
    All HTTP methods → valid user JWT OR admin JWT.
    Regular users can also POST/PUT/DELETE here.
    No subscription check.
    """
    def has_permission(self, request, view):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False
        raw_token = auth_header.split(' ', 1)[1]
        try:
            token = UntypedToken(raw_token)
            if token.get('is_admin'):
                request.admin = Admin.objects.get(
                    pk=token.get('admin_id'), deleted_at__isnull=True
                )
                return True
            user_id = token.get('user_id')
            if user_id:
                request.user = User.objects.get(pk=user_id, is_active=True)
                return True
            return False
        except (TokenError, InvalidToken, Admin.DoesNotExist, User.DoesNotExist, Exception):
            return False


class IsAdminOrLearningSubscriberFull(permissions.BasePermission):
    """
    All HTTP methods → user JWT with active learning/both subscription OR admin JWT.
    Use this for UserCourseProgress — users need subscription to POST too.
    """
    message = {
        'error': 'subscription_required',
        'detail': 'Active Learning or Both plan required.'
    }

    def has_permission(self, request, view):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False
        raw_token = auth_header.split(' ', 1)[1]
        try:
            token = UntypedToken(raw_token)
            if token.get('is_admin'):
                request.admin = Admin.objects.get(
                    pk=token.get('admin_id'), deleted_at__isnull=True
                )
                return True
            user_id = token.get('user_id')
            if user_id:
                user = User.objects.get(pk=user_id, is_active=True)
                request.user = user
                if not user.has_learning_access:  #  subscription check
                    return False
                return True
            return False
        except (TokenError, InvalidToken, Admin.DoesNotExist, User.DoesNotExist, Exception):
            return False