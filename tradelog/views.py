from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from tradelog.models import Trade
from tradelog.serializers import TradeManagementSerializer
from .pagination import StandardResultsSetPagination
from decimal import Decimal


class TradeListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/trades/       → List all trades for the authenticated user
    POST /api/trades/       → Create a new trade
    """
    serializer_class = TradeManagementSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return Trade.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        trade = serializer.save(user=self.request.user)
        self._calculate_pnl(trade)
        trade.save(update_fields=['total_pnl'])

    def _calculate_pnl(self, trade):
        """Auto-calculate P&L safely without triggering extra save calls."""

        if not trade.exit_price:
            trade.total_pnl = None
            return

        qty = trade.quantity or Decimal('0')
        entry = trade.entry_price or Decimal('0')
        exit_p = trade.exit_price or Decimal('0')
        fees = trade.fees or Decimal('0')
        leverage = trade.leverage or Decimal('1')

        if trade.direction == 'long':
            raw_pnl = (exit_p - entry) * qty * leverage
        else:  # short
            raw_pnl = (entry - exit_p) * qty * leverage

        trade.total_pnl = raw_pnl - fees



class TradeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/trades/<id>/   → Retrieve a trade
    PUT    /api/trades/<id>/   → Full update
    PATCH  /api/trades/<id>/   → Partial update
    DELETE /api/trades/<id>/   → Delete a trade
    """
    serializer_class = TradeManagementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only access their own trades
        return Trade.objects.filter(user=self.request.user)

    def get_object(self):
        obj = get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])
        return obj

    def perform_update(self, serializer):
        trade = serializer.save()
        self._recalculate_pnl(trade)

    def _recalculate_pnl(self, trade):
        """Recalculate P&L on every update if exit_price is set."""
        if trade.exit_price is not None:
            qty = trade.quantity
            entry = trade.entry_price
            exit_p = trade.exit_price
            fees = trade.fees or Decimal('0')
            leverage = trade.leverage or Decimal('1')

            if trade.direction == 'long':
                raw_pnl = (exit_p - entry) * qty * leverage
            else:
                raw_pnl = (entry - exit_p) * qty * leverage

            trade.total_pnl = raw_pnl - fees
        else:
            trade.total_pnl = None  # Reset P&L for open trades

        trade.save(update_fields=['total_pnl'])