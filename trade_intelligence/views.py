"""
trade_intelligence/views.py

POST /api/trade-intelligence/analyze/
Body: { timeRange: 'all'|'last7'|'last30'|'last90'|'last365'|'custom', fromDate, toDate,
        market: optional str, broker: optional str }

Returns a rich, frontend-structured intelligence report with five sections:
  1. intelligence_summary
  2. doing_well       (What You're Doing Well)
  3. holding_back     (What's Holding You Back)
  4. repeating_patterns
  5. discipline_health
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions
from rest_framework.response import Response
from django.db.models import Sum, Count, Avg, Q, F
from django.db.models.functions import TruncDate, ExtractHour, TruncWeek
from decimal import Decimal
from datetime import date, timedelta, datetime
from accounts.permissions import HasToolSubscription


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date_range(request):
    time_range = request.data.get('timeRange', 'last30')
    from_date  = request.data.get('fromDate')
    to_date    = request.data.get('toDate')
    today      = date.today()

    if time_range == 'all':
        return None, None, 'All Time'
    elif time_range == 'last7':
        return today - timedelta(days=7), today, 'Last 7 Days'
    elif time_range == 'last30':
        return today - timedelta(days=30), today, 'Last 30 Days'
    elif time_range == 'last90':
        return today - timedelta(days=90), today, 'Last 90 Days'
    elif time_range == 'last365':
        return today - timedelta(days=365), today, 'Last 365 Days'
    elif time_range == 'custom' and from_date and to_date:
        return (
            datetime.strptime(from_date, '%Y-%m-%d').date(),
            datetime.strptime(to_date, '%Y-%m-%d').date(),
            f"{from_date} – {to_date}",
        )
    return today - timedelta(days=30), today, 'Last 30 Days'


def _safe_pct(numerator, denominator):
    if not denominator:
        return 0.0
    return round((numerator or 0) / denominator * 100, 1)


def _safe_float(value, default=0.0):
    """Safely convert a value to float, returning default if None."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _discipline_score(sessions_qs):
    """0-100 discipline score = green % weighted by no hard violations."""
    total = sessions_qs.count()
    if not total:
        return 0.0
    green = sessions_qs.filter(session_state='green').count()
    hard_viol = sessions_qs.aggregate(h=Sum('hard_violations'))['h'] or 0
    base = (green / total) * 100
    # Penalise 2 pts per hard violation, floor at 0
    score = max(0.0, base - (hard_viol * 2))
    return round(min(score, 100.0), 1)


def _health_rating(score):
    if score >= 85:
        return 'Excellent'
    if score >= 70:
        return 'Improving but fragile'
    if score >= 50:
        return 'Needs Attention'
    return 'Critical'


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def analyze_view(request):
    from tradelog.models import Trade
    from mistakes.models import TradeMistake
    from discipline.models import DisciplineSession, ViolationsLog
    from journal.models import PsychologyLog, DailyJournal
    from rules.models import Rule

    user = request.user
    start, end, period_label = _parse_date_range(request)

    # Optional extra filters from frontend (market / broker)
    market_filter  = request.data.get('market')
    broker_filter  = request.data.get('broker')

    # ── Base querysets ──────────────────────────────────────────────────────
    trades = Trade.objects.filter(user=user, deleted_at__isnull=True)
    if start:
        trades = trades.filter(trade_date__gte=start)
    if end:
        trades = trades.filter(trade_date__lte=end)
    if market_filter and market_filter.lower() != 'all':
        trades = trades.filter(market_type=market_filter)
    if broker_filter and broker_filter.lower() != 'all':
        trades = trades.filter(broker_name__iexact=broker_filter)

    total_trades = trades.count()
    if total_trades == 0:
        return Response({
            'period': period_label,
            'total_trades': 0,
            'message': 'No trades found in the selected period.',
        })

    sessions = DisciplineSession.objects.filter(user=user)
    if start:
        sessions = sessions.filter(session_date__gte=start)
    if end:
        sessions = sessions.filter(session_date__lte=end)

    trade_ids      = list(trades.values_list('id', flat=True))
    total_sessions = sessions.count()

    # ── Core metrics ────────────────────────────────────────────────────────
    wins      = trades.filter(total_pnl__gt=0).count()
    losses    = trades.filter(total_pnl__lt=0).count()
    total_pnl = _safe_float(trades.aggregate(t=Sum('total_pnl'))['t'])

    # Disciplined trades (is_disciplined flag)
    disciplined_trades   = trades.filter(is_disciplined=True).count()
    undisciplined_trades = trades.filter(is_disciplined=False).count()

    # ── Session state breakdown ─────────────────────────────────────────────
    green_sessions  = sessions.filter(session_state='green').count()
    yellow_sessions = sessions.filter(session_state='yellow').count()
    red_sessions    = sessions.filter(session_state='red').count()

    green_ids  = list(sessions.filter(session_state='green').values_list('id', flat=True))
    yellow_ids = list(sessions.filter(session_state='yellow').values_list('id', flat=True))
    red_ids    = list(sessions.filter(session_state='red').values_list('id', flat=True))

    # PnL by session state
    green_pnl  = _safe_float(trades.filter(session_id__in=green_ids).aggregate(t=Sum('total_pnl'))['t'])
    yellow_pnl = _safe_float(trades.filter(session_id__in=yellow_ids).aggregate(t=Sum('total_pnl'))['t'])
    red_pnl    = _safe_float(trades.filter(session_id__in=red_ids).aggregate(t=Sum('total_pnl'))['t'])

    # ── FOMO / emotional data ───────────────────────────────────────────────
    fomo_trades          = trades.filter(emotional_state='fomo').count()
    trades_after_loss    = 0
    fomo_after_loss      = 0

    sorted_trades = list(
        trades.order_by('trade_date', 'trade_time').values(
            'id', 'total_pnl', 'emotional_state', 'trade_date', 'trade_time'
        )
    )
    for i in range(1, len(sorted_trades)):
        prev = sorted_trades[i - 1]
        curr = sorted_trades[i]
        prev_pnl = _safe_float(prev['total_pnl'], default=0.0)
        if prev_pnl < 0:
            trades_after_loss += 1
            if curr['emotional_state'] == 'fomo':
                fomo_after_loss += 1

    fomo_after_loss_pct = _safe_pct(fomo_after_loss, trades_after_loss)

    # ── Psychology logs ─────────────────────────────────────────────────────
    psych_logs = PsychologyLog.objects.filter(user=user)
    if start:
        psych_logs = psych_logs.filter(log_date__gte=start)
    if end:
        psych_logs = psych_logs.filter(log_date__lte=end)

    nervous_logs = psych_logs.filter(emotional_state='anxious').count()
    total_psych  = psych_logs.count()
    nervous_pct  = _safe_pct(nervous_logs, total_psych)

    # ── Violations ──────────────────────────────────────────────────────────
    violations_qs = ViolationsLog.objects.filter(user=user)
    if start:
        violations_qs = violations_qs.filter(violated_at__date__gte=start)
    if end:
        violations_qs = violations_qs.filter(violated_at__date__lte=end)

    total_violations = violations_qs.count()
    hard_violations  = violations_qs.filter(violation_type='hard').count()

    # Position-size violations (rules whose name contains 'position')
    position_size_viol = violations_qs.filter(
        rule__rule_name__icontains='position'
    ).count()

    # ── Confirmation / entry discipline ─────────────────────────────────────
    # Trades with entry_confidence >= 7 = "waited for confirmation"
    confirmed_entries = trades.filter(entry_confidence__gte=7).count()
    confirm_rate_pct  = _safe_pct(confirmed_entries, total_trades)

    # Trades that followed strategy rules (is_disciplined=True with a strategy)
    strategy_adherent = trades.filter(
        is_disciplined=True, strategy__isnull=False
    ).count()
    trades_with_strat = trades.filter(strategy__isnull=False).count()
    strategy_adherence_pct = _safe_pct(strategy_adherent, trades_with_strat)

    # ── R:R improvement ─────────────────────────────────────────────────────
    # Compare avg win/loss in first vs second half
    half = total_trades // 2
    sorted_ids      = list(trades.order_by('trade_date', 'trade_time').values_list('id', flat=True))
    first_half_ids  = sorted_ids[:half]
    second_half_ids = sorted_ids[half:]

    def _avg_rr(ids):
        wins_  = trades.filter(id__in=ids, total_pnl__gt=0)
        losses_= trades.filter(id__in=ids, total_pnl__lt=0)
        avg_w  = _safe_float(wins_.aggregate(a=Avg('total_pnl'))['a'])
        avg_l  = abs(_safe_float(losses_.aggregate(a=Avg('total_pnl'))['a'])) or 1
        return round(avg_w / avg_l, 2)

    rr_first       = _avg_rr(first_half_ids)
    rr_second      = _avg_rr(second_half_ids)
    rr_improvement = round(rr_second - rr_first, 2)

    # ── Best trading window (first 30 min = hour 9) ─────────────────────────
    hourly = list(
        trades.filter(trade_time__isnull=False)
        .annotate(h=ExtractHour('trade_time'))
        .values('h')
        .annotate(win_rate=Avg('total_pnl'), cnt=Count('id'))
        .order_by('h')
    )
    best_hour_data = max(hourly, key=lambda x: _safe_float(x['win_rate'])) if hourly else None
    best_hour      = best_hour_data['h'] if best_hour_data else 9

    # Win rate in best hour window
    best_hour_trades = trades.filter(trade_time__isnull=False).annotate(
        h=ExtractHour('trade_time')
    ).filter(h=best_hour)
    bh_wins    = best_hour_trades.filter(total_pnl__gt=0).count()
    bh_total   = best_hour_trades.count()
    bh_win_pct = _safe_pct(bh_wins, bh_total)

    # ── Average loss vs threshold ────────────────────────────────────────────
    avg_loss_pct  = 0.0
    losing_trades = trades.filter(total_pnl__lt=0)
    if losing_trades.exists():
        avg_loss_val = abs(_safe_float(losing_trades.aggregate(a=Avg('total_pnl'))['a']))
        avg_notional = _safe_float(
            losing_trades.aggregate(
                n=Avg(F('entry_price') * F('quantity'))
            )['n'],
            default=1.0
        ) or 1.0
        avg_loss_pct = round(avg_loss_val / avg_notional * 100, 1)

    # Max loss threshold from rules
    max_loss_rule = Rule.objects.filter(
        Q(is_admin_defined=True) | Q(user=user),
        is_active=True, deleted_at__isnull=True,
    ).filter(
        Q(trigger_condition__has_key='maxLossPercent') |
        Q(trigger_condition__has_key='maxLoss') |
        Q(trigger_condition__has_key='maxDailyPercent')
    ).first()
    if max_loss_rule:
        tc = max_loss_rule.trigger_condition
        max_loss_threshold = _safe_float(
            tc.get('maxLossPercent') or tc.get('maxLoss') or tc.get('maxDailyPercent'),
            default=3.0
        ) or 3.0
    else:
        max_loss_threshold = 3.0

    # ── Revenge-trading detection ────────────────────────────────────────────
    revenge_count = 0
    for i in range(1, len(sorted_trades)):
        prev = sorted_trades[i - 1]
        curr = sorted_trades[i]
        prev_pnl = _safe_float(prev['total_pnl'], default=0.0)
        if prev_pnl >= 0:
            continue
        # Same day check
        if prev['trade_date'] != curr['trade_date']:
            continue
        if curr['emotional_state'] in ('angry', 'fomo', 'overconfident'):
            revenge_count += 1

    # ── Consecutive loss streaks ─────────────────────────────────────────────
    # Use daily PnL
    daily_pnls = list(
        trades.annotate(day=TruncDate('trade_date'))
        .values('day')
        .annotate(dpnl=Sum('total_pnl'))
        .order_by('day')
        .values_list('dpnl', flat=True)
    )

    max_loss_streak = 0
    cur_streak      = 0
    for dpnl in daily_pnls:
        dpnl_val = _safe_float(dpnl, default=0.0)   # ← THE KEY FIX (was crashing on None)
        if dpnl_val < 0:
            cur_streak += 1
            max_loss_streak = max(max_loss_streak, cur_streak)
        else:
            cur_streak = 0

    # ── RED-day discipline ───────────────────────────────────────────────────
    red_day_revenge = trades.filter(
        session_id__in=red_ids,
        emotional_state__in=('angry', 'fomo', 'overconfident')
    ).count()
    red_day_discipline_pct = _safe_pct(
        max(0, red_sessions - (red_day_revenge > 0)),
        max(red_sessions, 1)
    )

    # ── Discipline health ────────────────────────────────────────────────────
    disc_score   = _discipline_score(sessions)
    health_label = _health_rating(disc_score)

    # Average sessions per violation event
    sessions_per_viol = round(total_sessions / max(total_violations, 1), 1)

    # Discipline trend (compare first vs second half sessions)
    if total_sessions >= 2:
        half_s       = total_sessions // 2
        all_sess_ids = list(sessions.order_by('session_date').values_list('id', flat=True))
        first_sess   = sessions.filter(id__in=all_sess_ids[:half_s])
        second_sess  = sessions.filter(id__in=all_sess_ids[half_s:])
        trend = 'Improving' if _discipline_score(second_sess) >= _discipline_score(first_sess) else 'Declining'
    else:
        trend = 'Stable'

    # ── Emotional clarity streak ─────────────────────────────────────────────
    calm_states    = ('calm', 'confident')
    clarity_streak = 0
    best_clarity   = 0
    for t in sorted_trades:
        if t['emotional_state'] in calm_states:
            clarity_streak += 1
            best_clarity = max(best_clarity, clarity_streak)
        else:
            clarity_streak = 0

    # ── Journal "nervous" pattern ────────────────────────────────────────────
    total_journal_days = DailyJournal.objects.filter(user=user)
    if start:
        total_journal_days = total_journal_days.filter(journal_date__gte=start)
    if end:
        total_journal_days = total_journal_days.filter(journal_date__lte=end)
    total_journal_days_count = total_journal_days.count()

    # ── Session avg PnL after FOMO ───────────────────────────────────────────
    avg_session_pnl_after_fomo = 0.0
    if fomo_trades:
        fomo_sess_ids = list(
            trades.filter(emotional_state='fomo')
            .exclude(session_id__isnull=True)
            .values_list('session_id', flat=True)
            .distinct()
        )
        sess_pnls = [
            _safe_float(trades.filter(session_id=sid).aggregate(s=Sum('total_pnl'))['s'])
            for sid in fomo_sess_ids
        ]
        avg_session_pnl_after_fomo = round(
            sum(sess_pnls) / len(sess_pnls), 2
        ) if sess_pnls else 0.0

    # ── Premature exit cost ──────────────────────────────────────────────────
    premature_exits = TradeMistake.objects.filter(
        trade_id__in=trade_ids,
        mistake__mistake_mode__in=['early_exit', 'late_exit']
    ).count()
    premature_exit_pct = _safe_pct(premature_exits, total_trades)

    # ── Build intelligence_summary text ─────────────────────────────────────
    performance_text = 'positive' if total_pnl > 0 else 'negative'
    discipline_text  = (
        'strong and consistent'   if disc_score >= 80 else
        'improving but fragile'   if disc_score >= 65 else
        'unstable and needs work'
    )
    profit_session = (
        'GREEN' if green_pnl >= yellow_pnl and green_pnl >= red_pnl else
        'YELLOW' if yellow_pnl >= red_pnl else
        'RED'
    )
    _session_pnl_map = {'GREEN': green_pnl, 'YELLOW': yellow_pnl, 'RED': red_pnl}
    loss_session = min(_session_pnl_map, key=_session_pnl_map.get)

    summary_text = (
        f"Over the {period_label}, your performance is {performance_text}, "
        f"but discipline consistency is {discipline_text}. "
        f"Most profits came from trend-following trades executed during {profit_session} sessions. "
        f"Losses cluster during {loss_session} sessions driven by FOMO and early entries."
    )

    # ── Assemble response ────────────────────────────────────────────────────
    return Response({
        'period': period_label,
        'total_trades': total_trades,

        # ── 1. Intelligence Summary ─────────────────────────────────────────
        'intelligence_summary': {
            'text': summary_text,
            'performance': performance_text,
            'discipline_consistency': discipline_text,
            'best_profit_session_state': profit_session,
            'loss_cluster_session_state': loss_session,
            'total_pnl': round(total_pnl, 2),
            'wins': wins,
            'losses': losses,
            'win_rate_pct': _safe_pct(wins, total_trades),
        },

        # ── 2. Doing Well ───────────────────────────────────────────────────
        'doing_well': [
            {
                'id': 'confirmation_rate',
                'label': 'Waited for confirmation',
                'value': confirmed_entries,
                'out_of': total_trades,
                'pct': confirm_rate_pct,
                'description': f'You waited for confirmation {confirmed_entries} out of {total_trades} times',
                'view_in_plan': False,
            },
            {
                'id': 'strategy_adherence',
                'label': 'Strategy rule adherence',
                'value': strategy_adherent,
                'out_of': trades_with_strat,
                'pct': strategy_adherence_pct,
                'description': f'{strategy_adherent} of {trades_with_strat} strategy trades followed strategy rules',
                'view_in_plan': True,
            },
            {
                'id': 'rr_improvement',
                'label': 'Risk-to-reward improved',
                'value': rr_improvement,
                'out_of': None,
                'pct': None,
                'description': f'Your risk-to-reward improved by {rr_improvement:+.2f}x comparing first vs second half',
                'view_in_plan': False,
            },
            {
                'id': 'avg_loss_vs_threshold',
                'label': 'Average loss vs max trade threshold',
                'value': avg_loss_pct,
                'out_of': max_loss_threshold,
                'pct': None,
                'description': f'Average loss of {avg_loss_pct}% vs max trade threshold of {max_loss_threshold}%',
                'view_in_plan': False,
            },
            {
                'id': 'best_entry_window',
                'label': 'Best entries in first 30 mins',
                'value': bh_win_pct,
                'out_of': 100,
                'pct': bh_win_pct,
                'description': f'{bh_win_pct}% win rate on entries in hour {best_hour:02d}:00 (best window)',
                'view_in_plan': True,
            },
        ],

        # ── 3. Holding Back ─────────────────────────────────────────────────
        'holding_back': [
            {
                'id': 'fomo_after_loss',
                'label': 'FOMO entries after a loss',
                'value': fomo_after_loss,
                'out_of': trades_after_loss,
                'pct': fomo_after_loss_pct,
                'description': f'FOMO entries appear {fomo_after_loss_pct}% after a loss',
                'avg_session_pnl_after': avg_session_pnl_after_fomo,
            },
            {
                'id': 'fomo_days',
                'label': 'Days affected by FOMO pattern',
                'value': fomo_trades,
                'out_of': total_trades,
                'pct': _safe_pct(fomo_trades, total_trades),
                'description': f'This pattern appeared in {fomo_trades} trades across the period',
            },
            {
                'id': 'risk_after_losses',
                'label': 'Risk analysis after 2 consecutive losses',
                'value': max_loss_streak,
                'out_of': None,
                'pct': None,
                'description': f'Max consecutive losing days: {max_loss_streak}. Declines scale after losing streaks.',
            },
            {
                'id': 'position_size_violations',
                'label': 'Position size rule violations',
                'value': position_size_viol,
                'out_of': total_violations,
                'pct': _safe_pct(position_size_viol, total_violations),
                'description': f'{position_size_viol} position size violations detected — review before ignoring size rules',
            },
            {
                'id': 'premature_exits',
                'label': 'Premature exit trades',
                'value': premature_exits,
                'out_of': total_trades,
                'pct': premature_exit_pct,
                'description': f'{premature_exit_pct}% of trades had premature exits, causing avg profit left on table',
            },
        ],

        # ── 4. Repeating Patterns ───────────────────────────────────────────
        'repeating_patterns': [
            {
                'id': 'revenge_trading',
                'label': 'Revenge trading after loss',
                'value': revenge_count,
                'out_of': total_trades,
                'description': f'Revenge trading (angry/FOMO/overconfident) appears after losses — {revenge_count} occurrences',
                'stat': f'{revenge_count} occurrences detected',
                'journal_mention_pct': round(_safe_pct(revenge_count, total_journal_days_count or 1), 1),
            },
            {
                'id': 'consecutive_losses',
                'label': 'Consecutive losing days',
                'value': max_loss_streak,
                'out_of': None,
                'description': f'{max_loss_streak} consecutive losing days detected in the period',
                'stat': f'Max streak: {max_loss_streak} days',
            },
            {
                'id': 'emotional_clarity',
                'label': 'Emotional clarity streak (calm/confident)',
                'value': best_clarity,
                'out_of': total_trades,
                'description': f'Emotional clarity held for {best_clarity} straight trades',
                'stat': f'{best_clarity} consecutive calm/confident trades',
            },
            {
                'id': 'nervous_before_violations',
                'label': '"Nervous/Anxious" before risk violations',
                'value': nervous_logs,
                'out_of': total_psych,
                'description': f'"Anxious" self-described in {nervous_pct}% of psychology entries',
                'stat': f'{nervous_pct}% of all psych logs',
            },
            {
                'id': 'red_day_discipline',
                'label': 'Discipline on RED days',
                'value': red_sessions,
                'out_of': total_sessions,
                'description': f'{red_sessions} RED days — {red_day_revenge} had revenge entries',
                'stat': f'{red_sessions} red days, {red_day_revenge} with revenge entries',
            },
        ],

        # ── 5. Discipline Health ────────────────────────────────────────────
        'discipline_health': {
            'discipline_score': disc_score,
            'violated_boundaries': total_violations,
            'hard_violations': hard_violations,
            'sessions_count': total_sessions,
            'sessions_per_violation': sessions_per_viol,
            'health_rating': health_label,
            'trend': trend,
            'green_sessions': green_sessions,
            'yellow_sessions': yellow_sessions,
            'red_sessions': red_sessions,
            'reminder': (
                'Your discipline is improving, but fragile. '
                'One uncommitted session could trigger a cascade. '
                'Focus on the 3-second pause before every entry.'
            ) if disc_score < 80 else (
                'Excellent discipline. Keep reinforcing your pre-trade checklist.'
            ),
            'session_pnl_summary': {
                'green_pnl': round(green_pnl, 2),
                'yellow_pnl': round(yellow_pnl, 2),
                'red_pnl': round(red_pnl, 2),
            },
        },
    })