from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from django.db.models import Sum, Count, Q
from tradelog.models import Trade
import calendar
from datetime import date


# ─────────────────────────────────────────────
# TRADE DISTRIBUTION
# GET /api/tradelog/trades/distribution/
# ─────────────────────────────────────────────

class TradeDistributionView(APIView):
    """
    Returns trade distribution breakdown by market segment and direction.

    Query params (all optional, combinable):
        date_range  : today | this_week | this_month | custom
        date_from   : YYYY-MM-DD  (used when date_range=custom)
        date_to     : YYYY-MM-DD  (used when date_range=custom)

    Response shape:
    {
        "total_trades": 70,
        "by_segment": [
            { "market_type": "indian_market", "label": "Indian Market", "trade_count": 40, "total_pnl": 12500.00, "percentage": 57.1 },
            { "market_type": "forex",         "label": "Forex",         "trade_count": 20, "total_pnl": -800.00,  "percentage": 28.6 },
            { "market_type": "crypto",        "label": "Crypto",        "trade_count": 8,  "total_pnl": 300.00,   "percentage": 11.4 },
            { "market_type": "options",       "label": "Options",       "trade_count": 2,  "total_pnl": 0.00,     "percentage": 2.9  }
        ],
        "by_direction": {
            "long":  { "trade_count": 50, "total_pnl": 8000.00, "percentage": 71.4 },
            "short": { "trade_count": 20, "total_pnl": 2500.00, "percentage": 28.6 }
        }
    }

    Notes:
    - All 4 segments are always returned even if trade_count = 0.
    - percentage is relative to total_trades across all segments.
    """
    permission_classes = [permissions.IsAuthenticated]

    # All 4 segments in fixed order — always returned even if count = 0
    SEGMENTS = [
        ('indian_market', 'Indian Market'),
        ('forex',         'Forex'),
        ('crypto',        'Crypto'),
        ('options',       'Options'),
    ]

    def _apply_date_filter(self, qs, params):
        from datetime import timedelta
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
            date_to   = params.get('date_to', '').strip()
            if date_from:
                qs = qs.filter(trade_date__gte=date_from)
            if date_to:
                qs = qs.filter(trade_date__lte=date_to)

        return qs

    def get(self, request, *args, **kwargs):
        base_qs = Trade.objects.filter(
            user=request.user,
            deleted_at__isnull=True,
        )
        base_qs = self._apply_date_filter(base_qs, request.query_params)

        total_trades = base_qs.count()

        # ── By Segment ──────────────────────────────────────────────────────
        segment_rows = (
            base_qs
            .values('market_type')
            .annotate(
                trade_count=Count('id'),
                pnl_sum=Sum('total_pnl'),
            )
        )
        # Index by market_type for O(1) lookup
        segment_map = {r['market_type']: r for r in segment_rows}

        # Always return all 4 segments in fixed order
        by_segment = []
        for market_type, label in self.SEGMENTS:
            row   = segment_map.get(market_type)
            count = row['trade_count'] if row else 0
            pnl   = float(row['pnl_sum']) if row and row['pnl_sum'] is not None else 0.0
            pct   = round((count / total_trades * 100), 1) if total_trades else 0.0
            by_segment.append({
                'market_type': market_type,
                'label':       label,
                'trade_count': count,
                'total_pnl':   round(pnl, 2),
                'percentage':  pct,
            })

        # ── By Direction ─────────────────────────────────────────────────────
        direction_rows = (
            base_qs
            .values('direction')
            .annotate(
                trade_count=Count('id'),
                pnl_sum=Sum('total_pnl'),
            )
        )
        direction_map = {r['direction']: r for r in direction_rows}

        def _dir_data(direction_key):
            row = direction_map.get(direction_key)
            if not row:
                return {'trade_count': 0, 'total_pnl': 0.0, 'percentage': 0.0}
            count = row['trade_count']
            pnl   = float(row['pnl_sum']) if row['pnl_sum'] is not None else 0.0
            pct   = round((count / total_trades * 100), 1) if total_trades else 0.0
            return {'trade_count': count, 'total_pnl': round(pnl, 2), 'percentage': pct}

        by_direction = {
            'long':  _dir_data('long'),
            'short': _dir_data('short'),
        }

        return Response({
            'total_trades': total_trades,
            'by_segment':   by_segment,
            'by_direction': by_direction,
        })


# ─────────────────────────────────────────────
# TRADE CALENDAR
# GET /api/tradelog/trades/calendar/
# ─────────────────────────────────────────────

class TradeCalendarView(APIView):
    """
    Returns a per-day summary of trades for a given month/year,
    formatted for calendar rendering.

    Query params:
        year   : int  (default: current year)
        month  : int  (default: current month)

    Response shape:
    {
        "year": 2025,
        "month": 11,
        "month_name": "November",
        "weeks": [
            [
                null,                        <- day outside the month (padding)
                {
                    "date": "2025-11-01",
                    "day": 1,
                    "trade_count": 3,
                    "total_pnl": 1500.00,
                    "outcome": "profit",     <- profit | loss | breakeven | no_trades
                    "wins": 2,
                    "losses": 1
                },
                ...
            ],
            ...
        ],
        "summary": {
            "total_trades": 45,
            "total_pnl": 12500.00,
            "profit_days": 14,
            "loss_days": 6,
            "breakeven_days": 1,
            "trading_days": 21
        }
    }

    Notes:
    - weeks is a 2D array: rows x 7 columns (Sun -> Sat).
    - null means the day falls outside the requested month.
    - outcome is based on the sum of total_pnl for that day.
    - wins/losses are individual trade counts (not day counts).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        today = date.today()

        try:
            year  = int(request.query_params.get('year',  today.year))
            month = int(request.query_params.get('month', today.month))
        except (ValueError, TypeError):
            return Response(
                {'error': 'year and month must be valid integers.'},
                status=400,
            )

        if not (1 <= month <= 12):
            return Response({'error': 'month must be between 1 and 12.'}, status=400)

        # ── Single query for all days in the month ───────────────────────────
        # pnl_sum is named differently from the model field 'total_pnl'
        # to avoid annotation name collision inside Count(filter=Q(...))
        trades_qs = (
            Trade.objects
            .filter(
                user=request.user,
                deleted_at__isnull=True,
                trade_date__year=year,
                trade_date__month=month,
            )
            .values('trade_date')
            .annotate(
                trade_count=Count('id'),
                pnl_sum=Sum('total_pnl'),
                wins=Count('id', filter=Q(total_pnl__gt=0)),
                losses=Count('id', filter=Q(total_pnl__lt=0)),
            )
        )

        # Index by day number for O(1) calendar grid lookup
        day_data = {}
        for row in trades_qs:
            d   = row['trade_date']
            pnl = float(row['pnl_sum']) if row['pnl_sum'] is not None else 0.0

            if pnl > 0:
                outcome = 'profit'
            elif pnl < 0:
                outcome = 'loss'
            else:
                outcome = 'breakeven'

            day_data[d.day] = {
                'date':        d.isoformat(),
                'day':         d.day,
                'trade_count': row['trade_count'],
                'total_pnl':   round(pnl, 2),
                'outcome':     outcome,
                'wins':        row['wins'],
                'losses':      row['losses'],
            }

        # ── Build calendar grid (Sun -> Sat) ──────────────────────────────────
        cal = calendar.Calendar(firstweekday=6)  # 6 = Sunday
        month_weeks = cal.monthdayscalendar(year, month)

        weeks = []
        for week in month_weeks:
            week_row = []
            for day_num in week:
                if day_num == 0:
                    # Padding — day outside this month
                    week_row.append(None)
                elif day_num in day_data:
                    week_row.append(day_data[day_num])
                else:
                    week_row.append({
                        'date':        date(year, month, day_num).isoformat(),
                        'day':         day_num,
                        'trade_count': 0,
                        'total_pnl':   0.0,
                        'outcome':     'no_trades',
                        'wins':        0,
                        'losses':      0,
                    })
            weeks.append(week_row)

        # ── Month-level summary ───────────────────────────────────────────────
        total_trades   = sum(v['trade_count'] for v in day_data.values())
        total_pnl      = round(sum(v['total_pnl'] for v in day_data.values()), 2)
        profit_days    = sum(1 for v in day_data.values() if v['outcome'] == 'profit')
        loss_days      = sum(1 for v in day_data.values() if v['outcome'] == 'loss')
        breakeven_days = sum(1 for v in day_data.values() if v['outcome'] == 'breakeven')

        return Response({
            'year':       year,
            'month':      month,
            'month_name': calendar.month_name[month],
            'weeks':      weeks,
            'summary': {
                'total_trades':   total_trades,
                'total_pnl':      total_pnl,
                'profit_days':    profit_days,
                'loss_days':      loss_days,
                'breakeven_days': breakeven_days,
                'trading_days':   len(day_data),
            },
        })