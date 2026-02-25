from functools import wraps
from rest_framework.response import Response
from rest_framework import status


def require_tool_subscription(view_func):
    """Block access unless user has tool or both subscription."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.has_tool_access:
            return Response(
                {'error': 'subscription_required', 'detail': 'Active Tool or Both plan required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def require_learning_subscription(view_func):
    """Block access unless user has learning or both subscription."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.has_learning_access:
            return Response(
                {'error': 'subscription_required', 'detail': 'Active Learning or Both plan required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return view_func(request, *args, **kwargs)
    return wrapper