"""
Insights Service — Calculates all 12 proprietary BitsOfTrade metrics.
Called from reports/views.py behavior_report_view and insights/views.py.
"""
from decimal import Decimal
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from datetime import date, timedelta


def calculate_metrics(user, snapshot_date=None):
    """Calculate and cache all 12 metrics into UserMetricSnapshot."""
    from .models import UserMetricSnapshot
    from discipline.models import DisciplineSession
    from tradelog.models import Trade
    from strategies.models import Strategy

    if snapshot_date is None:
        snapshot_date = date.today()

    sessions = DisciplineSession.objects.filter(user=user)
    trades = Trade.objects.filter(user=user, deleted_at__isnull=True)

    snapshot, _ = UserMetricSnapshot.objects.get_or_create(
        user=user, snapshot_date=snapshot_date
    )

    total_sessions = sessions.count()

    # ──── 1. Discipline Integrity Score (DI) ────
    green_sessions = sessions.filter(session_state='green').count()
    snapshot.di_score = round(green_sessions / total_sessions * 100, 2) if total_sessions else Decimal('0')

    # ──── 2. Violation Momentum Index (VMI) ────
    today = date.today()
    last7_end = today
    last7_start = today - timedelta(days=7)
    prev7_start = today - timedelta(days=14)

    last7_violations = sessions.filter(session_date__gte=last7_start).aggregate(
        total=Sum('violations_count'))['total'] or 0
    prev7_violations = sessions.filter(
        session_date__gte=prev7_start, session_date__lt=last7_start
    ).aggregate(total=Sum('violations_count'))['total'] or 0

    if last7_violations > prev7_violations:
        snapshot.vmi_level = 'High'
    elif last7_violations < prev7_violations:
        snapshot.vmi_level = 'Low'
    else:
        snapshot.vmi_level = 'Medium'

    # ──── 3. Discipline Recovery Time (DRT) ────
    non_green = sessions.exclude(session_state='green').filter(unlocked_at__isnull=False)
    recovery_times = []
    for s in non_green:
        if s.unlocked_at and s.created_at:
            delta = (s.unlocked_at - s.created_at).days
            recovery_times.append(delta)
    snapshot.drt_days = round(sum(recovery_times) / len(recovery_times), 2) if recovery_times else Decimal('0')

    # ──── 4. Trade Permission Ratio (TPR) ────
    green_session_ids = sessions.filter(session_state='green').values_list('id', flat=True)
    green_trades = trades.filter(session_id__in=green_session_ids).count()
    total_trades = trades.count()
    snapshot.tpr_score = round(green_trades / total_trades * 100, 2) if total_trades else Decimal('0')

    # ──── 5. Foregone Impact of Emotions (FIE) ────
    emotional_violations = ['fomo', 'anxious', 'fearful', 'angry']
    fie = trades.filter(
        emotional_state__in=emotional_violations,
        total_pnl__lt=0
    ).aggregate(total=Sum('total_pnl'))['total'] or Decimal('0')
    snapshot.fie_amount = fie  # Always negative (loss)

    # ──── 6. Obstinacy vs Resilience Score (OVR) ────
    red_sessions = sessions.filter(session_state='red')
    recovered = red_sessions.filter(unlocked_at__isnull=False).count()
    total_red = red_sessions.count()
    if total_red > 0:
        resilience_ratio = recovered / total_red
        snapshot.ovr_score = round(Decimal(str(resilience_ratio)) * 10, 2)
    else:
        snapshot.ovr_score = Decimal('5')

    # ──── 7. Emotion Cost Index (ECI) ────
    bad_emotions = ['anxious', 'fearful', 'angry', 'fomo']
    good_emotions = ['calm', 'confident']
    bad_pnl = trades.filter(emotional_state__in=bad_emotions).aggregate(total=Sum('total_pnl'))['total'] or Decimal('0')
    good_pnl = trades.filter(emotional_state__in=good_emotions).aggregate(total=Sum('total_pnl'))['total'] or Decimal('0')
    snapshot.eci_amount = bad_pnl - good_pnl  # Negative = bad emotions cost money

    # ──── 8. Confidence Accuracy Score (CAS) ────
    confident_wins = trades.filter(entry_confidence__gte=7, total_pnl__gt=0).count()
    confident_total = trades.filter(entry_confidence__gte=7).count()
    low_conf_losses = trades.filter(entry_confidence__lte=3, total_pnl__lt=0).count()
    low_conf_total = trades.filter(entry_confidence__lte=3).count()
    if confident_total + low_conf_total > 0:
        cas = (confident_wins + low_conf_losses) / (confident_total + low_conf_total) * 100
        snapshot.cas_score = round(Decimal(str(cas)), 2)
    else:
        snapshot.cas_score = Decimal('0')

    # ──── 9. Disciplined Expectancy (DAE) ────
    green_trades_qs = trades.filter(session_id__in=green_session_ids)
    dae_agg = green_trades_qs.aggregate(avg_pnl=Avg('total_pnl'))
    snapshot.dae_r = round(Decimal(str(dae_agg['avg_pnl'] or 0)), 2)

    # ──── 10. Strategy Maturity Index (SMI) ────
    top_strategy = trades.values('strategy_id').annotate(
        count=Count('id')).order_by('-count').first()
    if top_strategy and top_strategy['strategy_id']:
        try:
            from strategies.models import Strategy
            strat = Strategy.objects.get(pk=top_strategy['strategy_id'])
            snapshot.smi_status = strat.maturity_status
        except Strategy.DoesNotExist:
            snapshot.smi_status = 'Testing'
    else:
        snapshot.smi_status = 'Testing'

    # ──── 11. Discipline Dependency Ratio (DDR) ────
    green_win_rate = 0
    non_green_win_rate = 0
    non_green_session_ids = sessions.exclude(session_state='green').values_list('id', flat=True)
    non_green_trades = trades.filter(session_id__in=non_green_session_ids)

    if green_trades_qs.count() > 0:
        green_win_rate = green_trades_qs.filter(total_pnl__gt=0).count() / green_trades_qs.count() * 100
    if non_green_trades.count() > 0:
        non_green_win_rate = non_green_trades.filter(total_pnl__gt=0).count() / non_green_trades.count() * 100

    ddr = abs(green_win_rate - non_green_win_rate)
    if ddr < 10:
        snapshot.ddr_level = 'Low'
    elif ddr < 25:
        snapshot.ddr_level = 'Medium'
    else:
        snapshot.ddr_level = 'High'

    # ──── 12. Capital Protection Index (CPI) ────
    if user.trading_capital:
        from rules.models import Rule
        from django.db.models import Sum
        max_daily_rule = Rule.objects.filter(
            Q(is_admin_defined=True) | Q(user=user),
            category='risk',
            is_active=True,
            deleted_at__isnull=True
        ).filter(trigger_condition__has_key='maxDailyPercent').first()

        if max_daily_rule:
            max_pct = Decimal(str(max_daily_rule.trigger_condition.get('maxDailyPercent', 3)))
            max_loss_allowed = user.trading_capital * max_pct / 100

            # Get daily P&L
            from django.db.models.functions import TruncDate
            daily_pnls = trades.annotate(day=TruncDate('trade_date')).values('day').annotate(
                daily_pnl=Sum('total_pnl')
            )
            compliant_days = sum(1 for d in daily_pnls if d['daily_pnl'] >= -max_loss_allowed)
            total_days = daily_pnls.count()
            snapshot.cpi_score = round(
                Decimal(str(compliant_days / total_days * 100)), 2
            ) if total_days else Decimal('0')
        else:
            snapshot.cpi_score = Decimal('100')
    else:
        snapshot.cpi_score = None

    snapshot.save()
    return snapshot
