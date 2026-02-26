from django.urls import path
from tradelog.views import TradeListCreateView, TradeDetailView, TradeImportView

urlpatterns = [
    path('trades/', TradeListCreateView.as_view(), name='trade-list-create'),
    path('trades/import/', TradeImportView.as_view(), name='trade-import'),
    path('trades/<uuid:pk>/', TradeDetailView.as_view(), name='trade-detail'),
]                                                     