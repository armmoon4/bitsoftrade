from django.urls import path
from .views import (
    StrategyListCreateView, StrategyDetailView,
    community_strategies_view, template_strategies_view, add_to_mine_view
)

urlpatterns = [
    path('', StrategyListCreateView.as_view(), name='strategy-list-create'),
    path('community/', community_strategies_view, name='strategy-community'),
    path('templates/', template_strategies_view, name='strategy-templates'),
    path('<uuid:pk>/', StrategyDetailView.as_view(), name='strategy-detail'),
    path('<uuid:pk>/add-to-mine/', add_to_mine_view, name='strategy-add-to-mine'),
]
