from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.models import Notification, NotificationSettings
from notifications.serializers import NotificationSerializer, NotificationSettingsSerializer


class NotificationListView(generics.ListAPIView):
    """
    GET /api/notifications/
    Returns all notifications for the authenticated user (paginated, newest first).

    Optional query params:
      ?unread=true          → only unread notifications
      ?type=rule_violated   → filter by notification_type
      ?severity=error       → filter by severity
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)

        unread = self.request.query_params.get('unread')
        if unread and unread.lower() == 'true':
            qs = qs.filter(is_read=False)

        notif_type = self.request.query_params.get('type')
        if notif_type:
            qs = qs.filter(notification_type=notif_type)

        severity = self.request.query_params.get('severity')
        if severity:
            qs = qs.filter(severity=severity)

        return qs


class UnreadNotificationsView(APIView):
    """
    GET /api/notifications/unread/
    Returns unread notifications + total unread count.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Notification.objects.filter(user=request.user, is_read=False)
        count = qs.count()
        serializer = NotificationSerializer(qs, many=True)
        return Response({
            'unread_count': count,
            'results': serializer.data,
        })


class MarkNotificationReadView(APIView):
    """
    PATCH /api/notifications/{id}/read/
    Marks a specific notification as read.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response(
                {'detail': 'Notification not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response(NotificationSerializer(notification).data)


class MarkAllReadView(APIView):
    """
    PATCH /api/notifications/read-all/
    Marks ALL notifications for the authenticated user as read.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        updated = Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True)
        return Response({'marked_read': updated})


class DeleteNotificationView(APIView):
    """
    DELETE /api/notifications/{id}/delete/
    Deletes a specific notification for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response(
                {'detail': 'Notification not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        notification.delete()
        return Response({'detail': 'Notification deleted.'}, status=status.HTTP_204_NO_CONTENT)


class NotificationSettingsView(APIView):
    """
    GET  /api/notifications/settings/ → get current settings
    PATCH /api/notifications/settings/ → update settings

    Settings row is auto-created with defaults on first GET.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        settings_obj, _ = NotificationSettings.objects.get_or_create(user=request.user)
        return Response(NotificationSettingsSerializer(settings_obj).data)

    def patch(self, request):
        settings_obj, _ = NotificationSettings.objects.get_or_create(user=request.user)
        serializer = NotificationSettingsSerializer(
            settings_obj, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ClearAllNotificationsView(APIView):
    """
    DELETE /api/notifications/clear-all/
    Permanently deletes ALL notifications for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        deleted_count, _ = Notification.objects.filter(user=request.user).delete()
        return Response({'deleted': deleted_count}, status=status.HTTP_200_OK)