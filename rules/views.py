from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q
from .models import Rule
from .serializers import RuleSerializer, RuleTitleSerializer, SystemRuleUpdateSerializer


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
        return Rule.objects.filter(
            deleted_at__isnull=True
        ).filter(
            Q(is_admin_defined=True) | Q(user=self.request.user)
        )

    def update(self, request, *args, **kwargs):
        rule = self.get_object()
        if rule.is_admin_defined:
            return Response(
                {'error': 'Admin-defined rules cannot be modified.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if rule.is_system_rule:
            return Response(
                {'error': 'System rules can only be updated via PATCH /api/rules/system/<id>/.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        rule = self.get_object()
        if rule.is_admin_defined:
            return Response(
                {'error': 'Admin-defined rules cannot be deleted.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if rule.is_system_rule:
            return Response(
                {'error': 'System rules cannot be deleted.'},
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


# ── System Rules ──────────────────────────────────────────────────────────────

class SystemRuleListView(generics.ListAPIView):
    """
    GET /api/rules/system/

    List all system rules that belong to the authenticated user.
    Supports ?is_active=true/false filter.
    """
    serializer_class = SystemRuleUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Rule.objects.filter(
            user=self.request.user,
            is_system_rule=True,
            deleted_at__isnull=True,
        )

        is_active_param = self.request.query_params.get('is_active')
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ['true', '1', 't', 'y', 'yes']
            qs = qs.filter(is_active=is_active_bool)

        return qs.order_by('created_at')


class SystemRuleUpdateView(APIView):
    """
    GET    /api/rules/system/<uuid:pk>/  — retrieve a single system rule.
    PATCH  /api/rules/system/<uuid:pk>/  — update threshold and/or is_active.

    Allowed PATCH fields
    --------------------
    * trigger_condition  — must keep the same condition key; only the numeric
                           threshold may change.
                           Example: {"trigger_condition": {"maxLoss": 3000}}
    * is_active          — boolean toggle.

    Forbidden operations
    --------------------
    * PUT / DELETE — always 405 Method Not Allowed.
    * Changing rule_name, category, rule_type, trigger_scope, action, etc.
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get_rule(self, pk, user):
        return get_object_or_404(
            Rule,
            pk=pk,
            user=user,
            is_system_rule=True,
            deleted_at__isnull=True,
        )

    def get(self, request, pk, *args, **kwargs):
        rule = self._get_rule(pk, request.user)
        serializer = SystemRuleUpdateSerializer(rule)
        return Response(serializer.data)

    def patch(self, request, pk, *args, **kwargs):
        rule = self._get_rule(pk, request.user)
        serializer = SystemRuleUpdateSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def put(self, request, pk, *args, **kwargs):
        return Response(
            {'error': 'Full replacement of system rules is not allowed. Use PATCH.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def delete(self, request, pk, *args, **kwargs):
        return Response(
            {'error': 'System rules cannot be deleted.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )