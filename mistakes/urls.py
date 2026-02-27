from django.urls import path
from .views import (
    MistakeListCreateView, MistakeDetailView,
    TradeMistakeListCreateView, mistakes_analytics_view
)

urlpatterns = [
    path('', MistakeListCreateView.as_view(), name='mistake-list-create'),
    path('<uuid:pk>/', MistakeDetailView.as_view(), name='mistake-detail'),
    path('trade-links/', TradeMistakeListCreateView.as_view(), name='trade-mistake-list'),
    path('analytics/', mistakes_analytics_view, name='mistake-analytics'),
]
