from django.urls import path
from .views import RuleListCreateView, RuleDetailView, RuleTitleListView

urlpatterns = [
    path('', RuleListCreateView.as_view(), name='rule-list-create'),
    path('list/', RuleTitleListView.as_view(), name='rule-title-list'),
    path('<uuid:pk>/', RuleDetailView.as_view(), name='rule-detail'),
]
