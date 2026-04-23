from django.urls import path
from tradelog.views import (
    TradeListCreateView,
    TradeDetailView,
    TradeImportView,
    TradeSymbolListView,
    ImageUploadView,
    TradeScreenshotView,
    TradeBulkDeleteView,
)
from tradelog.analytics_views import (
    TradeDistributionView,
    TradeCalendarView,
)

urlpatterns = [
    # ── Trade CRUD (list/create)
    path('trades/', TradeListCreateView.as_view(), name='trade-list-create'),

    # ── Static paths FIRST — before <uuid:pk>
    path('trades/import/', TradeImportView.as_view(), name='trade-import'),
    path('trades/symbols/', TradeSymbolListView.as_view(), name='trade-symbols'),
    path('trades/bulk-delete/', TradeBulkDeleteView.as_view(), name='trade-bulk-delete'),
    path('trades/distribution/', TradeDistributionView.as_view(), name='trade-distribution'),
    path('trades/calendar/', TradeCalendarView.as_view(), name='trade-calendar'),

    # ── Dynamic paths AFTER — <uuid:pk> won't swallow static segments above
    path('trades/<uuid:pk>/', TradeDetailView.as_view(), name='trade-detail'),
    path('trades/<uuid:pk>/screenshots/', TradeScreenshotView.as_view(), name='trade-screenshots'),

    # ── Standalone image upload
    path('upload-screenshot/', ImageUploadView.as_view(), name='upload-screenshot'),
]