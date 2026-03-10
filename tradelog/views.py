from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from decimal import Decimal

from tradelog.models import Trade
from tradelog.serializers import TradeManagementSerializer
from .pagination import StandardResultsSetPagination

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

def _get_session_lock_response(user, date=None):
    """
    Returns a DRF Response (HTTP 423) if the user's trading session is locked,
    or None if trading is allowed.

    """
    from rules.engine import is_session_locked
    locked, message = is_session_locked(user, date=date)
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
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = TradeImportSerializer

    def post(self, request, *args, **kwargs):
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

        try:
            detected_broker, rows = detect_and_normalize(raw_rows, broker_name)
        except Exception as e:
            return Response({'error': f'Format normalization failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        created_trades = []
        errors = []
        skipped_trades = []
        blocked_dates = set()  # dates whose session got locked during this import

        # Sort rows by date ascending so rules are evaluated in chronological
        # order. This ensures that if Feb-20 hits maxTrades and locks, all
        # remaining Feb-20 rows are blocked before we even start Feb-21.
        def _parse_date_for_sort(row):
            from datetime import datetime, date as ddate
            date_raw = row.get('date') or row.get('trade_date', '')
            if date_raw and ' ' in str(date_raw):
                date_raw = str(date_raw).split(' ')[0]
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y'):
                try:
                    return datetime.strptime(str(date_raw), fmt).date()
                except (ValueError, TypeError):
                    continue
            return ddate.today()

        rows = sorted(rows, key=_parse_date_for_sort)

        # Tracks the first date that locked during this import.
        # Once set, ALL subsequent rows (any date) are stopped immediately.
        import_stopped_at = None

        for i, row in enumerate(rows, start=1):
            row_date = _parse_date_for_sort(row)

            # If import was already stopped by a previous violation, block
            # every remaining row regardless of date.
            if import_stopped_at is not None:
                errors.append({
                    'row': i,
                    'error': f'Import stopped — session locked for {import_stopped_at}. Unlock that session first then re-import.',
                    'data': row,
                })
                continue

            # Re-check DB lock state before every row — the signal from
            # the previous trade may have just locked this date.
            from rules.engine import is_session_locked
            locked, lock_msg = is_session_locked(request.user, date=row_date)
            if locked:
                import_stopped_at = row_date
                errors.append({
                    'row': i,
                    'error': f'Import stopped — session locked for {row_date}: {lock_msg}',
                    'data': row,
                })
                continue

            try:
                trade = _create_trade_from_row(row, request.user, detected_broker or broker_name)
                created_trades.append(trade)

                # After save, signal fires synchronously and may lock this date.
                # If it did, stop the entire import from the next row onwards.
                locked, lock_msg = is_session_locked(request.user, date=row_date)
                if locked:
                    import_stopped_at = row_date

            except ValueError as e:
                err_str = str(e)
                if err_str.startswith('DUPLICATE'):
                    # Already imported — silently skip, do not stop import
                    skipped_trades.append(row)
                else:
                    # Real lock or error — stop the entire import
                    import_stopped_at = row_date
                    errors.append({'row': i, 'error': err_str, 'data': row})
            except Exception as e:
                errors.append({'row': i, 'error': str(e), 'data': row})

        response_data = {
            'imported': len(created_trades),
            'failed': len(errors),
            'errors': errors[:10],
            'detected_broker': detected_broker,
            'skipped': len(skipped_trades),
            'message': f'{len(created_trades)} trades imported successfully.',
        }
        if import_stopped_at is not None:
            response_data['import_stopped'] = True
            response_data['stopped_at_date'] = str(import_stopped_at)
            response_data['message'] = (
                f'{len(created_trades)} trades imported. '
                f'Import stopped at {import_stopped_at} due to a rule violation. '
                f'Unlock that session to import remaining trades.'
            )

        return Response(response_data, status=status.HTTP_201_CREATED)


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
        # Block manual trade entry when today's session is locked.
        lock_response = _get_session_lock_response(request.user)
        if lock_response:
            return lock_response
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        trade = serializer.save(user=self.request.user)
        trade.calculate_pnl()

        if trade.strategy and trade.emotional_state and trade.entry_confidence:
            trade.is_tagged_complete = True

        trade.save(update_fields=['total_pnl', 'is_tagged_complete'])

        if trade.strategy:
            total = Trade.objects.filter(
                strategy=trade.strategy, deleted_at__isnull=True
            ).count()
            trade.strategy.update_maturity(total)




class TradeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/tradelog/trades/<id>/"""
    serializer_class = TradeManagementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Trade.objects.filter(user=self.request.user, deleted_at__isnull=True)

    def perform_update(self, serializer):
        trade = serializer.save()
        trade.calculate_pnl()

        if trade.strategy and trade.emotional_state and trade.entry_confidence:
            trade.is_tagged_complete = True

        trade.save(update_fields=['total_pnl', 'is_tagged_complete'])

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
    """
    Create and save a Trade instance from a normalized row dict.

    """
    from datetime import datetime, date as ddate
    from discipline.models import DisciplineSession
    from rules.engine import is_session_locked

    symbol = row.get('symbol') or row.get('scrip', '')
    direction = (row.get('direction') or row.get('trade_type', 'long')).lower()
    quantity = Decimal(str(row.get('quantity') or row.get('qty', 1)))
    entry_price = Decimal(str(row.get('entry_price') or row.get('buy_price', 0)))
    exit_price_raw = row.get('exit_price') or row.get('sell_price', '')
    exit_price = Decimal(str(exit_price_raw)) if exit_price_raw else None
    fees = Decimal(str(row.get('fees') or row.get('brokerage', 0)))

    # Date parsing — strip any time component (e.g. Upstox sends "2026-02-24 00:00:00")
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
            parts = str(time_raw).split(':')
            trade_time = dtime(
                int(parts[0]),
                int(parts[1]),
                int(parts[2]) if len(parts) > 2 else 0
            )
        except Exception:
            pass


    already_exists = Trade.objects.filter(
        user=user,
        trade_date=trade_date,
        symbol=symbol or 'UNKNOWN',
        direction='long' if direction in ('long', 'buy', 'b') else 'short',
        entry_price=entry_price,
        quantity=quantity,
        deleted_at__isnull=True,
    ).exists()
    if already_exists:
        raise ValueError(f"DUPLICATE — trade already imported for {trade_date} {symbol} skipped.")

    # Check the session lock for this specific trade_date BEFORE saving.
    locked, lock_msg = is_session_locked(user, date=trade_date)
    if locked:
        raise ValueError(f"Trade blocked — session locked for {trade_date}: {lock_msg}")

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

    if trade.strategy:
        total = Trade.objects.filter(
            strategy=trade.strategy, deleted_at__isnull=True
        ).count()
        trade.strategy.update_maturity(total)

    return trade