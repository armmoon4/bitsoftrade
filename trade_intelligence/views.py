from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions
from rest_framework.response import Response
from django.db.models import Sum, Count, Avg, Q
from decimal import Decimal
from datetime import date, timedelta


def _parse_date_range(request):
    time_range = request.data.get('timeRange', 'last30')
    from_date = request.data.get('fromDate')
    to_date = request.data.get('toDate')
    today = date.today()

    if time_range == 'last7':
        return today - timedelta(days=7), today
    elif time_range == 'last30':
        return today - timedelta(days=30), today
    elif time_range == 'last90':
        return today - timedelta(days=90), today
    elif time_range == 'last365':
        return today - timedelta(days=365), today
    elif from_date and to_date:
        from datetime import datetime
        return datetime.strptime(from_date, '%Y-%m-%d').date(), datetime.strptime(to_date, '%Y-%m-%d').date()
    else:
        return today - timedelta(days=30), today


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def analyze_view(request):
    """
    POST /api/trade-intelligence/analyze/
    Body: { timeRange: 'last7'|'last30'|'last90'|'last365'|'custom', fromDate, toDate }
    Returns predefined analysis points.
    """
    from tradelog.models import Trade
    from mistakes.models import TradeMistake
    from strategies.models import Strategy
    from discipline.models import DisciplineSession
    from django.db.models.functions import ExtractHour, TruncDate

    user = request.user
    start, end = _parse_date_range(request)

    trades = Trade.objects.filter(
        user=user, trade_date__gte=start, trade_date__lte=end, deleted_at__isnull=True
    )
    total = trades.count()

    if total == 0:
        return Response({'message': 'No trades in the selected range.'})

    # Win/Loss Ratio
    wins = trades.filter(total_pnl__gt=0).count()
    losses = trades.filter(total_pnl__lte=0).count()

    # Over-trading detection
    sessions_in_range = DisciplineSession.objects.filter(
        user=user, session_date__gte=start, session_date__lte=end
    )
    from rules.models import Rule
    max_trades_rule = Rule.objects.filter(
        Q(is_admin_defined=True) | Q(user=user),
        is_active=True, deleted_at__isnull=True,
        trigger_condition__has_key='maxTrades'
    ).first()
    overtrade_days = 0
    if max_trades_rule:
        max_t = int(max_trades_rule.trigger_condition.get('maxTrades', 10))
        daily_counts = trades.annotate(day=TruncDate('trade_date')).values('day').annotate(
            count=Count('id')
        )
        overtrade_days = sum(1 for d in daily_counts if d['count'] > max_t)

    # Best/Worst strategy
    strategy_pnl = trades.values('strategy_id', 'strategy__strategy_name').annotate(
        total_pnl=Sum('total_pnl'), trade_count=Count('id')
    ).exclude(strategy_id__isnull=True).order_by('-total_pnl')
    best_strategy = strategy_pnl.first()
    worst_strategy = strategy_pnl.last()

    # Most common mistake
    trade_ids = trades.values_list('id', flat=True)
    top_mistake = TradeMistake.objects.filter(
        trade_id__in=trade_ids
    ).values('mistake__mistake_name').annotate(
        count=Count('id')
    ).order_by('-count').first()

    # Emotion impact
    green_ids = DisciplineSession.objects.filter(
        user=user, session_date__gte=start, session_date__lte=end, session_state='green'
    ).values_list('id', flat=True)
    disciplined_pnl = trades.filter(session_id__in=green_ids).aggregate(total=Sum('total_pnl'))['total'] or 0
    undisciplined_pnl = trades.exclude(session_id__in=green_ids).aggregate(total=Sum('total_pnl'))['total'] or 0

    # Best trading hours
    hourly = trades.filter(trade_time__isnull=False).annotate(
        hour=ExtractHour('trade_time')
    ).values('hour').annotate(avg_pnl=Avg('total_pnl')).order_by('hour')

    # Streak analysis
    from reports.views import _consecutive_streaks
    daily_pnls_data = trades.annotate(day=TruncDate('trade_date')).values('day').annotate(
        daily_pnl=Sum('total_pnl')
    ).order_by('day')
    daily_pnls_list = [float(d['daily_pnl']) for d in daily_pnls_data]
    max_win_streak, max_loss_streak = _consecutive_streaks(daily_pnls_list)

    # Improvement score: compare DI in first vs second half of period
    mid = start + (end - start) / 2
    first_half_sessions = DisciplineSession.objects.filter(
        user=user, session_date__gte=start, session_date__lt=mid
    )
    second_half_sessions = DisciplineSession.objects.filter(
        user=user, session_date__gte=mid, session_date__lte=end
    )
    def di(sess_qs):
        total = sess_qs.count()
        green = sess_qs.filter(session_state='green').count()
        return round(green / total * 100, 2) if total else 0
    first_di = di(first_half_sessions)
    second_di = di(second_half_sessions)

    return Response({
        'period': {'from': start, 'to': end, 'total_trades': total},
        'win_loss_ratio': {'wins': wins, 'losses': losses, 'ratio': round(wins / losses, 2) if losses else wins},
        'overtrading': {'days_over_limit': overtrade_days},
        'best_performing_strategy': best_strategy,
        'worst_performing_strategy': worst_strategy,
        'most_common_mistake': top_mistake,
        'emotion_impact_summary': {
            'disciplined_pnl': disciplined_pnl,
            'undisciplined_pnl': undisciplined_pnl,
            'difference': float(disciplined_pnl) - float(undisciplined_pnl),
        },
        'best_trading_hours': list(hourly),
        'streak_analysis': {
            'longest_winning_streak': max_win_streak,
            'longest_losing_streak': max_loss_streak,
        },
        'improvement_score': {
            'first_half_di': first_di,
            'second_half_di': second_di,
            'trend': 'Improving' if second_di > first_di else ('Declining' if second_di < first_di else 'Stable'),
        },
    })
