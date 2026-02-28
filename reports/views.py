"""
Reports Module — all calculations from trade data, no stored reports.
All views accept: ?from=YYYY-MM-DD&to=YYYY-MM-DD&market=all&broker=all
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions
from rest_framework.response import Response
from django.db.models import Sum, Avg, Count, Max, Min, Q
from decimal import Decimal
from datetime import date, timedelta


def _get_filtered_trades(user, request):
    """Apply common query params: from, to, market, broker."""
    from tradelog.models import Trade
    qs = Trade.objects.filter(user=user, deleted_at__isnull=True)

    from_date = request.query_params.get('from')
    to_date = request.query_params.get('to')
    market = request.query_params.get('market')
    broker = request.query_params.get('broker')

    if from_date:
        qs = qs.filter(trade_date__gte=from_date)
    if to_date:
        qs = qs.filter(trade_date__lte=to_date)
    if market and market != 'all':
        qs = qs.filter(market_type=market)
    if broker and broker != 'all':
        qs = qs.filter(broker_name__iexact=broker)

    return qs


def _consecutive_streaks(values):
    """Returns (max_winning_streak, max_losing_streak) from a list of daily P&Ls."""
    max_win = max_loss = cur_win = cur_loss = 0
    for v in values:
        if v > 0:
            cur_win += 1; cur_loss = 0
        elif v < 0:
            cur_loss += 1; cur_win = 0
        else:
            cur_win = cur_loss = 0
        max_win = max(max_win, cur_win)
        max_loss = max(max_loss, cur_loss)
    return max_win, max_loss


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def performance_report_view(request):
    """GET /api/reports/performance/"""
    qs = _get_filtered_trades(request.user, request)
    total = qs.count()

    if total == 0:
        return Response({'message': 'No trades in the selected range.'})

    agg = qs.aggregate(
        net_pnl=Sum('total_pnl'),
        avg_trade_pnl=Avg('total_pnl'),
        largest_win=Max('total_pnl'),
        largest_loss=Min('total_pnl'),
        gross_profit=Sum('total_pnl', filter=Q(total_pnl__gt=0)),
        gross_loss=Sum('total_pnl', filter=Q(total_pnl__lt=0)),
        avg_win=Avg('total_pnl', filter=Q(total_pnl__gt=0)),
        avg_loss=Avg('total_pnl', filter=Q(total_pnl__lt=0)),
    )

    wins = qs.filter(total_pnl__gt=0).count()
    win_rate = round(wins / total * 100, 2) if total else 0

    gross_profit = agg['gross_profit'] or Decimal('0')
    gross_loss = abs(agg['gross_loss'] or Decimal('0'))
    profit_factor = round(float(gross_profit / gross_loss), 2) if gross_loss else 0
    expectancy = round(float(agg['net_pnl'] / total), 2) if total else 0

    # Daily stats
    from django.db.models.functions import TruncDate
    daily = qs.annotate(day=TruncDate('trade_date')) \
               .values('day').annotate(daily_pnl=Sum('total_pnl')).order_by('day')
    daily_list = list(daily)
    total_days = len(daily_list)
    winning_days = sum(1 for d in daily_list if d['daily_pnl'] > 0)
    losing_days = sum(1 for d in daily_list if d['daily_pnl'] < 0)
    avg_daily_pnl = round(float(agg['net_pnl']) / total_days, 2) if total_days else 0
    daily_pnls = [float(d['daily_pnl']) for d in daily_list]
    consecutive_wins, consecutive_losses = _consecutive_streaks(daily_pnls)

    # Best trading hour
    from django.db.models.functions import ExtractHour
    hour_pnl = qs.filter(trade_time__isnull=False).annotate(
        hour=ExtractHour('trade_time')
    ).values('hour').annotate(avg_pnl=Avg('total_pnl')).order_by('-avg_pnl')
    best_hour = hour_pnl.first()

    return Response({
        'total_trades': total,
        'net_pnl': agg['net_pnl'],
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'trade_expectancy': expectancy,
        'avg_trade_pnl': agg['avg_trade_pnl'],
        'avg_winning_trade': agg['avg_win'],
        'avg_losing_trade': agg['avg_loss'],
        'largest_winning_trade': agg['largest_win'],
        'largest_losing_trade': agg['largest_loss'],
        'total_trading_days': total_days,
        'winning_days': winning_days,
        'losing_days': losing_days,
        'avg_daily_pnl': avg_daily_pnl,
        'consecutive_win_days': consecutive_wins,
        'consecutive_loss_days': consecutive_losses,
        'best_trading_hour': best_hour,
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def risk_report_view(request):
    """GET /api/reports/risk/"""
    qs = _get_filtered_trades(request.user, request)
    if qs.count() == 0:
        return Response({'message': 'No trades in the selected range.'})

    agg = qs.aggregate(
        max_capital_used=Max('entry_price'),
        min_capital_used=Min('entry_price'),
        avg_capital_used=Avg('entry_price'),
        max_qty=Max('quantity'),
        avg_qty=Avg('quantity'),
    )

    # Max drawdown: peak-to-trough of cumulative P&L
    pnls = list(qs.values_list('total_pnl', flat=True).order_by('trade_date', 'trade_time'))
    cumulative = []
    running = Decimal('0')
    for p in pnls:
        if p:
            running += p
        cumulative.append(float(running))

    max_dd = 0
    peak = cumulative[0] if cumulative else 0
    for val in cumulative:
        if val > peak:
            peak = val
        dd = peak - val
        if dd > max_dd:
            max_dd = dd

    return Response({
        'max_drawdown': round(max_dd, 2),
        'max_capital_used': agg['max_capital_used'],
        'min_capital_used': agg['min_capital_used'],
        'avg_capital_used': agg['avg_capital_used'],
        'max_quantity': agg['max_qty'],
        'avg_quantity': agg['avg_qty'],
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def behavior_report_view(request):
    """GET /api/reports/behavior/ — returns 12 metric snapshot for user."""
    from insights.services import calculate_metrics
    from insights.serializers import MetricsSnapshotSerializer
    snapshot = calculate_metrics(request.user)
    return Response(MetricsSnapshotSerializer(snapshot).data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def strategy_report_view(request):
    """GET /api/reports/strategy/"""
    from strategies.models import Strategy
    from tradelog.models import Trade

    qs = _get_filtered_trades(request.user, request)
    strategy_ids = qs.values_list('strategy_id', flat=True).distinct()
    results = []

    for sid in strategy_ids:
        if not sid:
            continue
        strategy_trades = qs.filter(strategy_id=sid)
        total = strategy_trades.count()
        agg = strategy_trades.aggregate(
            total_pnl=Sum('total_pnl'),
            gross_profit=Sum('total_pnl', filter=Q(total_pnl__gt=0)),
            gross_loss=Sum('total_pnl', filter=Q(total_pnl__lt=0)),
        )
        wins = strategy_trades.filter(total_pnl__gt=0).count()
        gp = agg['gross_profit'] or Decimal('0')
        gl = abs(agg['gross_loss'] or Decimal('0'))

        try:
            strategy_name = Strategy.objects.get(pk=sid).strategy_name
        except Strategy.DoesNotExist:
            strategy_name = 'Unknown'

        results.append({
            'strategy_id': sid,
            'strategy_name': strategy_name,
            'total_trades': total,
            'win_rate': round(wins / total * 100, 2) if total else 0,
            'total_pnl': agg['total_pnl'],
            'profit_factor': round(float(gp / gl), 2) if gl else 0,
        })

    results.sort(key=lambda x: float(x['total_pnl'] or 0), reverse=True)
    return Response(results)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def journal_report_view(request):
    """GET /api/reports/journal/"""
    from journal.models import DailyJournal, PsychologyLog, SessionRecap
    from mistakes.models import TradeMistake
    from django.db.models import Count, Avg

    user = request.user
    from_date = request.query_params.get('from')
    to_date = request.query_params.get('to')

    def date_filter(qs, field='journal_date'):
        if from_date:
            qs = qs.filter(**{f'{field}__gte': from_date})
        if to_date:
            qs = qs.filter(**{f'{field}__lte': to_date})
        return qs

    journals = date_filter(DailyJournal.objects.filter(user=user))
    psych_logs = date_filter(PsychologyLog.objects.filter(user=user), 'log_date')
    recaps = date_filter(SessionRecap.objects.filter(user=user), 'recap_date')

    psych_agg = psych_logs.aggregate(
        avg_confidence=Avg('confidence_before'),
        avg_satisfaction=Avg('satisfaction_after'),
    )
    common_emotion = psych_logs.values('emotional_state').annotate(
        count=Count('id')).order_by('-count').first()

    recap_summary = recaps.values('outcome').annotate(count=Count('id'))
    recap_dist = {r['outcome']: r['count'] for r in recap_summary}

    return Response({
        'journal_streak': {
            'current': user.current_streak,
            'longest': user.longest_streak,
        },
        'journal_count': journals.count(),
        'psychology_summary': {
            **psych_agg,
            'most_common_emotion': common_emotion['emotional_state'] if common_emotion else None,
        },
        'session_recap_summary': {
            'good': recap_dist.get('good', 0),
            'neutral': recap_dist.get('neutral', 0),
            'bad': recap_dist.get('bad', 0),
        },
    })
