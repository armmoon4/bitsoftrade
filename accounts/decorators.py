from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required


def role_required(role):
    """
    Decorator to check if user has the required role
    Usage: @role_required('admin') or @role_required('user')
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped_view(request, *args, **kwargs):
            if request.user.role != role:
                raise PermissionDenied(f"You must be a {role} to access this page.")
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def admin_required(view_func):
    """Shorthand decorator for admin-only views"""
    return role_required('admin')(view_func)


def user_required(view_func):
    """Shorthand decorator for regular user views"""
    return role_required('user')(view_func)
