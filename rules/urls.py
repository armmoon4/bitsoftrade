from django.urls import path
from .views import (
    RuleListCreateView,
    RuleDetailView,
    RuleTitleListView,
    SystemRuleListView,
    SystemRuleUpdateView,
    TradeRuleListCreateView,
    rule_evaluate_debug,
)

urlpatterns = [
    # ── Standard rules ────────────────────────────────────────────────────────
    path('', RuleListCreateView.as_view(), name='rule-list-create'),
    path('list/', RuleTitleListView.as_view(), name='rule-title-list'),
    path('<uuid:pk>/', RuleDetailView.as_view(), name='rule-detail'),

    # ── System rules ──────────────────────────────────────────────────────────
    path('system/', SystemRuleListView.as_view(), name='system-rule-list'),
    path('system/<uuid:pk>/', SystemRuleUpdateView.as_view(), name='system-rule-detail'),

    path('trade-links/', TradeRuleListCreateView.as_view(), name='trade-rule-list'),

    # ── Debug / diagnostic ────────────────────────────────────────────────────
    path('evaluate-debug/', rule_evaluate_debug, name='rule-evaluate-debug'),
]