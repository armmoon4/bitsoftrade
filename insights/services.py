"""
Insights Service — Calculates all 12 proprietary BitsOfTrade metrics.
Called from insights/views.py.

Metric definitions:
  1.  DIS™  — Discipline Integrity Score         (0-100, weighted penalties)
  2.  VMI   — Violation Momentum Index            (0-100 numeric + Low/Med/High)
  3.  DRT   — Discipline Recovery Time            (avg sessions to recover)
  4.  TPR   — Trading Permission Ratio            (% of GREEN sessions)
  5.  FIE   — Forced Inactivity Effectiveness     (avg-loss × red-session-count)
  6.  OVR   — Override Resistance Score           (1-10, higher = better)
  7.  ECI   — Emotion Cost Index                  (INR losses on negative emotions)
  8.  CAS   — Confidence Accuracy Score           (0-100%)
  9.  DAE   — Discipline-Adjusted Expectancy      (raw vs disciplined avg P&L)
  10. SMI   — Strategy Maturity Index             (0-100 weighted score)
  11. DDR   — Discipline Dependency Ratio         (numeric % + Low/Med/High)
  12. CPI   — Capital Protection Index            (% days within loss rule)
"""
from decimal import Decimal
from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import date, timedelta


def calculate_metrics(user, snapshot_date=None):
    """Calculate and persist all 12 metrics into UserMetricSnapshot."""
    from .models import UserMetricSnapshot
    from discipline.models import DisciplineSession, ViolationsLog
    from tradelog.models import Trade

    if snapshot_date is None:
        snapshot_date = date.today()

    sessions = DisciplineSession.objects.filter(user=user)
    trades = Trade.objects.filter(user=user, deleted_at__isnull=True)

    # Always recalculate — use update_or_create so stale cache is overwritten
    snapshot, _ = UserMetricSnapshot.objects.update_or_create(
        user=user, snapshot_date=snapshot_date,
        defaults={}  # fields populated below then snapshot.save() called at end
    )

    total_sessions = sessions.count()
    total_trades = trades.count()

    # Pre-compute session id sets for reuse
    green_session_ids = list(sessions.filter(peak_state='green').values_list('id', flat=True))
    non_green_session_ids = list(
        sessions.exclude(peak_state='green').values_list('id', flat=True)
    )

    green_trades_qs = trades.filter(session_id__in=green_session_ids)

    # ────────────────────────────────────────────────────────────────────────
    # 1. DIS™ — Discipline Integrity Score
    # Formula: 100 − weighted penalties
    #   • Each unique rule violated in a session:  -5 points
    #   • Each hard (RED-triggering) violation:    -3 extra points
    #   • Sessions that have >1 violation day:     -2 points per recurrence
    # Capped at 0 (never goes negative).
    # ────────────────────────────────────────────────────────────────────────
    total_rule_breaches = sessions.aggregate(
        total=Sum('violations_count'))['total'] or 0
    total_hard = sessions.aggregate(
        total=Sum('hard_violations'))['total'] or 0

    # Count sessions with violations (sessions where rules were broken)
    sessions_with_violations = sessions.filter(violations_count__gt=0).count()
    # Recurrences: sessions where same pattern repeated (>1 violation in session)
    recurrence_sessions = sessions.filter(violations_count__gt=1).count()

    penalty = (
        (total_rule_breaches * 5) +   # each breach
        (total_hard * 3) +             # extra for hard violations
        (recurrence_sessions * 2)      # repeated mistakes
    )
    raw_di = Decimal('100') - Decimal(str(penalty))
    snapshot.di_score = max(raw_di, Decimal('0'))

    # ────────────────────────────────────────────────────────────────────────
    # 2. VMI — Violation Momentum Index
    # Compare last 7 days violations vs prior 7 days.
    # Score 0-100: higher = more momentum / worse.
    # ────────────────────────────────────────────────────────────────────────
    today = date.today()
    last7_start = today - timedelta(days=7)
    prev7_start = today - timedelta(days=14)

    last7_violations = sessions.filter(session_date__gte=last7_start).aggregate(
        total=Sum('violations_count'))['total'] or 0
    prev7_violations = sessions.filter(
        session_date__gte=prev7_start, session_date__lt=last7_start
    ).aggregate(total=Sum('violations_count'))['total'] or 0

    # Normalise to 0-100 based on comparison
    if prev7_violations == 0 and last7_violations == 0:
        vmi_score = Decimal('0')
    elif prev7_violations == 0:
        vmi_score = Decimal('100')
    else:
        ratio = last7_violations / prev7_violations
        vmi_score = min(round(Decimal(str(ratio)) * 50, 2), Decimal('100'))

    snapshot.vmi_score = vmi_score
    if vmi_score >= 75:
        snapshot.vmi_level = 'High'
    elif vmi_score >= 35:
        snapshot.vmi_level = 'Medium'
    else:
        snapshot.vmi_level = 'Low'

    # ────────────────────────────────────────────────────────────────────────
    # 3. DRT — Discipline Recovery Time
    # Avg number of sessions between a violation day and the next clean session.
    # ────────────────────────────────────────────────────────────────────────
    all_sessions_ordered = list(
        sessions.order_by('session_date').values('session_date', 'peak_state')
    )
    recovery_session_counts = []
    in_violation = False
    violation_session_idx = None

    for idx, s in enumerate(all_sessions_ordered):
        if not in_violation and s['peak_state'] != 'green':
            in_violation = True
            violation_session_idx = idx
        elif in_violation and s['peak_state'] == 'green':
            sessions_to_recover = idx - violation_session_idx
            recovery_session_counts.append(sessions_to_recover)
            in_violation = False
            violation_session_idx = None

    snapshot.drt_days = (
        round(Decimal(str(sum(recovery_session_counts) / len(recovery_session_counts))), 2)
        if recovery_session_counts else Decimal('0')
    )

    # ────────────────────────────────────────────────────────────────────────
    # 4. TPR — Trading Permission Ratio
    # % of SESSIONS that were GREEN (by peak_state).
    # Formula: green_sessions / total_sessions × 100
    # ────────────────────────────────────────────────────────────────────────
    green_sessions_count = sessions.filter(peak_state='green').count()
    snapshot.tpr_score = (
        round(Decimal(str(green_sessions_count / total_sessions * 100)), 2)
        if total_sessions else Decimal('0')
    )

    # ────────────────────────────────────────────────────────────────────────
    # 5. FIE — Forced Inactivity Effectiveness
    # Estimated INR saved by RED sessions (forced stops).
    # Formula: avg_daily_loss_on_violation_days × red_session_count
    # ────────────────────────────────────────────────────────────────────────
    red_sessions = sessions.filter(peak_state='red')
    red_count = red_sessions.count()
    red_session_dates = list(red_sessions.values_list('session_date', flat=True))

    if red_session_dates:
        # Average loss on violation days
        red_day_pnl = trades.filter(
            trade_date__in=red_session_dates, total_pnl__lt=0
        ).aggregate(avg=Avg('total_pnl'))['avg'] or Decimal('0')
        snapshot.fie_amount = abs(Decimal(str(red_day_pnl))) * red_count
    else:
        snapshot.fie_amount = Decimal('0')

    # ────────────────────────────────────────────────────────────────────────
    # 6. OVR — Override Resistance Score (1-10)
    # Measures how often user fights the system (ignored warnings / traded while RED).
    # Proxy: trades taken during RED sessions / total red session trades × scale.
    # Higher = better discipline (resisted more).
    # ────────────────────────────────────────────────────────────────────────
    red_session_ids = list(red_sessions.values_list('id', flat=True))
    red_session_total_trades = trades.filter(session_id__in=red_session_ids).count()

    # We don't have an explicit "override attempt" field; use red-session trade count
    # as proxy: 0 trades in RED = perfect override resistance (10/10).
    if red_count == 0:
        snapshot.ovr_score = Decimal('10')
    else:
        override_attempts = red_session_total_trades
        penalty_per_attempt = Decimal('0.5')
        ovr = Decimal('10') - (Decimal(str(override_attempts)) * penalty_per_attempt)
        snapshot.ovr_score = max(round(ovr, 2), Decimal('1'))

    # ────────────────────────────────────────────────────────────────────────
    # 7. ECI — Emotion Cost Index
    # Sum of P&L losses on trades tagged with negative emotional states.
    # Negative value = money lost due to emotion.
    # ────────────────────────────────────────────────────────────────────────
    negative_emotions = ['fomo', 'anxious', 'fearful', 'angry', 'overconfident']
    eci = trades.filter(
        emotional_state__in=negative_emotions,
        total_pnl__lt=0
    ).aggregate(total=Sum('total_pnl'))['total'] or Decimal('0')
    snapshot.eci_amount = eci  # Already negative

    # ────────────────────────────────────────────────────────────────────────
    # 8. CAS — Confidence Accuracy Score
    # Correlation between pre-trade confidence rating and actual outcome.
    # High confidence (7-10) wins + Low confidence (1-3) losses as % of all such trades.
    # ────────────────────────────────────────────────────────────────────────
    confident_wins = trades.filter(entry_confidence__gte=7, total_pnl__gt=0).count()
    confident_total = trades.filter(entry_confidence__gte=7).count()
    low_conf_losses = trades.filter(entry_confidence__lte=3, total_pnl__lt=0).count()
    low_conf_total = trades.filter(entry_confidence__lte=3).count()

    denominator = confident_total + low_conf_total
    if denominator > 0:
        cas = (confident_wins + low_conf_losses) / denominator * 100
        snapshot.cas_score = round(Decimal(str(cas)), 2)
    else:
        snapshot.cas_score = Decimal('0')

    # ────────────────────────────────────────────────────────────────────────
    # 9. DAE — Discipline-Adjusted Expectancy
    # dae_r   = avg P&L per disciplined trade (GREEN sessions only)
    # dae_raw = avg P&L per trade across ALL trades
    # ────────────────────────────────────────────────────────────────────────
    raw_avg = trades.aggregate(avg=Avg('total_pnl'))['avg'] or Decimal('0')
    snapshot.dae_raw = round(Decimal(str(raw_avg)), 2)

    disciplined_avg = green_trades_qs.aggregate(avg=Avg('total_pnl'))['avg'] or Decimal('0')
    snapshot.dae_r = round(Decimal(str(disciplined_avg)), 2)

    # ────────────────────────────────────────────────────────────────────────
    # 10. SMI — Strategy Maturity Index
    # Weighted score (0-100) for the user's most-used strategy.
    #   sample_size  30% — based on sample_size_threshold progress
    #   win_rate     25% — % winning trades for the strategy
    #   emotional    25% — % of strategy trades with calm/confident state
    #   rule_adhere  20% — % of strategy trades that were disciplined
    # ────────────────────────────────────────────────────────────────────────
    top_strategy_agg = (
        trades.exclude(strategy__isnull=True)
              .values('strategy_id', 'strategy__strategy_name',
                      'strategy__sample_size_threshold', 'strategy__maturity_status')
              .annotate(count=Count('id'))
              .order_by('-count')
              .first()
    )

    if top_strategy_agg and top_strategy_agg['strategy_id']:
        st_qs = trades.filter(strategy_id=top_strategy_agg['strategy_id'])
        st_count = top_strategy_agg['count']
        threshold = top_strategy_agg['strategy__sample_size_threshold'] or 30

        sample_pct = min((st_count / threshold) * 100, 100) if threshold else 0
        win_pct = (st_qs.filter(total_pnl__gt=0).count() / st_count * 100) if st_count else 0
        calm_pct = (
            st_qs.filter(emotional_state__in=['calm', 'confident']).count() / st_count * 100
        ) if st_count else 0
        disciplined_pct = (
            st_qs.filter(is_disciplined=True).count() / st_count * 100
        ) if st_count else 0

        smi = (
            sample_pct * 0.30 +
            win_pct * 0.25 +
            calm_pct * 0.25 +
            disciplined_pct * 0.20
        )
        snapshot.smi_score = round(Decimal(str(smi)), 2)
        snapshot.smi_status = top_strategy_agg['strategy__maturity_status'] or 'testing'
    else:
        snapshot.smi_score = Decimal('0')
        snapshot.smi_status = 'testing'

    # ────────────────────────────────────────────────────────────────────────
    # 11. DDR — Discipline Dependency Ratio
    # (disciplined_profit − undisciplined_profit) / total_profit × 100
    # If total profit ≤ 0, fall back to win-rate difference approach.
    # ────────────────────────────────────────────────────────────────────────
    green_pnl = green_trades_qs.aggregate(total=Sum('total_pnl'))['total'] or Decimal('0')
    non_green_trades = trades.filter(session_id__in=non_green_session_ids)
    non_green_pnl = non_green_trades.aggregate(total=Sum('total_pnl'))['total'] or Decimal('0')
    total_pnl_all = trades.aggregate(total=Sum('total_pnl'))['total'] or Decimal('0')

    if total_pnl_all != 0:
        ddr_pct = abs((green_pnl - non_green_pnl) / total_pnl_all * 100)
    else:
        # Fallback: win-rate gap
        green_wr = (
            green_trades_qs.filter(total_pnl__gt=0).count() / green_trades_qs.count() * 100
            if green_trades_qs.count() else 0
        )
        non_green_wr = (
            non_green_trades.filter(total_pnl__gt=0).count() / non_green_trades.count() * 100
            if non_green_trades.count() else 0
        )
        ddr_pct = abs(green_wr - non_green_wr)

    snapshot.ddr_score = round(Decimal(str(ddr_pct)), 2)
    if ddr_pct < 10:
        snapshot.ddr_level = 'Low'
    elif ddr_pct < 40:
        snapshot.ddr_level = 'Medium'
    else:
        snapshot.ddr_level = 'High'

    # ────────────────────────────────────────────────────────────────────────
    # 12. CPI — Capital Protection Index
    # % of trading days on which the user stayed within their max-loss rule.
    # ────────────────────────────────────────────────────────────────────────
    if user.trading_capital:
        from rules.models import Rule
        max_daily_rule = Rule.objects.filter(
            Q(is_admin_defined=True) | Q(user=user),
            category='risk',
            is_active=True,
            deleted_at__isnull=True,
        ).filter(trigger_condition__has_key='maxDailyPercent').first()

        if max_daily_rule:
            max_pct = Decimal(str(max_daily_rule.trigger_condition.get('maxDailyPercent', 3)))
            max_loss_allowed = user.trading_capital * max_pct / 100

            daily_pnls = trades.annotate(day=TruncDate('trade_date')).values('day').annotate(
                daily_pnl=Sum('total_pnl')
            )
            total_days = daily_pnls.count()
            compliant_days = sum(
                1 for d in daily_pnls
                if d['daily_pnl'] is None or d['daily_pnl'] >= -max_loss_allowed
            )
            snapshot.cpi_score = (
                round(Decimal(str(compliant_days / total_days * 100)), 2)
                if total_days else Decimal('0')
            )
        else:
            snapshot.cpi_score = Decimal('100')
    else:
        snapshot.cpi_score = None

    snapshot.save()
    return snapshot
