from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from django.db.models import Q
from decimal import Decimal, InvalidOperation

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
# FILTER HELPER
# ─────────────────────────────────────────────

def _apply_filters(qs, params):
    """
    Apply all query param filters to a Trade queryset.
    All filters are combinable (ANDed together).

    Supported query params:
    ┌─────────────────────┬──────────────────────────────────────────────────────────────┐
    │ Param               │ Values / Notes                                               │
    ├─────────────────────┼──────────────────────────────────────────────────────────────┤
    │ filter              │ wins | losses | disciplined | violations                     │
    │ broker              │ exact broker_name (case-insensitive)                         │
    │ market_type         │ indian_stocks | forex | crypto | options                     │
    │ date_range          │ this_month | this_week | today | custom                      │
    │ date_from           │ YYYY-MM-DD  (used when date_range=custom)                   │
    │ date_to             │ YYYY-MM-DD  (used when date_range=custom)                   │
    │ direction           │ long | short                                                 │
    │ outcome             │ win | loss | open  (open = no exit_price)                   │
    │ instrument_type     │ same as market_type choices                                  │
    │ strategy            │ strategy UUID                                                │
    │ emotional_state     │ calm | anxious | confident | fearful | fomo |               │
    │                     │ angry | overconfident | uncertain                            │
    │ discipline_status   │ disciplined | violations                                     │
    │ review_status       │ tagged | untagged  (is_tagged_complete)                     │
    │ rule_breach         │ comma-separated violation modes e.g. fomo_entry,overtrading │
    │ pnl_min             │ decimal  e.g. -10000                                        │
    │ pnl_max             │ decimal  e.g. 10000                                         │
    │ mistakes            │ comma-separated: fomo_entry | revenge_trading |             │
    │                     │ oversized_position | premature_exit |                       │
    │                     │ ignored_stop_loss | overtrading                             │
    │ tags                │ comma-separated tag strings (searched inside violation_modes │
    │                     │ and rules_followed JSON fields)                             │
    │ search              │ free-text search on symbol, broker_name, lessons_learned    │
    └─────────────────────┴──────────────────────────────────────────────────────────────┘
    """
    from datetime import date, timedelta
    import calendar

    # ── 1. Outcome filter (wins / losses tab)
    trade_filter = params.get('filter')
    if trade_filter == 'wins':
        qs = qs.filter(total_pnl__gt=0)
    elif trade_filter == 'losses':
        qs = qs.filter(total_pnl__lt=0)
    elif trade_filter == 'disciplined':
        qs = qs.filter(is_disciplined=True)
    elif trade_filter == 'violations':
        qs = qs.filter(is_disciplined=False)

    # ── 2. Broker
    broker = params.get('broker', '').strip()
    if broker:
        qs = qs.filter(broker_name__iexact=broker)

    # ── 3. Market type (top-bar "Indian Stocks" dropdown)
    market_type = params.get('market_type', '').strip()
    if market_type:
        qs = qs.filter(market_type=market_type)

    # ── 4. Date range
    date_range = params.get('date_range', '').strip()
    today = date.today()
    if date_range == 'today':
        qs = qs.filter(trade_date=today)
    elif date_range == 'this_week':
        week_start = today - timedelta(days=today.weekday())
        qs = qs.filter(trade_date__gte=week_start, trade_date__lte=today)
    elif date_range == 'this_month':
        qs = qs.filter(trade_date__year=today.year, trade_date__month=today.month)
    elif date_range == 'custom':
        date_from = params.get('date_from', '').strip()
        date_to = params.get('date_to', '').strip()
        if date_from:
            qs = qs.filter(trade_date__gte=date_from)
        if date_to:
            qs = qs.filter(trade_date__lte=date_to)

    # ── 5. Direction  (long | short)
    direction = params.get('direction', '').strip().lower()
    if direction in ('long', 'short'):
        qs = qs.filter(direction=direction)

    # ── 6. Outcome  (win | loss | open)
    outcome = params.get('outcome', '').strip().lower()
    if outcome == 'win':
        qs = qs.filter(total_pnl__gt=0)
    elif outcome == 'loss':
        qs = qs.filter(total_pnl__lt=0)
    elif outcome == 'open':
        qs = qs.filter(exit_price__isnull=True)

    # ── 7. Instrument type (alias for market_type in "More Filters")
    instrument_type = params.get('instrument_type', '').strip()
    if instrument_type:
        qs = qs.filter(market_type=instrument_type)

    # ── 8. Strategy
    strategy_id = params.get('strategy', '').strip()
    if strategy_id:
        qs = qs.filter(strategy__id=strategy_id)

    # ── 9. Emotional state
    emotional_state = params.get('emotional_state', '').strip().lower()
    if emotional_state:
        qs = qs.filter(emotional_state=emotional_state)

    # ── 10. Discipline status
    discipline_status = params.get('discipline_status', '').strip().lower()
    if discipline_status == 'disciplined':
        qs = qs.filter(is_disciplined=True)
    elif discipline_status == 'violations':
        qs = qs.filter(is_disciplined=False)

    # ── 11. Review / tag status
    review_status = params.get('review_status', '').strip().lower()
    if review_status == 'tagged':
        qs = qs.filter(is_tagged_complete=True)
    elif review_status == 'untagged':
        qs = qs.filter(is_tagged_complete=False)

    # ── 12. Rule breaches  (comma-separated violation mode strings)
    rule_breach = params.get('rule_breach', '').strip()
    if rule_breach:
        breaches = [b.strip() for b in rule_breach.split(',') if b.strip()]
        for breach in breaches:
            qs = qs.filter(violation_modes__contains=breach)

    # ── 13. P&L Range
    pnl_min = params.get('pnl_min', '').strip()
    pnl_max = params.get('pnl_max', '').strip()
    if pnl_min:
        try:
            qs = qs.filter(total_pnl__gte=Decimal(pnl_min))
        except InvalidOperation:
            pass
    if pnl_max:
        try:
            qs = qs.filter(total_pnl__lte=Decimal(pnl_max))
        except InvalidOperation:
            pass

    # ── 14. Mistakes  (comma-separated — maps to violation_modes JSON field)
    #   Accepted values: fomo_entry | revenge_trading | oversized_position |
    #                    premature_exit | ignored_stop_loss | overtrading
    mistakes = params.get('mistakes', '').strip()
    if mistakes:
        mistake_list = [m.strip() for m in mistakes.split(',') if m.strip()]
        for mistake in mistake_list:
            qs = qs.filter(violation_modes__contains=mistake)

    # ── 15. Tags (free search across violation_modes + rules_followed JSON)
    tags = params.get('tags', '').strip()
    if tags:
        tag_list = [t.strip() for t in tags.split(',') if t.strip()]
        for tag in tag_list:
            qs = qs.filter(
                Q(violation_modes__contains=tag) |
                Q(rules_followed__contains=tag)
            )

    # ── 16. Free-text search  (symbol, broker, notes)
    search = params.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(symbol__icontains=search) |
            Q(broker_name__icontains=search) |
            Q(lessons_learned__icontains=search)
        )

    return qs


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
        blocked_dates = set()

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

        import_stopped_at = None

        for i, row in enumerate(rows, start=1):
            row_date = _parse_date_for_sort(row)

            if import_stopped_at is not None:
                errors.append({
                    'row': i,
                    'error': f'Import stopped — session locked for {import_stopped_at}. Unlock that session first then re-import.',
                    'data': row,
                })
                continue

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

                locked, lock_msg = is_session_locked(request.user, date=row_date)
                if locked:
                    import_stopped_at = row_date

            except ValueError as e:
                err_str = str(e)
                if err_str.startswith('DUPLICATE'):
                    skipped_trades.append(row)
                else:
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
    """
    GET  /api/tradelog/trades/
    POST /api/tradelog/trades/

    All query params are combinable. See _apply_filters() for full reference.

    Quick reference:
        ?filter=wins|losses|disciplined|violations
        ?broker=zerodha
        ?market_type=indian_stocks|forex|crypto|options
        ?date_range=today|this_week|this_month|custom&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
        ?direction=long|short
        ?outcome=win|loss|open
        ?instrument_type=indian_stocks|forex|crypto|options
        ?strategy=<uuid>
        ?emotional_state=calm|anxious|confident|fearful|fomo|angry|overconfident|uncertain
        ?discipline_status=disciplined|violations
        ?review_status=tagged|untagged
        ?rule_breach=fomo_entry,overtrading
        ?pnl_min=-10000&pnl_max=10000
        ?mistakes=fomo_entry,revenge_trading,oversized_position,premature_exit,ignored_stop_loss,overtrading
        ?tags=tag1,tag2
        ?search=RELIANCE
    """
    serializer_class = TradeManagementSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Trade.objects.filter(user=self.request.user, deleted_at__isnull=True)
        return _apply_filters(qs, self.request.query_params)

    def create(self, request, *args, **kwargs):
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

    locked, lock_msg = is_session_locked(user, date=trade_date)
    if locked:
        raise ValueError(f"Trade blocked — session locked for {trade_date}: {lock_msg}")

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