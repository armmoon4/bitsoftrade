from django.urls import path
from notifications.views import (
    NotificationListView,
    UnreadNotificationsView,
    MarkNotificationReadView,
    MarkAllReadView,
    DeleteNotificationView,
)

urlpatterns = [
    # List all notifications (paginated) — supports ?unread=true, ?type=, ?severity=
    path('', NotificationListView.as_view(), name='notification-list'),

    # Only unread notifications + count
    path('unread/', UnreadNotificationsView.as_view(), name='notification-unread'),

    # Mark all notifications as read
    path('read-all/', MarkAllReadView.as_view(), name='notification-read-all'),

    # Mark a single notification as read
    path('<uuid:pk>/read/', MarkNotificationReadView.as_view(), name='notification-read'),

    # Delete a single notification
    path('<uuid:pk>/delete/', DeleteNotificationView.as_view(), name='notification-delete'),
]
