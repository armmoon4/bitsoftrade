from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Rule
from .serializers import RuleSerializer


class RuleListCreateView(generics.ListCreateAPIView):
    """GET /api/rules/ — list current user's rules + admin defaults.
       POST /api/rules/ — create a user custom rule."""
    serializer_class = RuleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from django.db.models import Q
        return Rule.objects.filter(
            deleted_at__isnull=True,
            is_active=True
        ).filter(
            Q(is_admin_defined=True) | Q(user=self.request.user)
        ).order_by('-is_admin_defined', 'category', 'rule_name')

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
