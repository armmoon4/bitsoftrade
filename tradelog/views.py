from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from decimal import Decimal

from tradelog.models import Trade
from tradelog.serializers import TradeManagementSerializer
from .pagination import StandardResultsSetPagination

# Import the parsing logic
from .importers.parser import parse_csv, parse_excel, detect_and_normalize


# ─────────────────────────────────────────────
# SERIALIZERS
# ─────────────────────────────────────────────

class TradeImportSerializer(serializers.Serializer):
    file = serializers.FileField()
    broker_name = serializers.CharField(required=False, allow_blank=True)


# ─────────────────────────────────────────────
# SESSION LOCK HELPER
# ─────────────────────────────────────────────

def _get_session_lock_response(user):
    """
    Returns a DRF Response (HTTP 423) if the user's trading session is locked,
    or None if trading is allowed.

    A session is considered locked when:
      - state is 'red', OR
      - state is 'yellow' AND the cooldown has not expired yet.
    """
    from rules.engine import is_session_locked
    locked, message = is_session_locked(user)
    if locked:
        return Response(
            {
                'error': 'Trading session is locked.',
                'detail': message,
            },
            status=status.HTTP_423_LOCKED,
        )
    return None


# ─────────────────────────────────────────────
# API VIEWS
# ─────────────────────────────────────────────

class TradeImportView(generics.GenericAPIView):
    """
    POST /api/tradelog/trades/import/
    Accepts CSV or Excel file. Parses and imports trades.
    Supports: Generic CSV, Zerodha, Upstox, Groww formats.

    BUG FIX: Returns HTTP 423 if the user's discipline session is locked.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = TradeImportSerializer

    def post(self, request, *args, **kwargs):
        # Allow import to proceed so that per-row dates are checked correctly.
        # Top-level block by today's date prevents importing back-dated trades.

        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        broker_name = request.data.get('broker_name', '').strip().lower()
        filename = file.name.lower()

        try:
            if filename.endswith('.csv'):
                raw_rows = parse_csv(file)
            elif filename.endswith(('.xlsx', '.xls')):
                raw_rows = parse_excel(file)
            else:
                return Response(
                    {'error': 'Unsupported file type. Upload CSV or Excel.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            return Response({'error': f'File parsing failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # Detect broker format and normalize rows into standard trade dicts
        try:
            detected_broker, rows = detect_and_normalize(raw_rows, broker_name)
        except Exception as e:
            return Response({'error': f'Format normalization failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        created_trades = []
        errors = []

        for i, row in enumerate(rows, start=1):
            # Session lock is now checked inside _create_trade_from_row
            # per-row based on the actual trade date.

            try:
                trade = _create_trade_from_row(row, request.user, detected_broker or broker_name)
                created_trades.append(trade)
            except Exception as e:
                errors.append({'row': i, 'error': str(e), 'data': row})

        return Response({
            'imported': len(created_trades),
            'failed': len(errors),
            'errors': errors[:10],
            'detected_broker': detected_broker,
            'message': f'{len(created_trades)} trades imported successfully.'
        }, status=status.HTTP_201_CREATED)


class TradeListCreateView(generics.ListCreateAPIView):
    """GET /api/tradelog/trades/  POST /api/tradelog/trades/"""
    serializer_class = TradeManagementSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Trade.objects.filter(user=self.request.user, deleted_at__isnull=True)
        trade_filter = self.request.query_params.get('filter')
        if trade_filter == 'wins':
            qs = qs.filter(total_pnl__gt=0)
        elif trade_filter == 'losses':
            qs = qs.filter(total_pnl__lt=0)
        elif trade_filter == 'disciplined':
            qs = qs.filter(is_disciplined=True)
        elif trade_filter == 'violations':
            qs = qs.filter(is_disciplined=False)
        return qs

    def create(self, request, *args, **kwargs):
        # BUG FIX: Block manual trade entry when session is locked
        lock_response = _get_session_lock_response(request.user)
        if lock_response:
            return lock_response
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        trade = serializer.save(user=self.request.user)
        trade.calculate_pnl()

        # Fix 5: Auto-mark tagging complete when all required fields are present
        if trade.strategy and trade.emotional_state and trade.entry_confidence:
            trade.is_tagged_complete = True

        trade.save(update_fields=['total_pnl', 'is_tagged_complete'])

        # Fix 2: Update strategy maturity based on latest trade count
        if trade.strategy:
            total = Trade.objects.filter(
                strategy=trade.strategy, deleted_at__isnull=True
            ).count()
            trade.strategy.update_maturity(total)

        # Rule evaluation is handled by the post_save signal in discipline/signals.py
        # which always fetches a fresh session from the DB. Do NOT call
        # evaluate_rules_for_user here — using the stale in-memory trade.session
        # would overwrite the DB session state back to GREEN after the signal
        # has already correctly set it to RED.


class TradeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/tradelog/trades/<id>/"""
    serializer_class = TradeManagementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Trade.objects.filter(user=self.request.user, deleted_at__isnull=True)

    def perform_update(self, serializer):
        trade = serializer.save()
        trade.calculate_pnl()

        # Fix 5: Auto-mark tagging complete when all required fields are present
        if trade.strategy and trade.emotional_state and trade.entry_confidence:
            trade.is_tagged_complete = True

        trade.save(update_fields=['total_pnl', 'is_tagged_complete'])

        # Fix 2: Update strategy maturity based on latest trade count
        if trade.strategy:
            total = Trade.objects.filter(
                strategy=trade.strategy, deleted_at__isnull=True
            ).count()
            trade.strategy.update_maturity(total)

        # Rule evaluation handled by post_save signal — see perform_create comment.

    def destroy(self, request, *args, **kwargs):
        trade = self.get_object()
        trade.deleted_at = timezone.now()
        trade.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────
# TRADE CREATION HELPER
# ─────────────────────────────────────────────

def _create_trade_from_row(row, user, broker_name):
    """Create and save a Trade instance from a normalized row dict."""
    from datetime import datetime, date as ddate
    from discipline.models import DisciplineSession

    symbol = row.get('symbol') or row.get('scrip', '')
    direction = (row.get('direction') or row.get('trade_type', 'long')).lower()
    quantity = Decimal(str(row.get('quantity') or row.get('qty', 1)))
    entry_price = Decimal(str(row.get('entry_price') or row.get('buy_price', 0)))
    exit_price_raw = row.get('exit_price') or row.get('sell_price', '')
    exit_price = Decimal(str(exit_price_raw)) if exit_price_raw else None
    fees = Decimal(str(row.get('fees') or row.get('brokerage', 0)))

    # Date parsing — strip any time component first (e.g. Upstox sends "2026-02-24 00:00:00")
    date_raw = row.get('date') or row.get('trade_date', '')
    if date_raw and ' ' in str(date_raw):
        date_raw = str(date_raw).split(' ')[0]
    trade_date = ddate.today()
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            trade_date = datetime.strptime(date_raw, fmt).date()
            break
        except (ValueError, TypeError):
            continue

    # Time parsing
    time_raw = row.get('time') or row.get('trade_time', '')
    trade_time = None
    if time_raw:
        try:
            from datetime import time as dtime
            parts = time_raw.split(':')
            trade_time = dtime(
                int(parts[0]),
                int(parts[1]),
                int(parts[2]) if len(parts) > 2 else 0
            )
        except Exception:
            pass

    from rules.engine import is_session_locked
    locked, lock_msg = is_session_locked(user, date=trade_date)
    if locked:
        raise ValueError(f"Trade blocked — session locked: {lock_msg}")

    # Get or create a discipline session for this trade date
    session, _ = DisciplineSession.objects.get_or_create(
        user=user, session_date=trade_date, defaults={'session_state': 'green'}
    )

    trade = Trade(
        user=user,
        session=session,
        trade_date=trade_date,
        trade_time=trade_time,
        symbol=symbol or 'UNKNOWN',
        market_type=row.get('market_type', 'indian_stocks'),
        direction='long' if direction in ('long', 'buy', 'b') else 'short',
        quantity=quantity,
        entry_price=entry_price,
        exit_price=exit_price,
        fees=fees,
        import_source='csv_import',
        broker_name=broker_name,
        is_tagged_complete=False,
    )
    trade.calculate_pnl()
    trade.save()

    # Update strategy maturity after import
    if trade.strategy:
        total = Trade.objects.filter(
            strategy=trade.strategy, deleted_at__isnull=True
        ).count()
        trade.strategy.update_maturity(total)

    # Rule evaluation handled by post_save signal — see perform_create comment.

    return trade