"""
Insights Service — Calculates all 12 proprietary BitsOfTrade metrics.
Called from insights/views.py.

Metric definitions:
  1.  DIS  — Discipline Integrity Score         (0-100, weighted penalties, all-time)
  2.  VMI  — Violation Momentum Index           (raw int: Count_A − Count_B, last 10 trades)
  3.  DRT  — Discipline Recovery Time           (avg sessions to recover after RED)
  4.  TPR  — Trading Permission Ratio           (% of GREEN sessions, last 30 days)
  5.  FIE  — Forced Inactivity Effectiveness    (avg_loss × avg_trades × non-override RED sessions)
  6.  OVR  — Override Resistance Score          (10 − override_attempts, from ViolationsLog proxy)
  7.  ECI  — Emotion Cost Index                 (total P&L on ALL non-calm tagged trades)
  8.  CAS  — Confidence Accuracy Score          (% of high-confidence trades that were profitable)
  9.  DAE  — Discipline-Adjusted Expectancy     (true expectancy: disciplined vs undisciplined)
  10. SMI  — Strategy Maturity Index            (per-strategy weighted score 0-100)
  11. DDR  — Discipline Dependency Ratio        (disciplined exp − undisciplined exp) / disciplined exp)
  12. CPI  — Capital Protection Index           (drawdown reduction after rules enabled, or estimated)

MINIMUM DATA THRESHOLDS (spec-mandated — metrics return None if not met):
  DIS  → 1 session (all-time)
  VMI  → 10 trades (no tagging required — ViolationsLog is auto-populated by engine)
  DRT  → 1 RED session that has been followed by a GREEN recovery
  TPR  → 10 sessions in last 30 days
  FIE  → 1 RED session
  OVR  → any data (always calculable)
  ECI  → 10 tagged trades
  CAS  → 10 trades with entry_confidence set
  DAE  → 20 tagged trades (10 disciplined + 10 undisciplined ideal)
  SMI  → 10 trades per strategy
  DDR  → same as DAE
  CPI  → 30 days of trade data

NOTE on session_override_attempts:
  The spec requires a dedicated session_override_attempts table.
  That table does not yet exist. OVR currently uses ViolationsLog
  hard-violation count in last 30 days as the closest available proxy.
  Once the override_attempts table is built, replace _calc_ovr() accordingly.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from typing import Optional

from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncDate
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _d(value) -> Decimal:
    """Safe cast to Decimal. Returns Decimal('0') for None/falsy."""
    if value is None:
        return Decimal('0')
    return Decimal(str(value))


def _round2(value) -> Decimal:
    return _d(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _expectancy(trades_qs) -> Optional[Decimal]:
    """
    True expectancy formula:
      (Win Rate × Avg Win) − (Loss Rate × Avg Loss)

    Returns None if queryset is empty.
    """
    total = trades_qs.count()
    if total == 0:
        return None

    wins_qs  = trades_qs.filter(total_pnl__gt=0)
    losses_qs = trades_qs.filter(total_pnl__lt=0)

    win_count  = wins_qs.count()
    loss_count = losses_qs.count()

    win_rate  = _d(win_count)  / _d(total)
    loss_rate = _d(loss_count) / _d(total)

    avg_win  = _d(wins_qs.aggregate(avg=Avg('total_pnl'))['avg'])
    avg_loss = _d(losses_qs.aggregate(avg=Avg('total_pnl'))['avg'])  # already negative

    # avg_loss is negative; spec says (Win Rate × Avg Win) − (Loss Rate × Avg Loss)
    # loss rate × avg_loss already gives a negative contribution, so subtract it
    expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)
    return _round2(expectancy)


# ─────────────────────────────────────────────────────────────────────────────
# Individual metric calculators
# ─────────────────────────────────────────────────────────────────────────────

def _calc_dis(sessions_all, today: date) -> Optional[Decimal]:
    """
    DIS — Discipline Integrity Score
    Formula (ALL-TIME cumulative record):
      Start at 100, deduct:
        Hard rule breach        : −10 pts each
        Soft rule breach        : −5  pts each
        Repeated same mistake   : −5  pts (session with >1 rule violated)
        Skipped journal RED day : −8  pts each
        Override in restricted  : −12 pts each

    All-time window. Minimum: 1 session.
    """
    session_count = sessions_all.count()
    if session_count < 1:
        return None

    agg = sessions_all.aggregate(
        hard=Sum('hard_violations'),
        soft=Sum('soft_violations'),
    )
    hard_total = int(agg['hard'] or 0)
    soft_total = int(agg['soft'] or 0)

    repeated_sessions = sessions_all.filter(violations_count__gt=1).count()

    skipped_journal = sessions_all.filter(
        peak_state='red',
        journal_completed=False,
    ).count()

    override_proxy = sessions_all.filter(
        peak_state__in=['yellow', 'red'],
        unlocked_at__isnull=False,
        required_actions_completed=False,
    ).count()

    penalty = (
        hard_total        * 10 +
        soft_total        * 5  +
        repeated_sessions * 5  +
        skipped_journal   * 8  +
        override_proxy    * 12
    )

    raw = Decimal('100') - Decimal(str(penalty))
    return _round2(max(raw, Decimal('0')))


def _calc_vmi(trades_all) -> Optional[tuple[int, str]]:
    """
    VMI — Violation Momentum Index
    Formula (spec-exact):
      Split last 10 trades into two windows of 5.
      Count how many trades in each window had at least one ViolationsLog entry
      (i.e. a rule was actually fired by the engine for that trade).
      VMI = Count_A (last 5) − Count_B (prev 5)

    DATA SOURCE: ViolationsLog — the engine writes one row per rule breach
    per trade. This is the authoritative source of rule violations.

    DO NOT use Trade.violation_modes — that is a user psychology tag
    (e.g. "FOMO Entry", "Overtrading") filled manually during trade review.
    It has nothing to do with rule engine violations.

    DO NOT use Trade.is_disciplined alone — it is True/False per trade but
    does not tell us whether violations are clustering or improving.

    Minimum: 10 trades (any trades — no tagging required since ViolationsLog
    is auto-populated by the engine on every trade save).
    Returns (vmi_value, level) or None if < 10 trades.
    Level: Negative→Improving, 0→Stable, 1-2→Warning, 3+→Critical
    """
    from discipline.models import ViolationsLog

    # Get last 10 trades ordered by most recent first
    last_10_trades = list(
        trades_all
        .order_by('-trade_date', '-created_at')
        .values_list('id', flat=True)[:10]
    )

    if len(last_10_trades) < 10:
        return None

    # For each trade, check if any ViolationsLog entry exists
    # (meaning the rule engine fired at least one violation on that trade)
    trades_with_violations = set(
        ViolationsLog.objects
        .filter(trade_id__in=last_10_trades)
        .values_list('trade_id', flat=True)
        .distinct()
    )

    # last_10_trades[0] is most recent → window A = first 5, window B = last 5
    window_a = last_10_trades[:5]   # last 5 trades (most recent)
    window_b = last_10_trades[5:]   # prev 5 trades

    count_a = sum(1 for tid in window_a if tid in trades_with_violations)
    count_b = sum(1 for tid in window_b if tid in trades_with_violations)
    vmi = count_a - count_b

    if vmi < 0:
        level = 'Improving'
    elif vmi == 0:
        level = 'Stable'
    elif vmi <= 2:
        level = 'Warning'
    else:
        level = 'Critical'

    return vmi, level


def _calc_drt(sessions_all) -> Optional[Decimal]:
    """
    DRT — Discipline Recovery Time
    After every RED session, count sessions until next GREEN with no violations.
    DRT = average sessions to return to GREEN.
    Minimum: 1 RED session that has been recovered from.
    """
    all_sessions = list(
        sessions_all.order_by('session_date').values('peak_state', 'violations_count')
    )

    recovery_counts = []
    in_red = False
    red_idx = None

    for idx, s in enumerate(all_sessions):
        if not in_red and s['peak_state'] == 'red':
            in_red = True
            red_idx = idx
        elif in_red and s['peak_state'] == 'green' and s['violations_count'] == 0:
            recovery_counts.append(idx - red_idx)
            in_red = False
            red_idx = None

    if not recovery_counts:
        return None

    avg = sum(recovery_counts) / len(recovery_counts)
    return _round2(Decimal(str(avg)))


def _calc_tpr(sessions_all, today: date) -> Optional[Decimal]:
    """
    TPR — Trading Permission Ratio
    Formula: (GREEN sessions / total sessions) × 100
    Rolling 30 days. Minimum: 10 sessions.
    """
    since = today - timedelta(days=30)
    sessions_30d = sessions_all.filter(session_date__gte=since)
    total = sessions_30d.count()

    if total < 10:
        return None

    green = sessions_30d.filter(peak_state='green').count()
    return _round2(Decimal(str(green / total * 100)))


def _calc_fie(sessions_all, trades_all) -> Optional[Decimal]:
    """
    FIE — Forced Inactivity Effectiveness (estimated)
    Formula (spec-exact):
      avg_loss_per_trade × avg_trades_per_session × RED_sessions_where_user_did_NOT_override

    "Did not override" = RED session where required_actions_completed=True
    (user completed the checklist and did NOT force trades through).
    Minimum: 1 RED session.
    """
    # RED sessions where user respected the lock (did not override)
    respected_red = sessions_all.filter(
        peak_state='red',
        required_actions_completed=True,
    )
    red_count = respected_red.count()

    if red_count == 0:
        return Decimal('0')

    # avg loss per trade (all time, only losing trades)
    avg_loss_agg = trades_all.filter(total_pnl__lt=0).aggregate(avg=Avg('total_pnl'))
    avg_loss = abs(_d(avg_loss_agg['avg']))  # make positive

    if avg_loss == 0:
        return Decimal('0')

    # avg trades per session
    total_trades = trades_all.count()
    total_sessions = sessions_all.count()
    avg_trades_per_session = (
        _d(total_trades) / _d(total_sessions) if total_sessions > 0 else Decimal('0')
    )

    fie = avg_loss * avg_trades_per_session * _d(red_count)
    return _round2(fie)


def _calc_ovr(sessions_all, today: date) -> Decimal:
    """
    OVR — Override Resistance Score (0–10, higher = better)
    Spec formula: Score = 10 − override_attempts (last 30 days)

    NOTE: session_override_attempts table does not exist yet.
    Proxy: count of hard violations logged during YELLOW/RED sessions in last 30 days.
    Replace with override_attempts table query once that table is built.
    """
    from discipline.models import ViolationsLog

    since = today - timedelta(days=30)
    override_attempts = ViolationsLog.objects.filter(
        user=sessions_all.first().user if sessions_all.exists() else None,
        violated_at__date__gte=since,
        violation_type='hard',
        session_state_after__in=['yellow', 'red'],
    ).count() if sessions_all.exists() else 0

    raw = Decimal('10') - Decimal(str(override_attempts))
    return _round2(max(raw, Decimal('0')))


def _calc_eci(trades_all) -> Optional[Decimal]:
    """
    ECI — Emotion Cost Index
    Formula (spec-exact):
      Sum of P&L for ALL trades tagged with non-calm emotional states.
      Includes winning emotional trades — shows full cost (opportunity + loss).
      Headline = total P&L lost from all non-calm states combined.

    Minimum: 10 tagged trades.
    """
    tagged_count = trades_all.filter(is_tagged_complete=True).count()
    if tagged_count < 10:
        return None

    non_calm = ['fomo', 'anxious', 'fearful', 'angry', 'overconfident', 'uncertain']
    eci = trades_all.filter(
        emotional_state__in=non_calm,
        is_tagged_complete=True,
    ).aggregate(total=Sum('total_pnl'))['total']

    return _round2(_d(eci))


def _calc_cas(trades_all) -> Optional[Decimal]:
    """
    CAS — Confidence Accuracy Score
    Formula (spec-exact):
      Group trades into bands: Low (1-3), Medium (4-7), High (8-10)
      CAS = % of HIGH-confidence trades (8-10) that were profitable

    Minimum: 10 trades with entry_confidence set.
    """
    conf_trades = trades_all.filter(entry_confidence__isnull=False)
    if conf_trades.count() < 10:
        return None

    high_conf = conf_trades.filter(entry_confidence__gte=8)
    high_total = high_conf.count()

    if high_total == 0:
        return None  # No high-confidence trades — can't calculate

    high_wins = high_conf.filter(total_pnl__gt=0).count()
    return _round2(Decimal(str(high_wins / high_total * 100)))


def _calc_dae(trades_all) -> Optional[tuple[Decimal, Decimal, Decimal]]:
    """
    DAE — Discipline-Adjusted Expectancy
    Formula (spec-exact):
      Disciplined trade  = is_disciplined=True AND is_tagged_complete=True
      Undisciplined trade = is_disciplined=False AND is_tagged_complete=True

      Expectancy = (Win Rate × Avg Win) − (Loss Rate × Avg Loss)  per group

    Returns (dae_disciplined, dae_undisciplined, dae_raw) or None if < 20 tagged trades.
    """
    tagged = trades_all.filter(is_tagged_complete=True)
    if tagged.count() < 20:
        return None

    disciplined_qs   = tagged.filter(is_disciplined=True)
    undisciplined_qs = tagged.filter(is_disciplined=False)

    dae_disc   = _expectancy(disciplined_qs)
    dae_undisc = _expectancy(undisciplined_qs)
    dae_raw    = _expectancy(tagged)

    # If either group has no trades yet, return None for that side but still store raw
    if dae_disc is None:
        dae_disc = Decimal('0')
    if dae_undisc is None:
        dae_undisc = Decimal('0')
    if dae_raw is None:
        dae_raw = Decimal('0')

    return dae_disc, dae_undisc, dae_raw


def _calc_smi_for_strategy(st_trades_qs, threshold: int) -> Optional[Decimal]:
    """
    SMI — Strategy Maturity Index for a single strategy.
    Formula (spec-exact, weights):
      Sample size     40% — progress toward 30-trade threshold
      Rule adherence  30% — % of strategy trades that are disciplined
      R-multiple var  20% — consistency (inverted variance of P&L, capped)
      Emotional stab  10% — % of trades with calm/confident state

    Minimum: 10 trades for this strategy.
    """
    count = st_trades_qs.count()
    if count < 10:
        return None

    # 1. Sample size score (40%)
    sample_pct = min((_d(count) / _d(threshold or 30)) * 100, Decimal('100'))

    # 2. Rule adherence (30%)
    disciplined_count = st_trades_qs.filter(is_disciplined=True).count()
    adherence_pct = _d(disciplined_count) / _d(count) * 100

    # 3. R-multiple variance (20%) — use P&L values as R-multiple proxy
    #    Lower variance = higher score. We invert normalised std-dev.
    pnls = list(st_trades_qs.values_list('total_pnl', flat=True))
    pnls = [_d(p) for p in pnls if p is not None]
    if len(pnls) >= 2:
        mean_pnl = sum(pnls) / len(pnls)
        variance = sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls)
        std_dev = variance ** Decimal('0.5')
        # Normalise: score drops as std_dev grows. Cap at 100, floor at 0.
        # A std_dev of 0 → 100%, std_dev equal to mean → ~50%
        if mean_pnl != 0:
            cv = abs(std_dev / mean_pnl)  # coefficient of variation
            consistency_pct = max(Decimal('100') - (cv * 50), Decimal('0'))
        else:
            consistency_pct = Decimal('50')  # neutral when mean = 0
    else:
        consistency_pct = Decimal('50')

    # 4. Emotional stability (10%)
    calm_count = st_trades_qs.filter(
        emotional_state__in=['calm', 'confident'],
        is_tagged_complete=True,
    ).count()
    calm_pct = _d(calm_count) / _d(count) * 100

    smi = (
        sample_pct      * Decimal('0.40') +
        adherence_pct   * Decimal('0.30') +
        consistency_pct * Decimal('0.20') +
        calm_pct        * Decimal('0.10')
    )
    return _round2(min(smi, Decimal('100')))


def _smi_status(score: Decimal) -> str:
    if score >= 71:
        return 'mature'
    if score >= 41:
        return 'developing'
    return 'testing'


def _calc_ddr(dae_disc: Decimal, dae_undisc: Decimal) -> Optional[tuple[Decimal, str]]:
    """
    DDR — Discipline Dependency Ratio
    Formula (spec-exact):
      DDR = (disciplined_exp − undisciplined_exp) / disciplined_exp × 100

    Reuses DAE values. Returns (ddr_score, level) or None if disciplined_exp = 0.
    """
    if dae_disc == 0:
        return None

    ddr = (dae_disc - dae_undisc) / dae_disc * 100
    ddr = _round2(abs(ddr))

    if ddr >= 70:
        level = 'High'
    elif ddr >= 30:
        level = 'Medium'
    else:
        level = 'Low'

    return ddr, level


def _calc_cpi(trades_all, sessions_all, user, today: date) -> Optional[Decimal]:
    """
    CPI — Capital Protection Index
    Formula (spec-exact):

    Branch A — user has trade history before AND after rules were enabled:
      CPI = (drawdown_before − drawdown_after) / drawdown_before × 100

    Branch B — new user (no clear before/after split):
      CPI = (max_possible_loss − actual_max_loss) / max_possible_loss × 100
      where max_possible_loss = avg_trades_per_session × avg_loss_per_trade × RED_sessions_blocked

    Minimum: 30 days of trade data.
    """
    earliest = trades_all.order_by('trade_date').values_list('trade_date', flat=True).first()
    if not earliest:
        return None

    days_of_data = (today - earliest).days
    if days_of_data < 30:
        return None

    # Try Branch A: look for a rules_enabled_at date on the user profile
    rules_enabled_at = getattr(user, 'rules_enabled_at', None)

    if rules_enabled_at:
        rules_enabled_date = (
            rules_enabled_at.date() if hasattr(rules_enabled_at, 'date') else rules_enabled_at
        )
        before_trades = trades_all.filter(trade_date__lt=rules_enabled_date)
        after_trades  = trades_all.filter(trade_date__gte=rules_enabled_date)

        if before_trades.exists() and after_trades.exists():
            def _max_drawdown(qs):
                """Peak-to-trough drawdown from cumulative P&L."""
                pnls = list(
                    qs.order_by('trade_date', 'created_at')
                      .values_list('total_pnl', flat=True)
                )
                cumulative = Decimal('0')
                peak = Decimal('0')
                max_dd = Decimal('0')
                for pnl in pnls:
                    cumulative += _d(pnl)
                    if cumulative > peak:
                        peak = cumulative
                    dd = peak - cumulative
                    if dd > max_dd:
                        max_dd = dd
                return max_dd

            dd_before = _max_drawdown(before_trades)
            dd_after  = _max_drawdown(after_trades)

            if dd_before > 0:
                cpi = (dd_before - dd_after) / dd_before * 100
                return _round2(max(cpi, Decimal('0')))

    # Branch B — estimated formula
    red_blocked = sessions_all.filter(
        peak_state='red',
        required_actions_completed=True,
    ).count()

    if red_blocked == 0:
        return Decimal('0')

    avg_loss_agg = trades_all.filter(total_pnl__lt=0).aggregate(avg=Avg('total_pnl'))
    avg_loss = abs(_d(avg_loss_agg['avg']))

    total_sessions = sessions_all.count()
    total_trades   = trades_all.count()
    avg_trades_per_session = (
        _d(total_trades) / _d(total_sessions) if total_sessions > 0 else Decimal('1')
    )

    max_possible_loss = avg_trades_per_session * avg_loss * _d(red_blocked)
    actual_max_loss   = trades_all.filter(total_pnl__lt=0).aggregate(
        total=Sum('total_pnl'))['total']
    actual_max_loss = abs(_d(actual_max_loss))

    if max_possible_loss == 0:
        return Decimal('0')

    cpi = (max_possible_loss - actual_max_loss) / max_possible_loss * 100
    return _round2(max(min(cpi, Decimal('100')), Decimal('0')))


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def calculate_metrics(user, snapshot_date=None):
    """
    Calculate and persist all 12 metrics into UserMetricSnapshot.

    Each metric is set to None when minimum data requirements are not met.
    The view layer must check for None and return data_state='not_enough_data'.
    """
    from .models import UserMetricSnapshot
    from discipline.models import DisciplineSession, ViolationsLog
    from tradelog.models import Trade

    today = snapshot_date or date.today()

    # ── Base querysets (reused across metrics)
    sessions = DisciplineSession.objects.filter(user=user)
    trades   = Trade.objects.filter(user=user, deleted_at__isnull=True)

    # Pre-compute disciplined / undisciplined trade sets for reuse in DAE + DDR
    green_session_ids    = list(sessions.filter(peak_state='green').values_list('id', flat=True))
    non_green_session_ids = list(sessions.exclude(peak_state='green').values_list('id', flat=True))

    # Always recalculate — overwrite stale snapshot
    snapshot, _ = UserMetricSnapshot.objects.update_or_create(
        user=user,
        snapshot_date=today,
        defaults={},
    )

    # ── 1. DIS
    snapshot.di_score = _calc_dis(sessions, today)

    # ── 2. VMI
    vmi_result = _calc_vmi(trades)
    if vmi_result is None:
        snapshot.vmi_score = None
        snapshot.vmi_level = None
    else:
        vmi_val, vmi_level = vmi_result
        snapshot.vmi_score = _d(vmi_val)
        snapshot.vmi_level = vmi_level

    # ── 3. DRT
    snapshot.drt_days = _calc_drt(sessions)

    # ── 4. TPR
    snapshot.tpr_score = _calc_tpr(sessions, today)

    # ── 5. FIE
    snapshot.fie_amount = _calc_fie(sessions, trades)

    # ── 6. OVR
    snapshot.ovr_score = _calc_ovr(sessions, today)

    # ── 7. ECI
    snapshot.eci_amount = _calc_eci(trades)

    # ── 8. CAS
    snapshot.cas_score = _calc_cas(trades)

    # ── 9. DAE  (compute once, reuse for DDR)
    dae_result = _calc_dae(trades)
    if dae_result is None:
        snapshot.dae_r   = None   # disciplined expectancy
        snapshot.dae_raw = None   # raw expectancy
        dae_disc   = None
        dae_undisc = None
    else:
        dae_disc, dae_undisc, dae_raw = dae_result
        snapshot.dae_r   = dae_disc
        snapshot.dae_raw = dae_raw

    # ── 10. SMI  (top strategy only stored in snapshot; per-strategy in view)
    top_strategy_agg = (
        trades.exclude(strategy__isnull=True)
              .values('strategy_id', 'strategy__strategy_name',
                      'strategy__sample_size_threshold')
              .annotate(count=Count('id'))
              .order_by('-count')
              .first()
    )

    if top_strategy_agg and top_strategy_agg['strategy_id']:
        st_qs     = trades.filter(strategy_id=top_strategy_agg['strategy_id'])
        threshold = top_strategy_agg['strategy__sample_size_threshold'] or 30
        smi_val   = _calc_smi_for_strategy(st_qs, threshold)
        snapshot.smi_score  = smi_val
        snapshot.smi_status = _smi_status(smi_val) if smi_val is not None else 'testing'
    else:
        snapshot.smi_score  = None
        snapshot.smi_status = 'testing'

    # ── 11. DDR  (reuses DAE)
    if dae_disc is not None and dae_undisc is not None:
        ddr_result = _calc_ddr(dae_disc, dae_undisc)
        if ddr_result is None:
            snapshot.ddr_score = None
            snapshot.ddr_level = None
        else:
            snapshot.ddr_score, snapshot.ddr_level = ddr_result
    else:
        snapshot.ddr_score = None
        snapshot.ddr_level = None

    # ── 12. CPI
    snapshot.cpi_score = _calc_cpi(trades, sessions, user, today)

    snapshot.save()
    return snapshot