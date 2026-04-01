"""
Insights views — GET /api/insights/metrics/

Returns a fully structured JSON object with three top-level sections:
  • scorecard       — 12 proprietary metric cards with value, status, data_state, evidence, CTA.
  • categories      — Groupings of the 12 metrics into 4 thematic blocks.
  • strategy_health — SMI detail per strategy for the authenticated user.

data_state field on every scorecard card:
  "active"          — minimum data met, value is valid
  "not_enough_data" — below minimum threshold, value is null
  "no_data"         — user has no trades/sessions at all
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum, Avg, Q
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .services import calculate_metrics


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _f(val, decimals: int = 1):
    """Convert a Decimal/None to a rounded float. Returns None for None."""
    if val is None:
        return None
    return round(float(val), decimals)


def _fmt_inr(val) -> str:
    """Format a Decimal/float as ₹12.3k or ₹1,234. Returns ₹0 for None."""
    if val is None:
        return "₹0"
    v = float(val)
    if abs(v) >= 1000:
        return f"₹{v/1000:.1f}k"
    return f"₹{v:,.0f}"


def _data_state(value) -> str:
    """Return data_state string based on whether the value is populated."""
    if value is None:
        return "not_enough_data"
    return "active"


# ─────────────────────────────────────────────────────────────────────────────
# Status helpers — spec-exact thresholds
# ─────────────────────────────────────────────────────────────────────────────

def _status_dis(score) -> str:
    v = float(score or 0)
    if v >= 80:
        return "good"
    if v >= 60:
        return "improving"
    return "warning"


def _status_vmi(level: str | None) -> str:
    # Spec levels: Improving / Stable / Warning / Critical
    mapping = {
        "Improving": "good",
        "Stable":    "stable",
        "Warning":   "warning",
        "Critical":  "critical",
    }
    return mapping.get(level or "Stable", "stable")


def _status_drt(days) -> str:
    v = float(days or 0)
    if v < 2:
        return "good"     # spec: "strong recovery"
    if v < 4:
        return "warning"  # spec: "average recovery"
    return "critical"     # spec: "slow recovery"


def _status_tpr(score) -> str:
    v = float(score or 0)
    if v >= 80:
        return "good"      # spec: "highly trusted"
    if v >= 50:
        return "warning"   # spec: "moderate"
    return "critical"      # spec: "frequently restricted"


def _status_fie(_amount) -> str:
    return "neutral"   # FIE is informational only


def _status_ovr(score) -> str:
    # Spec: 9-10 high resistance, 6-8 moderate, below 5 low
    v = float(score or 0)
    if v >= 9:
        return "good"
    if v >= 6:
        return "warning"
    return "critical"


def _status_eci(amount) -> str:
    # ECI is negative (losses). Larger abs = worse.
    v = abs(float(amount or 0))
    if v >= 5000:
        return "critical"
    if v >= 1000:
        return "warning"
    return "stable"


def _status_cas(score) -> str:
    # Spec: 70%+ well calibrated, 50-70% partially aligned, below 50% overconfident
    v = float(score or 0)
    if v >= 70:
        return "good"
    if v >= 50:
        return "warning"
    return "critical"


def _status_dae(dae_r) -> str:
    v = float(dae_r or 0)
    if v > 0:
        return "good"
    if v == 0:
        return "neutral"
    return "critical"


def _status_smi(status_str: str | None) -> str:
    mapping = {"mature": "good", "developing": "improving", "testing": "warning"}
    return mapping.get(status_str or "testing", "warning")


def _status_ddr(level: str | None) -> str:
    # Spec: High (70%+) = discipline is critical edge, Medium = moderate, Low = structural problem
    mapping = {"High": "good", "Medium": "warning", "Low": "critical"}
    return mapping.get(level or "Low", "warning")


def _status_cpi(score) -> str:
    # Spec: 30%+ strong, 10-30% moderate, below 10% not effective
    v = float(score or 0)
    if v >= 30:
        return "good"
    if v >= 10:
        return "warning"
    return "critical"


# ─────────────────────────────────────────────────────────────────────────────
# Evidence strings
# ─────────────────────────────────────────────────────────────────────────────

def _evidence_dis(user) -> str:
    from discipline.models import DisciplineSession
    agg = (
        DisciplineSession.objects
        .filter(user=user)
        .aggregate(
            hard=Sum('hard_violations'),
            soft=Sum('soft_violations'),
            total_sessions=Count('id'),
        )
    )
    hard = int(agg['hard'] or 0)
    soft = int(agg['soft'] or 0)
    total = int(agg['total_sessions'] or 0)
    return f"{hard} hard + {soft} soft violations across {total} session{'s' if total != 1 else ''}"


def _evidence_vmi(snapshot) -> str:
    from discipline.models import ViolationsLog
    from tradelog.models import Trade

    # Get last 5 trades for this user
    last5_ids = list(
        Trade.objects
        .filter(user_id=snapshot.user_id, deleted_at__isnull=True)
        .order_by('-trade_date', '-created_at')
        .values_list('id', flat=True)[:5]
    )
    # Count how many of those trades had actual rule violations (from the engine)
    count = (
        ViolationsLog.objects
        .filter(trade_id__in=last5_ids)
        .values('trade_id')
        .distinct()
        .count()
    )
    return f"{count} of last 5 trades had rule violation{'s' if count != 1 else ''}"


def _evidence_drt(snapshot) -> str:
    avg = _f(snapshot.drt_days, 1) or 0
    return f"You recover discipline in {avg} session{'s' if avg != 1 else ''} after RED violations"


def _evidence_tpr(snapshot) -> str:
    v = _f(snapshot.tpr_score, 0) or 0
    return f"{v}% of your sessions in the last 30 days were GREEN (fully tradeable)"


def _evidence_fie(snapshot) -> str:
    from discipline.models import DisciplineSession
    red_count = DisciplineSession.objects.filter(
        user_id=snapshot.user_id, peak_state='red', required_actions_completed=True
    ).count()
    return (
        f"{red_count} RED session{'s' if red_count != 1 else ''} blocked — "
        f"estimated {_fmt_inr(snapshot.fie_amount)} in losses avoided"
    )


def _evidence_ovr(snapshot) -> str:
    from discipline.models import DisciplineSession
    from tradelog.models import Trade
    red_ids = list(
        DisciplineSession.objects
        .filter(user_id=snapshot.user_id, peak_state='red')
        .values_list('id', flat=True)
    )
    red_trades = Trade.objects.filter(
        user_id=snapshot.user_id,
        session_id__in=red_ids,
        deleted_at__isnull=True,
    ).count()
    if red_trades == 0:
        return "No trades forced through RED sessions — excellent system trust"
    return f"{red_trades} trade{'s' if red_trades != 1 else ''} taken during RED sessions"


def _evidence_eci(snapshot) -> str:
    """Show actual emotional cost from data — no hardcoded multipliers."""
    from tradelog.models import Trade
    non_calm = ['fomo', 'anxious', 'fearful', 'angry', 'overconfident', 'uncertain']
    emotion_counts = (
        Trade.objects
        .filter(
            user_id=snapshot.user_id,
            deleted_at__isnull=True,
            is_tagged_complete=True,
            emotional_state__in=non_calm,
        )
        .values('emotional_state')
        .annotate(count=Count('id'), total_pnl=Sum('total_pnl'))
        .order_by('total_pnl')   # worst first
        .first()
    )
    if emotion_counts:
        worst_emotion = emotion_counts['emotional_state'].upper()
        worst_cost    = _fmt_inr(abs(float(emotion_counts['total_pnl'] or 0)))
        return f"Worst emotional state: {worst_emotion} costs you {worst_cost} in total P&L"
    return f"Emotional trades total cost: {_fmt_inr(abs(float(snapshot.eci_amount or 0)))}"


def _evidence_cas(snapshot) -> str:
    v = _f(snapshot.cas_score, 0) or 0
    return f"High-confidence calls (8-10) were profitable {v}% of the time"


def _evidence_dae(snapshot) -> str:
    disc = float(snapshot.dae_r or 0)
    raw  = float(snapshot.dae_raw or 0)
    diff = disc - raw
    if diff > 0:
        return f"Disciplined trades earn {_fmt_inr(diff)} more per trade than your average"
    if diff < 0:
        return f"Disciplined trades earn {_fmt_inr(abs(diff))} less per trade — review discipline criteria"
    return "Disciplined and average expectancy are equal — keep building sample size"


def _evidence_smi(snapshot) -> str:
    from tradelog.models import Trade
    top = (
        Trade.objects
        .filter(user_id=snapshot.user_id, strategy__isnull=False, deleted_at__isnull=True)
        .values('strategy__strategy_name')
        .annotate(c=Count('id'))
        .order_by('-c')
        .first()
    )
    if top:
        return f"Top strategy '{top['strategy__strategy_name']}' — {top['c']} trades logged"
    return "No strategy trades yet — tag your trades to build SMI"


def _evidence_ddr(snapshot) -> str:
    disc = float(snapshot.dae_r or 0)
    undisc_implied = disc * (1 - float(snapshot.ddr_score or 0) / 100) if snapshot.ddr_score else 0
    level = snapshot.ddr_level or 'Low'
    return (
        f"Disciplined expectancy {_fmt_inr(disc)} vs undisciplined "
        f"{_fmt_inr(undisc_implied)} — {level} discipline dependency"
    )


def _evidence_cpi(snapshot) -> str:
    v = _f(snapshot.cpi_score, 0) or 0
    return f"Capital protection score: {v}% — based on drawdown before vs after rules"


# ─────────────────────────────────────────────────────────────────────────────
# Per-strategy SMI section
# ─────────────────────────────────────────────────────────────────────────────

def _build_strategy_health(user) -> list:
    """Return SMI details per strategy using the spec-correct formula."""
    from tradelog.models import Trade
    from .services import _calc_smi_for_strategy, _smi_status

    strategy_groups = (
        Trade.objects
        .filter(user=user, strategy__isnull=False, deleted_at__isnull=True)
        .values(
            'strategy_id',
            'strategy__strategy_name',
            'strategy__sample_size_threshold',
            'strategy__maturity_status',
        )
        .annotate(
            total_trades=Count('id'),
            wins=Count('id', filter=Q(total_pnl__gt=0)),
        )
        .order_by('-total_trades')
    )

    result = []
    for row in strategy_groups:
        st_qs     = Trade.objects.filter(
            user=user, strategy_id=row['strategy_id'], deleted_at__isnull=True
        )
        threshold = row['strategy__sample_size_threshold'] or 30
        smi_val   = _calc_smi_for_strategy(st_qs, threshold)

        total = row['total_trades'] or 1
        win_pct = round((row['wins'] / total) * 100, 1)
        sample_pct = round(min((total / threshold) * 100, 100), 1)

        maturity = (
            _smi_status(smi_val) if smi_val is not None
            else (row['strategy__maturity_status'] or 'testing')
        )

        result.append({
            'strategy_id':     str(row['strategy_id']),
            'strategy_name':   row['strategy__strategy_name'],
            'total_trades':    row['total_trades'],
            'smi_score':       _f(smi_val, 1),
            'data_state':      _data_state(smi_val),
            'maturity_status': maturity,
            'maturity_label':  maturity.capitalize(),
            'win_rate':        win_pct,
            'sample_progress': sample_pct,
            'min_trades_needed': max(0, 10 - row['total_trades']),
        })

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main response builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_response(snapshot, user) -> dict:
    s = snapshot

    scorecard = [
        # ── 1. DIS
        {
            'code':          'DIS',
            'label':         'Discipline Integrity Score',
            'value':         _f(s.di_score),
            'unit':          '%',
            'data_state':    _data_state(s.di_score),
            'status':        _status_dis(s.di_score) if s.di_score is not None else 'neutral',
            'trend':         'Improving' if _f(s.di_score, 0) and _f(s.di_score, 0) >= 60 else 'Declining',
            'what_it_means': (
                f"You follow your rules {_f(s.di_score)}% of the time"
                if s.di_score is not None
                else "Log at least 1 session to unlock DIS"
            ),
            'evidence':      _evidence_dis(user),
            'cta':           {'label': 'Review Rules & Limits', 'type': 'rules'},
        },
        # ── 2. VMI
        {
            'code':          'VMI',
            'label':         'Violation Momentum Index',
            'value':         _f(s.vmi_score, 0),
            'unit':          '',
            'data_state':    _data_state(s.vmi_score),
            'status':        _status_vmi(s.vmi_level) if s.vmi_level is not None else 'neutral',
            'trend':         s.vmi_level or 'Stable',
            'what_it_means': (
                {
                    'Improving': 'Mistakes are reducing — good momentum',
                    'Stable':    'No change in violation pattern',
                    'Warning':   'Mistakes are starting to cluster',
                    'Critical':  'Violations are snowballing — act now',
                }.get(s.vmi_level or 'Stable', 'Not enough data yet')
                if s.vmi_level is not None
                else 'Log at least 10 trades to unlock VMI'
            ),
            'evidence':      _evidence_vmi(s),
            'cta':           {'label': 'Complete Quick Journal', 'type': 'journal'},
        },
        # ── 3. DRT
        {
            'code':          'DRT',
            'label':         'Discipline Recovery Time',
            'value':         _f(s.drt_days),
            'unit':          'sessions',
            'data_state':    _data_state(s.drt_days),
            'status':        _status_drt(s.drt_days) if s.drt_days is not None else 'neutral',
            'trend':         'Stable',
            'what_it_means': (
                f"You recover to GREEN discipline in {_f(s.drt_days)} session(s) after a RED violation"
                if s.drt_days is not None
                else 'Complete at least 1 RED session recovery to unlock DRT'
            ),
            'evidence':      _evidence_drt(s),
            'cta':           {'label': 'Watch Recovery Lesson', 'type': 'learn'},
        },
        # ── 4. TPR
        {
            'code':          'TPR',
            'label':         'Trading Permission Ratio',
            'value':         _f(s.tpr_score),
            'unit':          '%',
            'data_state':    _data_state(s.tpr_score),
            'status':        _status_tpr(s.tpr_score) if s.tpr_score is not None else 'neutral',
            'trend':         'Stable',
            'what_it_means': (
                f"{_f(s.tpr_score)}% of your sessions give full trading permission"
                if s.tpr_score is not None
                else 'Log at least 10 sessions in the last 30 days to unlock TPR'
            ),
            'evidence':      _evidence_tpr(s),
            'cta':           {'label': 'View Session History', 'type': 'discipline'},
        },
        # ── 5. FIE  (always estimated — label must say so)
        {
            'code':          'FIE',
            'label':         'Forced Inactivity Effectiveness',
            'value':         _f(s.fie_amount, 0),
            'unit':          '₹',
            'data_state':    'active',   # FIE is always calculable (0 if no RED sessions)
            'status':        _status_fie(s.fie_amount),
            'trend':         'Neutral',
            'is_estimated':  True,       # Frontend must label this as estimated
            'what_it_means': f"Estimated {_fmt_inr(s.fie_amount)} in losses avoided by RED-session stops",
            'evidence':      _evidence_fie(s),
            'cta':           {'label': 'View RED Sessions', 'type': 'discipline'},
        },
        # ── 6. OVR
        {
            'code':          'OVR',
            'label':         'Override Resistance Score',
            'value':         _f(s.ovr_score),
            'unit':          '/10',
            'data_state':    _data_state(s.ovr_score),
            'status':        _status_ovr(s.ovr_score) if s.ovr_score is not None else 'neutral',
            'trend':         'Stable',
            'what_it_means': (
                f"You scored {_f(s.ovr_score)}/10 in resisting system overrides"
                if s.ovr_score is not None
                else 'Override resistance will calculate once you have RED sessions'
            ),
            'evidence':      _evidence_ovr(s),
            'cta':           {'label': 'Review Override Events', 'type': 'discipline'},
        },
        # ── 7. ECI  (requires manual tagging)
        {
            'code':          'ECI',
            'label':         'Emotion Cost Index',
            'value':         _f(s.eci_amount, 0),
            'unit':          '₹',
            'data_state':    _data_state(s.eci_amount),
            'status':        _status_eci(s.eci_amount) if s.eci_amount is not None else 'neutral',
            'trend':         'Critical' if _status_eci(s.eci_amount) == 'critical' else 'Stable',
            'what_it_means': (
                f"Emotional trades cost you {_fmt_inr(abs(float(s.eci_amount or 0)))} in total P&L"
                if s.eci_amount is not None
                else 'Tag emotional states on at least 10 trades to unlock ECI'
            ),
            'evidence':      _evidence_eci(s),
            'cta':           {'label': 'Review Emotional Patterns', 'type': 'journal'},
        },
        # ── 8. CAS  (requires manual tagging)
        {
            'code':          'CAS',
            'label':         'Confidence Accuracy Score',
            'value':         _f(s.cas_score),
            'unit':          '%',
            'data_state':    _data_state(s.cas_score),
            'status':        _status_cas(s.cas_score) if s.cas_score is not None else 'neutral',
            'trend':         'Stable',
            'what_it_means': (
                f"Your high-confidence calls (8-10) are accurate {_f(s.cas_score)}% of the time"
                if s.cas_score is not None
                else 'Rate confidence on at least 10 trades to unlock CAS'
            ),
            'evidence':      _evidence_cas(s),
            'cta':           {'label': 'View Confidence Analysis', 'type': 'reports'},
        },
        # ── 9. DAE  (requires manual tagging)
        {
            'code':          'DAE',
            'label':         'Discipline-Adjusted Expectancy',
            'value':         _f(s.dae_r, 0),
            'unit':          '₹',
            'data_state':    _data_state(s.dae_r),
            'status':        _status_dae(s.dae_r) if s.dae_r is not None else 'neutral',
            'trend':         'Positive' if float(s.dae_r or 0) > 0 else 'Negative',
            'what_it_means': (
                f"Avg expectancy per disciplined trade: {_fmt_inr(s.dae_r)}"
                if s.dae_r is not None
                else 'Tag at least 20 trades as disciplined/undisciplined to unlock DAE'
            ),
            'raw_expectancy': _f(s.dae_raw, 0),   # shown side-by-side with disciplined
            'evidence':      _evidence_dae(s),
            'cta':           {'label': 'View Expectancy Report', 'type': 'reports'},
        },
        # ── 10. SMI
        {
            'code':          'SMI',
            'label':         'Strategy Maturity Index',
            'value':         _f(s.smi_score, 0),
            'unit':          '/100',
            'data_state':    _data_state(s.smi_score),
            'status':        _status_smi(s.smi_status) if s.smi_score is not None else 'neutral',
            'trend':         (s.smi_status or 'testing').capitalize(),
            'what_it_means': (
                f"Your top strategy is {(s.smi_status or 'testing').lower()} — score {_f(s.smi_score, 0)}/100"
                if s.smi_score is not None
                else 'Tag a strategy on at least 10 trades to unlock SMI'
            ),
            'evidence':      _evidence_smi(s),
            'cta':           {'label': 'View Strategy Details', 'type': 'strategies'},
        },
        # ── 11. DDR
        {
            'code':          'DDR',
            'label':         'Discipline Dependency Ratio',
            'value':         _f(s.ddr_score),
            'unit':          '%',
            'data_state':    _data_state(s.ddr_score),
            'status':        _status_ddr(s.ddr_level) if s.ddr_score is not None else 'neutral',
            'trend':         s.ddr_level or 'Low',
            'what_it_means': (
                f"Discipline accounts for {_f(s.ddr_score)}% of your P&L edge"
                if s.ddr_score is not None
                else 'Unlock DAE first — DDR is calculated from DAE data'
            ),
            'evidence':      _evidence_ddr(s),
            'cta':           {'label': 'View Behaviour Report', 'type': 'reports'},
        },
        # ── 12. CPI
        {
            'code':          'CPI',
            'label':         'Capital Protection Index',
            'value':         _f(s.cpi_score) if s.cpi_score is not None else None,
            'unit':          '%',
            'data_state':    _data_state(s.cpi_score),
            'status':        _status_cpi(s.cpi_score) if s.cpi_score is not None else 'neutral',
            'is_estimated':  True,   # CPI may use estimated formula — always label it
            'trend':         'Stable',
            'what_it_means': (
                f"Rules reduced your drawdown by {_f(s.cpi_score)}%"
                if s.cpi_score is not None
                else 'Log 30 days of trade data to unlock CPI'
            ),
            'evidence':      _evidence_cpi(s) if s.cpi_score is not None else 'Not enough trade history yet',
            'cta':           {'label': 'Set Capital & Rules', 'type': 'rules'},
        },
    ]

    categories = [
        {
            'name':         'Discipline & Behaviour',
            'metric_count': 3,
            'metrics':      ['DIS', 'VMI', 'DRT'],
        },
        {
            'name':         'Session & Control',
            'metric_count': 3,
            'metrics':      ['TPR', 'FIE', 'OVR'],
        },
        {
            'name':         'Psychology & Performance',
            'metric_count': 3,
            'metrics':      ['ECI', 'CAS', 'DAE'],
        },
        {
            'name':         'System Intelligence',
            'metric_count': 3,
            'metrics':      ['SMI', 'DDR', 'CPI'],
        },
    ]

    strategy_health = _build_strategy_health(user)

    return {
        'scorecard':       scorecard,
        'categories':      categories,
        'strategy_health': strategy_health,
        'meta': {
            'snapshot_date':  str(s.snapshot_date),
            'calculated_at':  s.calculated_at.isoformat() if s.calculated_at else None,
            'total_metrics':  len(scorecard),
            'active_metrics': sum(1 for c in scorecard if c['data_state'] == 'active'),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# View
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def metrics_view(request):
    """
    GET /api/insights/metrics/

    Returns all 12 proprietary metrics in a structure the frontend can
    consume directly. Every card includes a data_state field:
      "active"          — metric is calculated, value is valid
      "not_enough_data" — below minimum data threshold, value is null
    """
    snapshot = calculate_metrics(request.user, snapshot_date=date.today())
    return Response(_build_response(snapshot, request.user))