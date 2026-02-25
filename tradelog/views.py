from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils import timezone
from tradelog.models import Trade
from tradelog.serializers import TradeManagementSerializer
from .pagination import StandardResultsSetPagination
from decimal import Decimal
import io


class TradeListCreateView(generics.ListCreateAPIView):
    """GET /api/tradelog/trades/  POST /api/tradelog/trades/"""
    serializer_class = TradeManagementSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Trade.objects.filter(user=self.request.user, deleted_at__isnull=True)
        # Filters: wins / losses / disciplined / violations
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


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def trade_import_view(request):
    """
    POST /api/tradelog/trades/import/
    Accepts CSV or Excel file. Parses and imports trades.
    Expected columns: symbol, date, time, direction, quantity, entry_price, exit_price, fees
    """
    file = request.FILES.get('file')
    if not file:
        return Response({'error': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

    broker_name = request.data.get('broker_name', '')
    filename = file.name.lower()

    try:
        if filename.endswith('.csv'):
            rows = _parse_csv(file)
        elif filename.endswith(('.xlsx', '.xls')):
            rows = _parse_excel(file)
        else:
            return Response({'error': 'Unsupported file type. Upload CSV or Excel.'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': f'File parsing failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    created_trades = []
    errors = []

    for i, row in enumerate(rows, start=1):
        try:
            trade = _create_trade_from_row(row, request.user, broker_name)
            created_trades.append(trade)
        except Exception as e:
            errors.append({'row': i, 'error': str(e), 'data': row})

    return Response({
        'imported': len(created_trades),
        'failed': len(errors),
        'errors': errors[:10],  # Return max 10 sample errors
        'message': f'{len(created_trades)} trades imported successfully.'
    }, status=status.HTTP_201_CREATED)


def _parse_csv(file):
    import csv
    content = file.read().decode('utf-8', errors='ignore')
    reader = csv.DictReader(io.StringIO(content))
    # Normalize headers to lowercase
    rows = []
    for row in reader:
        rows.append({k.strip().lower().replace(' ', '_'): v.strip() for k, v in row.items()})
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


def _create_trade_from_row(row, user, broker_name):
    """Create a Trade from a parsed CSV/Excel row dict."""
    from datetime import datetime, date as ddate
    from discipline.models import DisciplineSession

    # Required fields
    symbol = row.get('symbol') or row.get('scrip', '')
    direction = (row.get('direction') or row.get('trade_type', 'long')).lower()
    quantity = Decimal(str(row.get('quantity') or row.get('qty', 1)))
    entry_price = Decimal(str(row.get('entry_price') or row.get('buy_price', 0)))
    exit_price_raw = row.get('exit_price') or row.get('sell_price', '')
    exit_price = Decimal(str(exit_price_raw)) if exit_price_raw else None
    fees = Decimal(str(row.get('fees') or row.get('brokerage', 0)))

    # Date
    date_raw = row.get('date') or row.get('trade_date', '')
    try:
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y'):
            try:
                trade_date = datetime.strptime(date_raw, fmt).date()
                break
            except ValueError:
                continue
        else:
            trade_date = ddate.today()
    except Exception:
        trade_date = ddate.today()

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