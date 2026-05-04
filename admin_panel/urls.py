from django.urls import path
from .views import (
    admin_login_view,
    admin_me_view,
    admin_dashboard_stats_view,
    admin_payments_view,
    admin_user_list_view,
    admin_user_subscription_view, admin_user_toggle_view, admin_user_delete_view,
    admin_list_view, admin_create_view, admin_manage_view,
    admin_rule_list_create_view, admin_rule_detail_view,
    admin_strategy_list_create_view, admin_strategy_detail_view,
    admin_mistake_list_create_view, admin_mistake_detail_view,
    # CMS — public (no auth)
    public_review_list_view,
    public_pricing_list_view,
    public_learning_hub_view,
    # CMS — admin (protected)
    admin_review_list_create_view, admin_review_detail_view, admin_review_toggle_visibility_view,
    admin_pricing_list_create_view, admin_pricing_detail_view, admin_pricing_toggle_active_view,
    # Broadcast notifications
    admin_broadcast_list_create_view, admin_broadcast_delete_view,
    # CMS — Learning Hub (admin)
    admin_learning_module_list_create_view,
    admin_learning_module_detail_view,
    admin_learning_module_toggle_visibility_view,
    admin_learning_topic_list_create_view,
    admin_learning_topic_bulk_create_view,
    admin_learning_topic_detail_view,
    admin_learning_topic_toggle_visibility_view,
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
    # GET /api/cms/reviews/        → visible reviews only, no auth
    path('reviews/', public_review_list_view, name='public-review-list'),
    # GET /api/cms/pricing/        → active plans only, no auth
    path('pricing/', public_pricing_list_view, name='public-pricing-list'),
    # GET /api/cms/learning-hub/   → visible modules + visible topics, no auth
    path('learning-hub/', public_learning_hub_view, name='public-learning-hub'),
]

# Protected admin routes — mount under /api/admin/ in your root urls.py
urlpatterns = [
    # ── Auth ─────────────────────────────────────────────────────────────────
    path('auth/login/', admin_login_view, name='admin-login'),

    # ── Profile ───────────────────────────────────────────────────────────────
    path('me/', admin_me_view, name='admin-me'),

    # ── Dashboard ─────────────────────────────────────────────────────────────
    path('dashboard/stats/', admin_dashboard_stats_view, name='admin-dashboard-stats'),

    # ── User management ───────────────────────────────────────────────────────
    path('users/', admin_user_list_view, name='admin-user-list'),
    path('users/<int:user_id>/toggle/', admin_user_toggle_view, name='admin-user-toggle'),
    path('users/<int:user_id>/delete/', admin_user_delete_view, name='admin-user-delete'),
    # ── Users subscription (admin) ────────────────────────────────────
    path('users/<int:user_id>/subscription/', admin_user_subscription_view, name='admin-user-subscription'),

    # ── Admin management ──────────────────────────────────────────────────────
    path('admins/', admin_list_view, name='admin-admin-list'),
    path('admins/create/', admin_create_view, name='admin-admin-create'),
    path('admins/<uuid:admin_id>/', admin_manage_view, name='admin-admin-manage'),

    # ── Rules ─────────────────────────────────────────────────────────────────
    path('rules/', admin_rule_list_create_view, name='admin-rule-list'),
    path('rules/<uuid:pk>/', admin_rule_detail_view, name='admin-rule-detail'),

    # ── Strategies ────────────────────────────────────────────────────────────
    path('strategies/', admin_strategy_list_create_view, name='admin-strategy-list'),
    path('strategies/<uuid:pk>/', admin_strategy_detail_view, name='admin-strategy-detail'),

    # ── Mistakes ──────────────────────────────────────────────────────────────
    path('mistakes/', admin_mistake_list_create_view, name='admin-mistake-list'),
    path('mistakes/<uuid:pk>/', admin_mistake_detail_view, name='admin-mistake-detail'),

    # ── CMS: Reviews (admin — all reviews incl. hidden) ───────────────────────
    path('cms/reviews/', admin_review_list_create_view, name='admin-review-list'),
    path('cms/reviews/<uuid:pk>/', admin_review_detail_view, name='admin-review-detail'),
    path('cms/reviews/<uuid:pk>/toggle-visibility/', admin_review_toggle_visibility_view, name='admin-review-toggle'),

    # ── CMS: Pricing (admin — all plans incl. inactive) ───────────────────────
    path('cms/pricing/', admin_pricing_list_create_view, name='admin-pricing-list'),
    path('cms/pricing/<uuid:pk>/', admin_pricing_detail_view, name='admin-pricing-detail'),
    path('cms/pricing/<uuid:pk>/toggle-active/', admin_pricing_toggle_active_view, name='admin-pricing-toggle'),

    # ── Broadcast Notifications ────────────────────────────────────────────────
    path('notifications/broadcasts/', admin_broadcast_list_create_view, name='admin-broadcast-list'),
    path('notifications/broadcasts/<uuid:pk>/delete/', admin_broadcast_delete_view, name='admin-broadcast-delete'),

    # ── CMS: Learning Hub — Modules (admin — all modules incl. hidden) ─────────
    path('cms/learning-hub/modules/', admin_learning_module_list_create_view, name='admin-learning-module-list'),
    path('cms/learning-hub/modules/<uuid:pk>/', admin_learning_module_detail_view, name='admin-learning-module-detail'),
    path('cms/learning-hub/modules/<uuid:pk>/toggle-visibility/', admin_learning_module_toggle_visibility_view, name='admin-learning-module-toggle'),

    # ── CMS: Learning Hub — Topics (admin) ────────────────────────────────────
    path('cms/learning-hub/modules/<uuid:module_pk>/topics/', admin_learning_topic_list_create_view, name='admin-learning-topic-list'),
    path('cms/learning-hub/modules/<uuid:module_pk>/topics/bulk/', admin_learning_topic_bulk_create_view, name='admin-learning-topic-bulk-create'),
    path('cms/learning-hub/modules/<uuid:module_pk>/topics/<uuid:pk>/', admin_learning_topic_detail_view, name='admin-learning-topic-detail'),
    path('cms/learning-hub/modules/<uuid:module_pk>/topics/<uuid:pk>/toggle-visibility/', admin_learning_topic_toggle_visibility_view, name='admin-learning-topic-toggle'),

    # ── Payments (admin) ────────────────────────────────────
    path('payments/', admin_payments_view, name='admin-payments'),
]