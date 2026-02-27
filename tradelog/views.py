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

    # Zerodha detection
    is_zerodha = (
        broker_hint == 'zerodha' or
        {'trade_id', 'order_execution_time', 'series', 'segment'}.issubset(headers)
    )
    if is_zerodha:
        return 'zerodha', _normalize_zerodha(raw_rows)

    # Groww detection
    is_groww = (
        broker_hint == 'groww' or
        {'stock_name', 'symbol', 'execution_date_and_time', 'order_status'}.issubset(headers)
    )
    if is_groww:
        return 'groww', _normalize_groww(raw_rows)

    # Fallback: generic format
    return broker_hint or 'generic', raw_rows


def _normalize_zerodha(raw_rows):
    """
    Zerodha tradebook CSV — one row per execution leg.
    Groups by (symbol, trade_date), computes VWAP entry/exit prices.
    """
    from collections import defaultdict
    from datetime import datetime

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

        def vwap(legs):
            total_qty = sum(l['qty'] for l in legs)
            if total_qty == 0:
                return Decimal('0'), Decimal('0')
            total_value = sum(l['qty'] * l['price'] for l in legs)
            return (total_value / total_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP), total_qty

        buy_vwap, total_buy_qty = vwap(buys)
        sell_vwap, total_sell_qty = vwap(sells)

        direction = 'long' if total_buy_qty >= total_sell_qty else 'short'

        if direction == 'long':
            entry_price = buy_vwap
            exit_price = sell_vwap if sells else None
            quantity = total_buy_qty
        else:
            entry_price = sell_vwap
            exit_price = buy_vwap if buys else None
            quantity = total_sell_qty

        all_legs = buys + sells
        all_times = [l['time'] for l in all_legs if l['time'] is not None]
        trade_time_str = min(all_times).strftime('%H:%M') if all_times else ''

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
            'trade_date': trade_date_raw,
            'time': trade_time_str,
            'direction': direction,
            'quantity': str(quantity),
            'entry_price': str(entry_price),
            'exit_price': str(exit_price) if exit_price is not None else '',
            'fees': '0',
            'market_type': market_type,
            'exchange': exchange,
            'segment': segment,
        })

    return normalized


def _normalize_groww(raw_rows):
    """
    Groww order history CSV/Excel — one row per executed order leg.
    
    Groww CSV columns (after _extract_rows_from_raw_data normalisation):
      stock_name, symbol, isin, type, quantity, value,
      exchange, exchange_order_id, execution_date_and_time, order_status
    """
    from collections import defaultdict
    from datetime import datetime

    # group by symbol only so swing trades are not split
    groups = defaultdict(lambda: {'buys': [], 'sells': [], 'exchange': ''})

    for row in raw_rows:
        # Skip any order that was not executed
        order_status = row.get('order_status', '').strip().lower()
        if order_status and order_status != 'executed':
            continue

        symbol = row.get('symbol', '').strip()
        if not symbol:
            continue

        # try multiple datetime formats before giving up
        exec_datetime_raw = row.get('execution_date_and_time', '').strip()
        trade_date_raw = ''
        exec_time = None

        if exec_datetime_raw:
            for fmt in (
                '%d-%m-%Y %I:%M %p',   # 08-02-2022 09:00 AM  — standard Groww CSV
                '%d-%m-%Y %H:%M',      # 08-02-2022 09:00     — 24-hr variant
                '%Y-%m-%d %H:%M:%S',   # ISO — Excel sometimes serialises this way
                '%d/%m/%Y %I:%M %p',   # slash-separated with AM/PM
                '%d/%m/%Y %H:%M',      # slash-separated 24-hr
            ):
                try:
                    exec_time = datetime.strptime(exec_datetime_raw, fmt)
                    trade_date_raw = exec_time.strftime('%Y-%m-%d')
                    break
                except ValueError:
                    continue

            # Last resort: extract just the date token from the raw string
            if not trade_date_raw:
                date_token = exec_datetime_raw.split()[0] if exec_datetime_raw.split() else ''
                for dfmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y'):
                    try:
                        exec_time = datetime.strptime(date_token, dfmt)
                        trade_date_raw = exec_time.strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        continue

        if not trade_date_raw:
            continue  # Cannot determine date — skip this row

        trade_type = row.get('type', '').strip().lower()

        # Groww stores total value (not per-share price), so derive price = value / qty
        try:
            qty = Decimal(str(row.get('quantity') or 0))
            value = Decimal(str(row.get('value') or 0))
            price = (value / qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP) if qty > 0 else Decimal('0')
        except Exception:
            continue

        # (cont.): key is symbol only
        key = symbol
        groups[key]['exchange'] = row.get('exchange', 'NSE').strip().upper()

        #  store the date inside each leg
        entry = {'qty': qty, 'price': price, 'time': exec_time, 'date': trade_date_raw}

        if trade_type == 'buy':
            groups[key]['buys'].append(entry)
        elif trade_type == 'sell':
            groups[key]['sells'].append(entry)

    normalized = []

    for symbol, data in groups.items():
        buys = data['buys']
        sells = data['sells']
        exchange = data['exchange']

        if not buys and not sells:
            continue

        def vwap(legs):
            total_qty = sum(l['qty'] for l in legs)
            if total_qty == 0:
                return Decimal('0'), Decimal('0')
            total_value = sum(l['qty'] * l['price'] for l in legs)
            return (total_value / total_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP), total_qty

        buy_vwap, total_buy_qty = vwap(buys)
        sell_vwap, total_sell_qty = vwap(sells)

        direction = 'long' if total_buy_qty >= total_sell_qty else 'short'

        if direction == 'long':
            entry_price = buy_vwap
            exit_price = sell_vwap if sells else None
            quantity = total_buy_qty
        else:
            entry_price = sell_vwap
            exit_price = buy_vwap if buys else None
            quantity = total_sell_qty

        # derive trade_date from the earliest leg date
        all_legs = buys + sells
        all_dates = [l['date'] for l in all_legs if l.get('date')]
        trade_date_raw = min(all_dates) if all_dates else ''
        if not trade_date_raw:
            continue

        all_times = [l['time'] for l in all_legs if l.get('time') is not None]
        trade_time_str = min(all_times).strftime('%H:%M') if all_times else ''

        normalized.append({
            'symbol': symbol,
            'trade_date': trade_date_raw,   # YYYY-MM-DD
            'time': trade_time_str,
            'direction': direction,
            'quantity': str(quantity),
            'entry_price': str(entry_price),
            'exit_price': str(exit_price) if exit_price is not None else '',
            'fees': '0',                    # Groww CSV has no fees column; user can edit
            'market_type': 'indian_stocks',
            'exchange': exchange,
            'segment': 'EQ',
        })

    return normalized


# ─────────────────────────────────────────────
# FILE PARSING HELPERS
# ─────────────────────────────────────────────

def _parse_csv(file):
    import csv

    content = file.read().decode('utf-8', errors='ignore')
    sample = content[:2048]
    delimiter = '\t' if sample.count('\t') > sample.count(',') else ','

    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    raw_data = list(reader)

    return _extract_rows_from_raw_data(raw_data)


def _parse_excel(file):
    try:
        import openpyxl
    except ImportError:
        raise ImportError('openpyxl not installed. Run: pip install openpyxl')

    wb = openpyxl.load_workbook(file, data_only=True)
    ws = wb.active
    raw_data = list(ws.iter_rows(values_only=True))

    return _extract_rows_from_raw_data(raw_data)


def _extract_rows_from_raw_data(raw_data):
    """Skip junk header rows (name, account info, blanks) and find the real column headers."""
    header_idx = 0
    for i, row in enumerate(raw_data):
        row_lower = [str(item).strip().lower() if item else '' for item in row]
        # 'symbol' or 'scrip' identifies the true header row
        if 'symbol' in row_lower or 'scrip' in row_lower:
            header_idx = i
            break

    if not raw_data or header_idx >= len(raw_data):
        return []

    headers = [str(h).strip().lower().replace(' ', '_') for h in raw_data[header_idx]]

    rows = []
    for row in raw_data[header_idx + 1:]:
        if any(row):  # skip entirely empty rows
            row_dict = dict(zip(headers, [str(v).strip() if v is not None else '' for v in row]))
            rows.append(row_dict)
    return rows


# ─────────────────────────────────────────────
# TRADE CREATION
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

    # Date parsing — Groww normalized outputs YYYY-MM-DD; Zerodha uses dd-mm-yyyy
    date_raw = row.get('date') or row.get('trade_date', '')
    trade_date = ddate.today()
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y'):
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
    return trade