from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q
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
        qs = Rule.objects.filter(
            deleted_at__isnull=True
        ).filter(
            Q(is_admin_defined=True) | Q(user=self.request.user)
        )

        is_active_param = self.request.query_params.get('is_active')
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ['true', '1', 't', 'y', 'yes']
            qs = qs.filter(is_active=is_active_bool)

        return qs.order_by('-is_admin_defined', 'category', 'rule_name')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, is_admin_defined=False)


class RuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PUT / PATCH / DELETE /api/rules/<id>/"""
    serializer_class = RuleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        #  also include admin-defined rules, not just user's own rules
        return Rule.objects.filter(
            deleted_at__isnull=True
        ).filter(
            Q(is_admin_defined=True) | Q(user=self.request.user)
        )

    def update(self, request, *args, **kwargs):
        rule = self.get_object()
        # Block users from editing admin-defined rules
        if rule.is_admin_defined:
            return Response(
                {'error': 'Admin-defined rules cannot be modified.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        rule = self.get_object()
        # Block users from deleting admin-defined rules
        if rule.is_admin_defined:
            return Response(
                {'error': 'Admin-defined rules cannot be deleted.'},
                status=status.HTTP_403_FORBIDDEN
            )
        rule.deleted_at = timezone.now()
        rule.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RuleTitleListView(generics.ListAPIView):
    """
    GET /api/rules/list/ — list only IDs and titles of current user's rules + admin defaults.
    """
    serializer_class = RuleTitleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Rule.objects.filter(
            deleted_at__isnull=True
        ).filter(
            Q(is_admin_defined=True) | Q(user=self.request.user)
        )

        is_active_param = self.request.query_params.get('is_active')
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ['true', '1', 't', 'y', 'yes']
            qs = qs.filter(is_active=is_active_bool)

        return qs.order_by('-is_admin_defined', 'category', 'rule_name')