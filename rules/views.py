from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Rule
from .serializers import RuleSerializer, RuleTitleSerializer


class RuleListCreateView(generics.ListCreateAPIView):
    """
    GET /api/rules/ — list current user's rules + admin defaults.
      Use ?is_active=true to see only active rules.
      Use ?is_active=false to see only inactive rules.
      Omit the parameter to see ALL non-deleted rules.
    POST /api/rules/ — create a user custom rule.
    """
    serializer_class = RuleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from django.db.models import Q
        
        # Base query: get all non-deleted rules for this user or admin
        qs = Rule.objects.filter(
            deleted_at__isnull=True
        ).filter(
            Q(is_admin_defined=True) | Q(user=self.request.user)
        )

        # Check for 'is_active' in the URL query parameters
        is_active_param = self.request.query_params.get('is_active')
        
        if is_active_param is not None:
            # Convert string "true"/"false" from URL into a boolean
            is_active_bool = is_active_param.lower() in ['true', '1', 't', 'y', 'yes']
            qs = qs.filter(is_active=is_active_bool)
        else:
            pass

        #  Return ordered queryset
        return qs.order_by('-is_admin_defined', 'category', 'rule_name')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, is_admin_defined=False)


class RuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PUT / DELETE /api/rules/<id>/"""
    serializer_class = RuleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Rule.objects.filter(user=self.request.user, deleted_at__isnull=True)

    def destroy(self, request, *args, **kwargs):
        rule = self.get_object()
        if rule.is_admin_defined:
            return Response({'error': 'Admin-defined rules cannot be deleted.'},
                            status=status.HTTP_403_FORBIDDEN)
        rule.deleted_at = timezone.now()
        rule.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RuleTitleListView(generics.ListAPIView):
    """
    GET /api/rules/titles/ — list only IDs and titles of current user's rules + admin defaults.
    """
    serializer_class = RuleTitleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from django.db.models import Q
        
        # Base query: get all non-deleted rules for this user or admin
        qs = Rule.objects.filter(
            deleted_at__isnull=True
        ).filter(
            Q(is_admin_defined=True) | Q(user=self.request.user)
        )

        # Optional: Keep the 'is_active' filter if you need it for the dropdowns
        is_active_param = self.request.query_params.get('is_active')
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ['true', '1', 't', 'y', 'yes']
            qs = qs.filter(is_active=is_active_bool)

        return qs.order_by('-is_admin_defined', 'category', 'rule_name')