from rest_framework import permissions

class HasToolSubscription(permissions.BasePermission):
    """
    Allows access only to authenticated users with an active Tool or Both subscription.
    """
    message = {
        'error': 'subscription_required',
        'detail': 'Active Tool or Both plan required.'
    }

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.has_tool_access

class HasLearningSubscription(permissions.BasePermission):
    """
    Allows access only to authenticated users with an active Learning or Both subscription.
    """
    message = {
        'error': 'subscription_required',
        'detail': 'Active Learning or Both plan required.'
    }

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.has_learning_access
