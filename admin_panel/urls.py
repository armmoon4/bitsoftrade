from django.urls import path
from .views import (
    admin_login_view,
    admin_dashboard_stats_view,
    admin_user_list_view, admin_user_toggle_view, admin_user_delete_view,
    admin_list_view, admin_create_view, admin_manage_view,
    admin_rule_list_create_view, admin_rule_detail_view,
)

urlpatterns = [
    # Auth
    path('auth/login/', admin_login_view, name='admin-login'),
    # Dashboard
    path('dashboard/stats/', admin_dashboard_stats_view, name='admin-dashboard-stats'),
    # User management
    path('users/', admin_user_list_view, name='admin-user-list'),
    path('users/<uuid:user_id>/toggle/', admin_user_toggle_view, name='admin-user-toggle'),
    path('users/<uuid:user_id>/delete/', admin_user_delete_view, name='admin-user-delete'),
    # Admin management
    path('admins/', admin_list_view, name='admin-admin-list'),
    path('admins/create/', admin_create_view, name='admin-admin-create'),
    path('admins/<uuid:admin_id>/', admin_manage_view, name='admin-admin-manage'),
    # Rules
    path('rules/', admin_rule_list_create_view, name='admin-rule-list'),
    path('rules/<uuid:pk>/', admin_rule_detail_view, name='admin-rule-detail'),
]
