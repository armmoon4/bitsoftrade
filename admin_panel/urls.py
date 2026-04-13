from django.urls import path
from .views import (
    admin_login_view,
    admin_dashboard_stats_view,
    admin_user_list_view, admin_user_toggle_view, admin_user_delete_view,
    admin_list_view, admin_create_view, admin_manage_view,
    admin_rule_list_create_view, admin_rule_detail_view,
    admin_strategy_list_create_view, admin_strategy_detail_view,
    # CMS — public (no auth)
    public_review_list_view,
    public_pricing_list_view,
    # CMS — admin (protected)
    admin_review_list_create_view, admin_review_detail_view, admin_review_toggle_visibility_view,
    admin_pricing_list_create_view, admin_pricing_detail_view, admin_pricing_toggle_active_view,
    # Broadcast notifications
    admin_broadcast_list_create_view, admin_broadcast_delete_view,
)

# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC CMS endpoints — mount these under /api/cms/ in your root urls.py:
#
#   path('api/cms/', include('admin_panel.urls_public')),
#
# OR include them directly here and strip the prefix in root urls.py.
# They are listed at the bottom so it's easy to move them to a separate file.
# ─────────────────────────────────────────────────────────────────────────────

public_cms_urlpatterns = [
    # GET /api/cms/reviews/   → visible reviews only, no auth
    path('reviews/', public_review_list_view, name='public-review-list'),
    # GET /api/cms/pricing/   → active plans only, no auth
    path('pricing/', public_pricing_list_view, name='public-pricing-list'),
]

# Protected admin routes — mount under /api/admin/ in your root urls.py
urlpatterns = [
    # ── Auth ────────────────────────────────────────────────────────────────
    path('auth/login/', admin_login_view, name='admin-login'),

    # ── Dashboard ────────────────────────────────────────────────────────────
    path('dashboard/stats/', admin_dashboard_stats_view, name='admin-dashboard-stats'),

    # ── User management ──────────────────────────────────────────────────────
    path('users/', admin_user_list_view, name='admin-user-list'),
    path('users/<int:user_id>/toggle/', admin_user_toggle_view, name='admin-user-toggle'),
    path('users/<int:user_id>/delete/', admin_user_delete_view, name='admin-user-delete'),

    # ── Admin management ─────────────────────────────────────────────────────
    path('admins/', admin_list_view, name='admin-admin-list'),
    path('admins/create/', admin_create_view, name='admin-admin-create'),
    path('admins/<uuid:admin_id>/', admin_manage_view, name='admin-admin-manage'),

    # ── Rules ────────────────────────────────────────────────────────────────
    path('rules/', admin_rule_list_create_view, name='admin-rule-list'),
    path('rules/<uuid:pk>/', admin_rule_detail_view, name='admin-rule-detail'),

    # ── Strategies ───────────────────────────────────────────────────────────
    path('strategies/', admin_strategy_list_create_view, name='admin-strategy-list'),
    path('strategies/<uuid:pk>/', admin_strategy_detail_view, name='admin-strategy-detail'),

    # ── CMS: Reviews (admin — all reviews incl. hidden) ───────────────────────
    path('cms/reviews/', admin_review_list_create_view, name='admin-review-list'),
    path('cms/reviews/<uuid:pk>/', admin_review_detail_view, name='admin-review-detail'),
    path('cms/reviews/<uuid:pk>/toggle-visibility/', admin_review_toggle_visibility_view, name='admin-review-toggle'),

    # ── CMS: Pricing (admin — all plans incl. inactive) ──────────────────────
    path('cms/pricing/', admin_pricing_list_create_view, name='admin-pricing-list'),
    path('cms/pricing/<uuid:pk>/', admin_pricing_detail_view, name='admin-pricing-detail'),
    path('cms/pricing/<uuid:pk>/toggle-active/', admin_pricing_toggle_active_view, name='admin-pricing-toggle'),

    # ── Broadcast Notifications ───────────────────────────────────────────────
    path('notifications/broadcasts/', admin_broadcast_list_create_view, name='admin-broadcast-list'),
    path('notifications/broadcasts/<uuid:pk>/delete/', admin_broadcast_delete_view, name='admin-broadcast-delete'),
]