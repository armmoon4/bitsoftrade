from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from django.utils import timezone
from django.db.models import Q
from decimal import Decimal, InvalidOperation
import uuid
from django.core.files.storage import FileSystemStorage
from tradelog.models import Trade
from tradelog.serializers import ImageUploadSerializer, TradeManagementSerializer
from tradelog.serializers import TradeSymbolSerializer
from .pagination import StandardResultsSetPagination
from accounts.permissions import HasToolSubscription

from .importers.parser import parse_csv, parse_excel, detect_and_normalize


# ─────────────────────────────────────────────
# SERIALIZERS
# ─────────────────────────────────────────────

class TradeImportSerializer(serializers.Serializer):
    file = serializers.FileField()
    broker_name = serializers.CharField(required=False, allow_blank=True)


# ─────────────────────────────────────────────
# FILTER HELPER
# ─────────────────────────────────────────────

def _apply_filters(qs, params):
    from datetime import date, timedelta

    trade_filter = params.get('filter')
    if trade_filter == 'wins':
        qs = qs.filter(total_pnl__gt=0)
    elif trade_filter == 'losses':
        qs = qs.filter(total_pnl__lt=0)
    elif trade_filter == 'disciplined':
        qs = qs.filter(is_disciplined=True)
    elif trade_filter == 'violations':
        qs = qs.filter(is_disciplined=False)

    broker = params.get('broker', '').strip()
    if broker:
        qs = qs.filter(broker_name__iexact=broker)

    market_type = params.get('market_type', '').strip()
    if market_type:
        qs = qs.filter(market_type=market_type)

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

    direction = params.get('direction', '').strip().lower()
    if direction in ('long', 'short'):
        qs = qs.filter(direction=direction)

    outcome = params.get('outcome', '').strip().lower()
    if outcome == 'win':
        qs = qs.filter(total_pnl__gt=0)
    elif outcome == 'loss':
        qs = qs.filter(total_pnl__lt=0)
    elif outcome == 'open':
        qs = qs.filter(exit_price__isnull=True)

    instrument_type = params.get('instrument_type', '').strip()
    if instrument_type:
        qs = qs.filter(market_type=instrument_type)

    strategy_id = params.get('strategy', '').strip()
    if strategy_id:
        qs = qs.filter(strategy__id=strategy_id)

    emotional_state = params.get('emotional_state', '').strip().lower()
    if emotional_state:
        qs = qs.filter(emotional_state=emotional_state)

    discipline_status = params.get('discipline_status', '').strip().lower()
    if discipline_status == 'disciplined':
        qs = qs.filter(is_disciplined=True)
    elif discipline_status == 'violations':
        qs = qs.filter(is_disciplined=False)

    review_status = params.get('review_status', '').strip().lower()
    if review_status == 'tagged':
        qs = qs.filter(is_tagged_complete=True)
    elif review_status == 'untagged':
        qs = qs.filter(is_tagged_complete=False)

    rule_breach = params.get('rule_breach', '').strip()
    if rule_breach:
        for breach in [b.strip() for b in rule_breach.split(',') if b.strip()]:
            qs = qs.filter(violation_modes__contains=breach)

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

    mistakes = params.get('mistakes', '').strip()
    if mistakes:
        for mistake in [m.strip() for m in mistakes.split(',') if m.strip()]:
            qs = qs.filter(violation_modes__contains=mistake)

    tags = params.get('tags', '').strip()
    if tags:
        for tag in [t.strip() for t in tags.split(',') if t.strip()]:
            qs = qs.filter(
                Q(violation_modes__contains=tag) |
                Q(rules_followed__contains=tag)
            )

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

    Behavior:
    - Check if there is an active locked session (red/yellow) BEFORE starting.
      If locked → return 423 immediately. User must unlock first.
    - If not locked → import ALL trades from the file without any mid-loop
      blocking. Rule violations are evaluated after each trade save via the
      post_save signal. The session may go red/yellow during this import,
      but that only affects the NEXT import — never the current file.
    """
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = TradeImportSerializer

    def post(self, request, *args, **kwargs):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        # ── Block import if any session is currently locked ───────────────────
        # Uses get_active_locked_session so a red/yellow session from ANY recent
        # date (not just today) will block a new import.
        from rules.engine import is_session_locked
        locked, lock_message = is_session_locked(request.user)
        if locked:
            return Response(
                {'error': 'Trading session is locked.', 'detail': lock_message},
                status=status.HTTP_423_LOCKED,
            )

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
            from datetime import date as ddate
            return ddate.today()

        rows = sorted(rows, key=_parse_date_for_sort)

        # ── Import ALL trades — NO lock checks inside this loop ───────────────
        # The post_save signal fires after each save and updates the session
        # state if rules are violated. This is intentional — all trades in the
        # file must be saved first. Blocking mid-import would prevent users from
        # importing historical data (e.g. 6 months of trades at once).
        created_trades = []
        errors = []
        skipped_trades = []

        for i, row in enumerate(rows, start=1):
            try:
                trade = _create_trade_from_row(row, request.user, detected_broker or broker_name)
                created_trades.append(trade)
            except ValueError as e:
                err_str = str(e)
                if err_str.startswith('DUPLICATE'):
                    skipped_trades.append(row)
                else:
                    errors.append({'row': i, 'error': err_str, 'data': row})
            except Exception as e:
                errors.append({'row': i, 'error': str(e), 'data': row})

        # ── After all trades saved, reflect the current session state ─────────
        # The post_save signal may have escalated one or more sessions to RED/YELLOW
        # during this import. Collect the worst state across all imported trade dates
        # so the frontend can immediately show the correct Discipline Guard status
        # without needing a separate API call.
        from rules.engine import get_active_locked_session
        from discipline.models import DisciplineSession
        from discipline.serializers import DisciplineSessionSerializer

        active_locked = get_active_locked_session(request.user)
        if active_locked:
            active_locked.refresh_from_db()
            session_info = DisciplineSessionSerializer(active_locked).data
            final_state = active_locked.session_state
            locked, lock_msg = is_session_locked(request.user)
        else:
            # No locked session — return today's session (green)
            from django.utils.timezone import localdate
            today_sess, _ = DisciplineSession.objects.get_or_create(
                user=request.user,
                session_date=localdate(),
                defaults={'session_state': 'green'},
            )
            today_sess.refresh_from_db()
            session_info = DisciplineSessionSerializer(today_sess).data
            final_state = today_sess.session_state
            locked, lock_msg = False, ''

        return Response({
            'imported': len(created_trades),
            'failed': len(errors),
            'skipped': len(skipped_trades),
            'errors': errors[:10],
            'detected_broker': detected_broker,
            'message': f'{len(created_trades)} trades imported successfully.',
            # Session fields — let frontend update Discipline Guard without extra poll
            'session_state': final_state,
            'session_locked': locked,
            'lock_message': lock_msg,
            'session': session_info,
        }, status=status.HTTP_201_CREATED)


class TradeListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/tradelog/trades/
    POST /api/tradelog/trades/  (Add Trade)
    """
    serializer_class = TradeManagementSerializer
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = (
            Trade.objects
            .filter(user=self.request.user, deleted_at__isnull=True)
            .prefetch_related('violation_logs__rule')
        )
        return _apply_filters(qs, self.request.query_params)

    def create(self, request, *args, **kwargs):
        # Block manual Add Trade if any session is currently locked.
        # Uses is_session_locked(date=None) which calls get_active_locked_session
        # so a red/yellow session from ANY recent date blocks new manual entries.
        from rules.engine import is_session_locked
        locked, message = is_session_locked(request.user)
        if locked:
            return Response(
                {'error': 'Trading session is locked.', 'detail': message},
                status=status.HTTP_423_LOCKED,
            )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        trade = serializer.save(user=self.request.user)
        trade.calculate_pnl()
        if trade.strategy and trade.emotional_state and trade.entry_confidence:
            trade.is_tagged_complete = True
        trade.save(update_fields=['total_pnl', 'is_tagged_complete'])
        if trade.strategy:
            total = Trade.objects.filter(strategy=trade.strategy, deleted_at__isnull=True).count()
            trade.strategy.update_maturity(total)


class TradeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/tradelog/trades/<id>/"""
    serializer_class = TradeManagementSerializer
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]

    def get_queryset(self):
        return (
            Trade.objects
            .filter(user=self.request.user, deleted_at__isnull=True)
            .prefetch_related('violation_logs__rule')
        )

    def perform_update(self, serializer):
        trade = serializer.save()
        trade.calculate_pnl()
        if trade.strategy and trade.emotional_state and trade.entry_confidence:
            trade.is_tagged_complete = True
        trade.save(update_fields=['total_pnl', 'is_tagged_complete'])
        if trade.strategy:
            total = Trade.objects.filter(strategy=trade.strategy, deleted_at__isnull=True).count()
            trade.strategy.update_maturity(total)

    def destroy(self, request, *args, **kwargs):
        trade = self.get_object()
        trade.deleted_at = timezone.now()
        trade.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────
# TRADE CREATION HELPER
# ─────────────────────────────────────────────

def _parse_time_field(raw):
    if not raw:
        return None
    try:
        from datetime import time as dtime
        parts = str(raw).strip().split(':')
        return dtime(
            int(parts[0]),
            int(parts[1]),
            int(parts[2]) if len(parts) > 2 else 0,
        )
    except Exception:
        return None


def _create_trade_from_row(row, user, broker_name):
    """
    Create and save a Trade from a normalized CSV row.

    NO session lock check here — locking is handled:
      - BEFORE the import loop starts (in TradeImportView.post)
      - AFTER save via post_save signal (discipline/signals.py → engine)

    This ensures all trades in a file are saved regardless of rule violations
    triggered mid-import.
    """
    from datetime import datetime, date as ddate
    from discipline.models import DisciplineSession

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

    trade_time = _parse_time_field(row.get('time') or row.get('trade_time', ''))
    entry_time = _parse_time_field(row.get('entry_time', ''))
    exit_time = _parse_time_field(row.get('exit_time', ''))

    # Duplicate check
    normalized_direction = 'long' if direction in ('long', 'buy', 'b') else 'short'
    already_exists = Trade.objects.filter(
        user=user,
        trade_date=trade_date,
        symbol=symbol or 'UNKNOWN',
        direction=normalized_direction,
        entry_price=entry_price,
        quantity=quantity,
        deleted_at__isnull=True,
    ).exists()
    if already_exists:
        raise ValueError(f"DUPLICATE — trade already imported for {trade_date} {symbol} skipped.")

    session, _ = DisciplineSession.objects.get_or_create(
        user=user, session_date=trade_date, defaults={'session_state': 'green'}
    )

    trade = Trade(
        user=user,
        session=session,
        trade_date=trade_date,
        trade_time=trade_time,
        entry_time=entry_time,
        exit_time=exit_time,
        symbol=symbol or 'UNKNOWN',
        market_type=row.get('market_type', 'indian_market'),
        direction=normalized_direction,
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
        total = Trade.objects.filter(strategy=trade.strategy, deleted_at__isnull=True).count()
        trade.strategy.update_maturity(total)

    return trade


class TradeSymbolListView(generics.ListAPIView):
    serializer_class = TradeSymbolSerializer
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]
    pagination_class = None

    def get_queryset(self):
        return Trade.objects.filter(
            user=self.request.user, deleted_at__isnull=True
        ).only('id', 'symbol')


# ─────────────────────────────────────────────
# SCREENSHOT UPLOAD
# ─────────────────────────────────────────────

class ImageUploadView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = ImageUploadSerializer

    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist('images')
        if not files:
            return Response({"error": "No images provided."}, status=status.HTTP_400_BAD_REQUEST)
        fs = FileSystemStorage()
        uploaded_urls = []
        for file_obj in files:
            extension = file_obj.name.split('.')[-1]
            unique_filename = f"screenshots/{uuid.uuid4()}.{extension}"
            saved_name = fs.save(unique_filename, file_obj)
            uploaded_urls.append(request.build_absolute_uri(fs.url(saved_name)))
        return Response({
            "message": f"{len(uploaded_urls)} image(s) uploaded successfully.",
            "urls": uploaded_urls,
        }, status=status.HTTP_201_CREATED)


# ─────────────────────────────────────────────
# TRADE SCREENSHOT MANAGEMENT
# ─────────────────────────────────────────────

class TradeScreenshotView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]
    parser_classes = [MultiPartParser, FormParser]

    def _get_trade(self, request, pk):
        try:
            return Trade.objects.get(pk=pk, user=request.user, deleted_at__isnull=True)
        except Trade.DoesNotExist:
            return None

    def get(self, request, pk, *args, **kwargs):
        trade = self._get_trade(request, pk)
        if not trade:
            return Response({"error": "Trade not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "trade_id": str(trade.id),
            "screenshot_urls": trade.screenshot_urls,
            "count": len(trade.screenshot_urls),
        })

    def post(self, request, pk, *args, **kwargs):
        trade = self._get_trade(request, pk)
        if not trade:
            return Response({"error": "Trade not found."}, status=status.HTTP_404_NOT_FOUND)
        files = request.FILES.getlist('images')
        if not files:
            return Response({"error": "No images provided."}, status=status.HTTP_400_BAD_REQUEST)
        fs = FileSystemStorage()
        new_urls = []
        for file_obj in files:
            extension = file_obj.name.rsplit('.', 1)[-1]
            unique_filename = f"screenshots/{uuid.uuid4()}.{extension}"
            saved_name = fs.save(unique_filename, file_obj)
            new_urls.append(request.build_absolute_uri(fs.url(saved_name)))
        trade.screenshot_urls = (trade.screenshot_urls or []) + new_urls
        trade.save(update_fields=['screenshot_urls'])
        return Response({
            "message": f"{len(new_urls)} screenshot(s) added.",
            "added_urls": new_urls,
            "screenshot_urls": trade.screenshot_urls,
            "count": len(trade.screenshot_urls),
        }, status=status.HTTP_201_CREATED)

    def delete(self, request, pk, *args, **kwargs):
        trade = self._get_trade(request, pk)
        if not trade:
            return Response({"error": "Trade not found."}, status=status.HTTP_404_NOT_FOUND)
        urls_to_remove = request.data.get('urls', [])
        if not urls_to_remove:
            removed_count = len(trade.screenshot_urls)
            trade.screenshot_urls = []
            trade.save(update_fields=['screenshot_urls'])
            return Response({"message": f"All {removed_count} screenshot(s) removed.", "screenshot_urls": [], "count": 0})
        current_urls = trade.screenshot_urls or []
        updated_urls = [u for u in current_urls if u not in urls_to_remove]
        trade.screenshot_urls = updated_urls
        trade.save(update_fields=['screenshot_urls'])
        return Response({
            "message": f"{len(current_urls) - len(updated_urls)} screenshot(s) removed.",
            "screenshot_urls": trade.screenshot_urls,
            "count": len(trade.screenshot_urls),
        })


# ─────────────────────────────────────────────
# BULK OPERATIONS
# ─────────────────────────────────────────────

class TradeBulkDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]

    def post(self, request, *args, **kwargs):
        data = request.data
        delete_all = data.get('delete_all', False)
        base_qs = Trade.objects.filter(user=request.user, deleted_at__isnull=True)

        if delete_all:
            qs = _apply_filters(base_qs, data)
            count = qs.count()
            qs.update(deleted_at=timezone.now())
            return Response({"deleted": count, "message": f"{count} trade(s) deleted successfully."}, status=status.HTTP_200_OK)

        ids = data.get('ids', [])
        if not ids:
            return Response({"error": "Provide either 'ids' list or 'delete_all': true."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(ids, list):
            return Response({"error": "'ids' must be a list of trade UUIDs."}, status=status.HTTP_400_BAD_REQUEST)

        valid_ids, invalid_ids = [], []
        for raw_id in ids:
            try:
                valid_ids.append(uuid.UUID(str(raw_id)))
            except (ValueError, AttributeError):
                invalid_ids.append(raw_id)

        if invalid_ids:
            return Response({"error": f"Invalid UUIDs: {invalid_ids}"}, status=status.HTTP_400_BAD_REQUEST)

        qs = base_qs.filter(id__in=valid_ids)
        found_count = qs.count()
        not_found_count = len(valid_ids) - found_count
        qs.update(deleted_at=timezone.now())

        response = {"deleted": found_count, "message": f"{found_count} trade(s) deleted successfully."}
        if not_found_count:
            response["not_found"] = not_found_count
            response["note"] = f"{not_found_count} ID(s) were not found or already deleted."
        return Response(response, status=status.HTTP_200_OK)