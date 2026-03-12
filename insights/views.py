"""
Insights views — GET /api/insights/metrics/

Returns a fully structured JSON object with three top-level sections:
  • scorecard       — 12 proprietary metric cards (DIS, VMI, DRT, TPR, FIE, OVR,
                       ECI, CAS, DAE, SMI, DDR, CPI) with value, status, evidence, CTA.
  • categories      — Groupings of the 12 metrics into 4 thematic blocks.
  • strategy_health — SMI detail per strategy for the authenticated user.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum, Q
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .services import calculate_metrics


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _f(val, decimals: int = 1):
    """Convert a Decimal/None to a rounded float (or 0)."""
    if val is None:
        return None
    return round(float(val), decimals)


def _fmt_inr(val) -> str:
    """Format a Decimal/float as ₹12.3k or ₹1,234."""
    if val is None:
        return "₹0"
    v = float(val)
    if abs(v) >= 1000:
        return f"₹{v/1000:.1f}k"
    return f"₹{v:,.0f}"


def _status_dis(score) -> str:
    v = float(score or 0)
    if v >= 80:
        return "good"
    if v >= 60:
        return "improving"
    return "warning"


def _status_vmi(level: str | None) -> str:
    mapping = {"Low": "good", "Medium": "warning", "High": "critical"}
    return mapping.get(level or "Low", "warning")


def _status_drt(days) -> str:
    v = float(days or 0)
    if v == 0:
        return "stable"
    if v < 2:
        return "stable"
    if v < 4:
        return "warning"
    return "critical"


def _status_tpr(score) -> str:
    v = float(score or 0)
    if v >= 70:
        return "good"
    if v >= 50:
        return "warning"
    return "critical"


def _status_fie(_amount) -> str:
    # FIE is always informational — just shows potential savings
    return "neutral"


def _status_ovr(score) -> str:
    v = float(score or 0)
    if v >= 8:
        return "good"
    if v >= 5:
        return "warning"
    return "critical"


def _status_eci(amount) -> str:
    v = float(amount or 0)
    # ECI is negative (losses). If cost > ₹5 000 it is critical.
    if abs(v) >= 5000:
        return "critical"
    if abs(v) >= 1000:
        return "warning"
    return "stable"


def _status_cas(score) -> str:
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
    mapping = {"High": "good", "Medium": "warning", "Low": "critical"}
    return mapping.get(level or "Low", "warning")


def _status_cpi(score) -> str:
    v = float(score or 0)
    if v >= 90:
        return "good"
    if v >= 70:
        return "warning"
    return "critical"


# ─────────────────────────────────────────────────────────────────────────────
# Evidence strings (cheap — derived from stored snapshot + one small query)
# ─────────────────────────────────────────────────────────────────────────────

def _evidence_dis(user) -> str:
    """Count rule breaches in last 30 days."""
    from discipline.models import DisciplineSession
    since = date.today() - timedelta(days=30)
    total = (
        DisciplineSession.objects
        .filter(user=user, session_date__gte=since)
        .aggregate(total=Sum("violations_count"))["total"] or 0
    )
    return f"{total} rule breach{'es' if total != 1 else ''} in last 30 days"


def _evidence_vmi(snapshot) -> str:
    """Number of violations in the last 5 trades."""
    from discipline.models import ViolationsLog
    from tradelog.models import Trade
    # grab last 5 trades by date
    last5 = list(
        Trade.objects
        .filter(user_id=snapshot.user_id, deleted_at__isnull=True)
        .order_by("-trade_date", "-created_at")
        .values_list("id", flat=True)[:5]
    )
    count = ViolationsLog.objects.filter(
        user_id=snapshot.user_id, trade_id__in=last5
    ).count()
    return f"{count} mistake{'s' if count != 1 else ''} in last 5 trades"


def _evidence_drt(snapshot) -> str:
    avg = float(snapshot.drt_days or 0)
    return f"You recover discipline in {avg} session{'s' if avg != 1 else ''} after violations"


def _evidence_tpr(snapshot) -> str:
    v = float(snapshot.tpr_score or 0)
    return f"{v:.0f}% of your sessions are GREEN (tradeable)"


def _evidence_fie(snapshot) -> str:
    from discipline.models import DisciplineSession
    red_count = DisciplineSession.objects.filter(
        user_id=snapshot.user_id, peak_state="red"
    ).count()
    return f"{red_count} RED session{'s' if red_count != 1 else ''} triggered forced inactivity"


def _evidence_ovr(snapshot) -> str:
    from discipline.models import DisciplineSession
    from tradelog.models import Trade
    red_ids = list(
        DisciplineSession.objects
        .filter(user_id=snapshot.user_id, peak_state="red")
        .values_list("id", flat=True)
    )
    red_trades = Trade.objects.filter(
        user_id=snapshot.user_id,
        session_id__in=red_ids,
        deleted_at__isnull=True,
    ).count()
    if red_trades == 0:
        return "No trades taken during RED sessions — excellent override resistance"
    return f"{red_trades} trade{'s' if red_trades != 1 else ''} taken during RED sessions"


def _evidence_eci(snapshot) -> str:
    amt = abs(float(snapshot.eci_amount or 0))
    return f"Calm trades profit 2.4× more — emotional trades cost you {_fmt_inr(amt)}"


def _evidence_cas(snapshot) -> str:
    v = float(snapshot.cas_score or 0)
    return f"High-confidence calls were right {v:.0f}% of the time"


def _evidence_dae(snapshot) -> str:
    raw = float(snapshot.dae_raw or 0)
    disc = float(snapshot.dae_r or 0)
    diff = disc - raw
    if diff >= 0:
        return f"Disciplined trades earn {_fmt_inr(diff)} more per trade than average"
    return f"Disciplined trades earn {_fmt_inr(abs(diff))} less per trade than average"


def _evidence_smi(snapshot) -> str:
    from tradelog.models import Trade
    from django.db.models import Count as Cnt
    top = (
        Trade.objects
        .filter(user_id=snapshot.user_id, strategy__isnull=False, deleted_at__isnull=True)
        .values("strategy__strategy_name")
        .annotate(c=Cnt("id"))
        .order_by("-c")
        .first()
    )
    if top:
        return f"Top strategy '{top['strategy__strategy_name']}' has {top['c']} trades"
    return "No strategy trades yet — start tagging trades to build SMI"


def _evidence_ddr(snapshot) -> str:
    v = float(snapshot.ddr_score or 0)
    level = snapshot.ddr_level or "Low"
    return f"Disciplined sessions contribute {v:.0f}% more to your P&L ({level} dependency)"


def _evidence_cpi(snapshot) -> str:
    v = float(snapshot.cpi_score or 0)
    return f"You stayed within max-loss rule on {v:.0f}% of trading days"


# ─────────────────────────────────────────────────────────────────────────────
# Build strategy health section
# ─────────────────────────────────────────────────────────────────────────────

def _build_strategy_health(user) -> list:
    """Return SMI details per strategy that the user has trades for."""
    from tradelog.models import Trade
    from strategies.models import Strategy
    from django.db.models import Count as Cnt, Avg

    rows = (
        Trade.objects
        .filter(user=user, strategy__isnull=False, deleted_at__isnull=True)
        .values(
            "strategy_id",
            "strategy__strategy_name",
            "strategy__maturity_status",
            "strategy__sample_size_threshold",
        )
        .annotate(
            total_trades=Cnt("id"),
            wins=Cnt("id", filter=Q(total_pnl__gt=0)),
            calm_trades=Cnt("id", filter=Q(emotional_state__in=["calm", "confident"])),
            disc_trades=Cnt("id", filter=Q(is_disciplined=True)),
        )
        .order_by("-total_trades")
    )

    result = []
    for r in rows:
        total = r["total_trades"] or 1
        threshold = r["strategy__sample_size_threshold"] or 30

        sample_pct = min((total / threshold) * 100, 100)
        win_pct    = (r["wins"] / total) * 100
        calm_pct   = (r["calm_trades"] / total) * 100
        disc_pct   = (r["disc_trades"] / total) * 100

        smi = (
            sample_pct * 0.30 +
            win_pct    * 0.25 +
            calm_pct   * 0.25 +
            disc_pct   * 0.20
        )
        maturity = r["strategy__maturity_status"] or "testing"
        result.append({
            "strategy_id":     str(r["strategy_id"]),
            "strategy_name":   r["strategy__strategy_name"],
            "total_trades":    r["total_trades"],
            "smi_score":       round(smi, 1),
            "maturity_status": maturity,
            "maturity_label":  maturity.capitalize(),
            "win_rate":        round(win_pct, 1),
            "sample_progress": round(sample_pct, 1),
        })

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main response builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_response(snapshot, user) -> dict:
    s = snapshot

    scorecard = [
        # 1. DIS
        {
            "code":         "DIS",
            "label":        "Discipline Integrity Score",
            "value":        _f(s.di_score),
            "unit":         "%",
            "status":       _status_dis(s.di_score),
            "trend":        "Improving" if _f(s.di_score, 0) >= 60 else "Declining",
            "what_it_means": f"You follow your rules {_f(s.di_score)}% of the time",
            "evidence":     _evidence_dis(user),
            "cta":          {"label": "Review Rules & Limits", "type": "rules"},
        },
        # 2. VMI
        {
            "code":         "VMI",
            "label":        "Violation Momentum Index",
            "value":        _f(s.vmi_score, 0),
            "unit":         "",
            "status":       _status_vmi(s.vmi_level),
            "trend":        s.vmi_level or "Low",
            "what_it_means": "Your mistakes are "
                + ("clustered" if (s.vmi_level or "Low") == "High"
                   else "slightly clustering" if (s.vmi_level or "Low") == "Medium"
                   else "spread out — low momentum"),
            "evidence":     _evidence_vmi(s),
            "cta":          {"label": "Complete Quick Journal", "type": "journal"},
        },
        # 3. DRT
        {
            "code":         "DRT",
            "label":        "Discipline Recovery Time",
            "value":        _f(s.drt_days),
            "unit":         "sessions",
            "status":       _status_drt(s.drt_days),
            "trend":        "Stable",
            "what_it_means": f"You recover discipline in {_f(s.drt_days)} session(s) after violations",
            "evidence":     _evidence_drt(s),
            "cta":          {"label": "Watch Quick Recovery Lesson", "type": "learn"},
        },
        # 4. TPR
        {
            "code":         "TPR",
            "label":        "Trading Permission Ratio",
            "value":        _f(s.tpr_score),
            "unit":         "%",
            "status":       _status_tpr(s.tpr_score),
            "trend":        "Stable",
            "what_it_means": f"{_f(s.tpr_score)}% of your sessions give you full trading permission",
            "evidence":     _evidence_tpr(s),
            "cta":          {"label": "View Session History", "type": "discipline"},
        },
        # 5. FIE
        {
            "code":         "FIE",
            "label":        "Forced Inactivity Effectiveness",
            "value":        _f(s.fie_amount, 0),
            "unit":         "₹",
            "status":       _status_fie(s.fie_amount),
            "trend":        "Neutral",
            "what_it_means": f"Estimated {_fmt_inr(s.fie_amount)} protected by RED-session stops",
            "evidence":     _evidence_fie(s),
            "cta":          {"label": "View RED Sessions", "type": "discipline"},
        },
        # 6. OVR
        {
            "code":         "OVR",
            "label":        "Override Resistance Score",
            "value":        _f(s.ovr_score),
            "unit":         "/10",
            "status":       _status_ovr(s.ovr_score),
            "trend":        "Stable",
            "what_it_means": f"You scored {_f(s.ovr_score)}/10 in resisting system overrides",
            "evidence":     _evidence_ovr(s),
            "cta":          {"label": "Review Override Events", "type": "discipline"},
        },
        # 7. ECI
        {
            "code":         "ECI",
            "label":        "Emotion Cost Index",
            "value":        _f(s.eci_amount, 0),
            "unit":         "₹",
            "status":       _status_eci(s.eci_amount),
            "trend":        "Critical" if _status_eci(s.eci_amount) == "critical" else "Stable",
            "what_it_means": f"Emotional trades cost you {_fmt_inr(abs(float(s.eci_amount or 0)))}",
            "evidence":     _evidence_eci(s),
            "cta":          {"label": "Review Emotional Patterns", "type": "journal"},
        },
        # 8. CAS
        {
            "code":         "CAS",
            "label":        "Confidence Accuracy Score",
            "value":        _f(s.cas_score),
            "unit":         "%",
            "status":       _status_cas(s.cas_score),
            "trend":        "Stable",
            "what_it_means": f"Your high-confidence calls are accurate {_f(s.cas_score)}% of the time",
            "evidence":     _evidence_cas(s),
            "cta":          {"label": "View Confidence Analysis", "type": "reports"},
        },
        # 9. DAE
        {
            "code":         "DAE",
            "label":        "Discipline-Adjusted Expectancy",
            "value":        _f(s.dae_r, 0),
            "unit":         "₹",
            "status":       _status_dae(s.dae_r),
            "trend":        "Positive" if float(s.dae_r or 0) > 0 else "Negative",
            "what_it_means": f"Avg P&L per disciplined trade is {_fmt_inr(s.dae_r)}",
            "evidence":     _evidence_dae(s),
            "cta":          {"label": "View Expectancy Report", "type": "reports"},
        },
        # 10. SMI
        {
            "code":         "SMI",
            "label":        "Strategy Maturity Index",
            "value":        _f(s.smi_score, 0),
            "unit":         "/100",
            "status":       _status_smi(s.smi_status),
            "trend":        (s.smi_status or "testing").capitalize(),
            "what_it_means": f"Your top strategy is {(s.smi_status or 'testing').lower()} with score {_f(s.smi_score, 0)}/100",
            "evidence":     _evidence_smi(s),
            "cta":          {"label": "View Strategy Details", "type": "strategies"},
        },
        # 11. DDR
        {
            "code":         "DDR",
            "label":        "Discipline Dependency Ratio",
            "value":        _f(s.ddr_score),
            "unit":         "%",
            "status":       _status_ddr(s.ddr_level),
            "trend":        s.ddr_level or "Low",
            "what_it_means": f"Discipline accounts for {_f(s.ddr_score)}% of your P&L edge",
            "evidence":     _evidence_ddr(s),
            "cta":          {"label": "View Behaviour Report", "type": "reports"},
        },
        # 12. CPI
        {
            "code":         "CPI",
            "label":        "Capital Protection Index",
            "value":        _f(s.cpi_score) if s.cpi_score is not None else None,
            "unit":         "%",
            "status":       _status_cpi(s.cpi_score) if s.cpi_score is not None else "neutral",
            "trend":        "Stable",
            "what_it_means": (
                f"You protected capital on {_f(s.cpi_score)}% of trading days"
                if s.cpi_score is not None
                else "Set your trading capital to enable CPI tracking"
            ),
            "evidence":     _evidence_cpi(s) if s.cpi_score is not None else "No trading capital set",
            "cta":          {"label": "Set Capital & Rules", "type": "rules"},
        },
    ]

    categories = [
        {
            "name":         "Discipline & Behaviour",
            "metric_count": 3,
            "metrics":      ["DIS", "DRT", "VMI"],
        },
        {
            "name":         "Session & Control",
            "metric_count": 3,
            "metrics":      ["TPR", "FIE", "OVR"],
        },
        {
            "name":         "Psychology + Performance",
            "metric_count": 3,
            "metrics":      ["ECI", "CAS", "DAE"],
        },
        {
            "name":         "System Intelligence",
            "metric_count": 3,
            "metrics":      ["SMI", "DDR", "CPI"],
        },
    ]

    strategy_health = _build_strategy_health(user)

    return {
        "scorecard":       scorecard,
        "categories":      categories,
        "strategy_health": strategy_health,
        "meta": {
            "snapshot_date": str(s.snapshot_date),
            "calculated_at": s.calculated_at.isoformat() if s.calculated_at else None,
            "total_metrics": len(scorecard),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def metrics_view(request):
    """
    GET /api/insights/metrics/

    Returns all 12 proprietary metrics in a structure the frontend can
    consume directly — no additional mapping needed on the client side.

    Response shape:
      {
        "scorecard": [ ...12 metric card objects... ],
        "categories": [ ...4 category groupings... ],
        "strategy_health": [ ...per-strategy SMI rows... ],
        "meta": { "snapshot_date", "calculated_at", "total_metrics" }
      }
    """
    snapshot = calculate_metrics(request.user, snapshot_date=date.today())
    return Response(_build_response(snapshot, request.user))
