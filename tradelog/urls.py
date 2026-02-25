from django.urls import path
from tradelog.views import TradeListCreateView, TradeDetailView, trade_import_view

urlpatterns = [
    path('trades/', TradeListCreateView.as_view(), name='trade-list-create'),
    path('trades/import/', trade_import_view, name='trade-import'),
    path('trades/<uuid:pk>/', TradeDetailView.as_view(), name='trade-detail'),
]