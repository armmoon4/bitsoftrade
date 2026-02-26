from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from tradelog.models import Trade
from tradelog.serializers import TradeManagementSerializer
from .pagination import StandardResultsSetPagination
from decimal import Decimal, ROUND_HALF_UP
import io


# SERIALIZER FOR THE BROWSER UI
class TradeImportSerializer(serializers.Serializer):
    file = serializers.FileField()
    broker_name = serializers.CharField(required=False, allow_blank=True)


# THE IMPORT VIEW
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
                raw_rows = _parse_csv(file)
            elif filename.endswith(('.xlsx', '.xls')):
                raw_rows = _parse_excel(file)
            else:
                return Response(
                    {'error': 'Unsupported file type. Upload CSV or Excel.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            return Response({'error': f'File parsing failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # Detect broker format and normalize rows into standard trade dicts
        try:
            detected_broker, rows = _detect_and_normalize(raw_rows, broker_name)
        except Exception as e:
            return Response({'error': f'Format normalization failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        created_trades = []
        errors = []

        for i, row in enumerate(rows, start=1):
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


# STANDARD API VIEWS
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

    def perform_create(self, serializer):
        trade = serializer.save(user=self.request.user)
        trade.calculate_pnl()
        trade.save(update_fields=['total_pnl'])


class TradeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/tradelog/trades/<id>/"""
    serializer_class = TradeManagementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Trade.objects.filter(user=self.request.user, deleted_at__isnull=True)

    def perform_update(self, serializer):
        trade = serializer.save()
        trade.calculate_pnl()
        trade.save(update_fields=['total_pnl'])

    def destroy(self, request, *args, **kwargs):
        trade = self.get_object()
        trade.deleted_at = timezone.now()
        trade.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────
# BROKER DETECTION & NORMALIZATION
# ─────────────────────────────────────────────

def _detect_and_normalize(raw_rows, broker_hint=''):
    """
    Auto-detect broker format from headers or broker_hint,
    then return (broker_name, normalized_rows) where each
    normalized row matches the generic _create_trade_from_row schema.
    """
    if not raw_rows:
        return 'unknown', []

    headers = set(raw_rows[0].keys())

    # Zerodha detection: has 'trade_id', 'order_execution_time', 'series'
    is_zerodha = (
        broker_hint == 'zerodha' or
        {'trade_id', 'order_execution_time', 'series', 'segment'}.issubset(headers)
    )

    if is_zerodha:
        return 'zerodha', _normalize_zerodha(raw_rows)

    # Future: Upstox, Groww detection here
    # is_upstox = broker_hint == 'upstox' or {'instrument_name', 'trade_no'}.issubset(headers)
    # is_groww  = broker_hint == 'groww'  or {'scrip_name', 'trade_number'}.issubset(headers)

    # Fallback: generic format
    return broker_hint or 'generic', raw_rows


def _normalize_zerodha(raw_rows):
    """
    Zerodha tradebook CSV has one row per execution (buy or sell leg).
    Strategy:
      1. Group all executions by (symbol, trade_date).
      2. Within each group, compute VWAP entry price from all buy legs,
         VWAP exit price from all sell legs, net quantity, and total fees (0 in CSV, set default).
      3. Determine direction: if total buy qty >= total sell qty → 'long', else 'short'.
      4. Emit one normalized trade dict per (symbol, date) group.

    Zerodha CSV columns (tab-separated, normalized to lowercase by _parse_csv):
      symbol, isin, trade_date, exchange, segment, series,
      trade_type, auction, quantity, price, trade_id,
      order_id, order_execution_time, expiry_date
    """
    from collections import defaultdict
    from datetime import datetime

    # Group executions by (symbol, trade_date)
    groups = defaultdict(lambda: {'buys': [], 'sells': [], 'segment': '', 'exchange': ''})

    for row in raw_rows:
        symbol = (row.get('symbol') or '').strip()
        trade_date_raw = (row.get('trade_date') or '').strip()
        trade_type = (row.get('trade_type') or '').strip().lower()

        if not symbol or not trade_date_raw:
            continue

        try:
            qty = Decimal(str(row.get('quantity') or 0))
            price = Decimal(str(row.get('price') or 0))
        except Exception:
            continue

        key = (symbol, trade_date_raw)
        groups[key]['segment'] = row.get('segment', '').strip().upper()
        groups[key]['exchange'] = row.get('exchange', 'NSE').strip().upper()

        # Capture first execution time for trade_time
        exec_time_raw = (row.get('order_execution_time') or '').strip()
        exec_time = None
        if exec_time_raw:
            for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
                try:
                    exec_time = datetime.strptime(exec_time_raw, fmt)
                    break
                except ValueError:
                    continue

        entry = {'qty': qty, 'price': price, 'time': exec_time}

        if trade_type == 'buy':
            groups[key]['buys'].append(entry)
        elif trade_type == 'sell':
            groups[key]['sells'].append(entry)

    normalized = []

    for (symbol, trade_date_raw), data in groups.items():
        buys = data['buys']
        sells = data['sells']
        segment = data['segment']
        exchange = data['exchange']

        if not buys and not sells:
            continue

        # VWAP calculation helper
        def vwap(legs):
            total_qty = sum(l['qty'] for l in legs)
            if total_qty == 0:
                return Decimal('0'), Decimal('0')
            total_value = sum(l['qty'] * l['price'] for l in legs)
            return (total_value / total_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP), total_qty

        buy_vwap, total_buy_qty = vwap(buys)
        sell_vwap, total_sell_qty = vwap(sells)

        # Direction: long = bought first (buy qty dominates or equal)
        direction = 'long' if total_buy_qty >= total_sell_qty else 'short'

        if direction == 'long':
            entry_price = buy_vwap
            exit_price = sell_vwap if sells else None
            quantity = total_buy_qty
        else:
            # Short trade: sold first, bought to close
            entry_price = sell_vwap
            exit_price = buy_vwap if buys else None
            quantity = total_sell_qty

        # Earliest execution time as trade_time
        all_legs = buys + sells
        all_times = [l['time'] for l in all_legs if l['time'] is not None]
        trade_time_str = min(all_times).strftime('%H:%M') if all_times else ''

        # Market type mapping from segment
        market_type_map = {
            'FO': 'indian_options',
            'EQ': 'indian_stocks',
            'CDS': 'indian_currency',
            'COM': 'indian_commodity',
            'MF': 'indian_stocks',
        }
        market_type = market_type_map.get(segment, 'indian_stocks')

        normalized.append({
            'symbol': symbol,
            'trade_date': trade_date_raw,      # dd-mm-yyyy  — handled in _create_trade_from_row
            'time': trade_time_str,
            'direction': direction,
            'quantity': str(quantity),
            'entry_price': str(entry_price),
            'exit_price': str(exit_price) if exit_price is not None else '',
            'fees': '0',                        # Zerodha CSV has no fees column; user can edit
            'market_type': market_type,
            'exchange': exchange,
            'segment': segment,
        })

    return normalized


# ─────────────────────────────────────────────
# FILE PARSING HELPERS
# ─────────────────────────────────────────────

def _parse_csv(file):
    import csv
    content = file.read().decode('utf-8', errors='ignore')
    # Handle tab-separated (Zerodha) or comma-separated
    sample = content[:2048]
    delimiter = '\t' if sample.count('\t') > sample.count(',') else ','
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    rows = []
    for row in reader:
        rows.append({k.strip().lower().replace(' ', '_'): (v.strip() if v else '') for k, v in row.items()})
    return rows


def _parse_excel(file):
    try:
        import openpyxl
    except ImportError:
        raise ImportError('openpyxl not installed. Run: pip install openpyxl')
    wb = openpyxl.load_workbook(file, data_only=True)
    ws = wb.active
    headers = [str(cell.value).strip().lower().replace(' ', '_') for cell in ws[1]]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if any(v is not None for v in row):
            rows.append(dict(zip(headers, [str(v).strip() if v is not None else '' for v in row])))
    return rows


# ─────────────────────────────────────────────
# TRADE CREATION
# ─────────────────────────────────────────────

def _create_trade_from_row(row, user, broker_name):
    """Create a Trade from a normalized row dict."""
    from datetime import datetime, date as ddate
    from discipline.models import DisciplineSession

    symbol = row.get('symbol') or row.get('scrip', '')
    direction = (row.get('direction') or row.get('trade_type', 'long')).lower()
    quantity = Decimal(str(row.get('quantity') or row.get('qty', 1)))
    entry_price = Decimal(str(row.get('entry_price') or row.get('buy_price', 0)))
    exit_price_raw = row.get('exit_price') or row.get('sell_price', '')
    exit_price = Decimal(str(exit_price_raw)) if exit_price_raw else None
    fees = Decimal(str(row.get('fees') or row.get('brokerage', 0)))

    # Date — support dd-mm-yyyy (Zerodha), yyyy-mm-dd, dd/mm/yyyy, mm/dd/yyyy
    date_raw = row.get('date') or row.get('trade_date', '')
    trade_date = ddate.today()
    for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            trade_date = datetime.strptime(date_raw, fmt).date()
            break
        except (ValueError, TypeError):
            continue

    # Time
    time_raw = row.get('time') or row.get('trade_time', '')
    trade_time = None
    if time_raw:
        try:
            from datetime import time as dtime
            parts = time_raw.split(':')
            trade_time = dtime(int(parts[0]), int(parts[1]))
        except Exception:
            pass

    # Get or create discipline session
    from discipline.models import DisciplineSession
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
    return trade