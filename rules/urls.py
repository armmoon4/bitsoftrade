from django.urls import path
from .views import RuleListCreateView, RuleDetailView

urlpatterns = [
    path('', RuleListCreateView.as_view(), name='rule-list-create'),
    path('<uuid:pk>/', RuleDetailView.as_view(), name='rule-detail'),
]
