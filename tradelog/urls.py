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

urlpatterns = [
    # ── Trade CRUD
    path('trades/', TradeListCreateView.as_view(), name='trade-list-create'),
    path('trades/<uuid:pk>/', TradeDetailView.as_view(), name='trade-detail'),

    # ── Import
    path('trades/import/', TradeImportView.as_view(), name='trade-import'),

    # ── Symbols (dropdown/autocomplete)
    path('trades/symbols/', TradeSymbolListView.as_view(), name='trade-symbols'),

    # ── Bulk delete  (soft-delete many at once)
    path('trades/bulk-delete/', TradeBulkDeleteView.as_view(), name='trade-bulk-delete'),

    # ── Standalone image upload (returns URLs, caller attaches them to a trade)
    path('upload-screenshot/', ImageUploadView.as_view(), name='upload-screenshot'),

    # ── Per-trade screenshot management (GET / POST / DELETE)
    path('trades/<uuid:pk>/screenshots/', TradeScreenshotView.as_view(), name='trade-screenshots'),
]