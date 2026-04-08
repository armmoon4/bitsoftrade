"""
Reports — Behavior / discipline report data.
"""
from __future__ import annotations
from datetime import date, timedelta
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from .utils import fmt_date


RULE_CATEGORY_MAP = {
    "risk":        "Risk Management",
    "time":        "Time Management",
    "process":     "Position Sizing",
    "psychology":  "Entry Rules",
    "other":       "Exit Rules",
}

# Ordered list of frontend category labels (preserves display order)
ADHERENCE_CATEGORIES = [
    "Risk Management",
    "Entry Rules",
    "Exit Rules",
    "Position Sizing",
    "Time Management",
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def get_behavior_report_data(user, qs, filters) -> dict:
    from insights.serializers import MetricsSnapshotSerializer
    from insights.services import calculate_metrics

    try:
        snapshot = calculate_metrics(user)
    except Exception:
        snapshot = None

    snapshot_data = MetricsSnapshotSerializer(snapshot).data if snapshot else {}

    kpis = _build_kpis(user, qs, snapshot, filters)
    violations_timeline = _violations_timeline(user, filters)
    formatted_heatmap, top_recurring, total_mistake_losses = _mistake_analysis(user, qs)
    insight_text = _behavior_insight(
        kpis["ECI"]["value"], total_mistake_losses, top_recurring
    )
    rule_adherence = _rule_adherence(user, qs, filters)

    return {
        "kpis": kpis,
        "snapshot": snapshot_data,
        "violations_timeline": violations_timeline,
        "mistake_heatmap": formatted_heatmap,
        "top_recurring_mistakes": top_recurring,
        "behavior_insight": insight_text,
        "rule_adherence": rule_adherence,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _trend_direction(current: float, previous: float) -> tuple[str, str]:
    """
    Return (trend_label, arrow) by comparing current vs previous value.
    For scores where HIGHER is BETTER (DIS, ECI).
    """
    if current > previous + 0.5:
        return "Improving", "↗"
    if current < previous - 0.5:
        return "Declining", "↘"
    return "Stable", "—"


def _trend_direction_lower_better(current: float, previous: float) -> tuple[str, str]:
    """Like _trend_direction but for metrics where LOWER is BETTER (VMI, DRT)."""
    if current < previous - 0.5:
        return "Improving", "↗"
    if current > previous + 0.5:
        return "Declining", "↘"
    return "Stable", "—"


def _get_prior_snapshot(user):
    """Return the most recent snapshot from more than 7 days ago, or None."""
    from insights.models import UserMetricSnapshot
    cutoff = date.today() - timedelta(days=7)
    return (
        UserMetricSnapshot.objects
        .filter(user=user, snapshot_date__lt=cutoff)
        .order_by("-snapshot_date")
        .first()
    )


def _build_kpis(user, qs, snapshot, filters) -> dict:
    from discipline.models import ViolationsLog

    total_trades = qs.count()

    # Execution Consistency Index (ECI) — % of trades with NO hard violation
    violated_count = (
        ViolationsLog.objects
        .filter(user=user, trade__in=qs, violation_type="hard")
        .values("trade_id")
        .distinct()
        .count()
    )
    eci = (
        round((total_trades - violated_count) / total_trades * 100, 1)
        if total_trades
        else 100.0
    )

    # Safe getters from snapshot
    def _snap(attr, default=0.0):
        if snapshot is None:
            return default
        val = getattr(snapshot, attr, None)
        return float(val) if val is not None else default

    dis_val   = _snap("di_score",  100.0)
    vmi_val   = _snap("vmi_score", 0.0)
    drt_val   = _snap("drt_days",  0.0)
    vmi_level = (snapshot.vmi_level or "Low") if snapshot else "Low"

    # Trend computation via prior snapshot (7+ days ago)
    prior = _get_prior_snapshot(user)

    prior_dis = float(prior.di_score)  if prior and prior.di_score  is not None else dis_val
    prior_vmi = float(prior.vmi_score) if prior and prior.vmi_score is not None else vmi_val
    prior_drt = float(prior.drt_days)  if prior and prior.drt_days  is not None else drt_val

    dis_trend_label, dis_arrow = _trend_direction(dis_val, prior_dis)
    vmi_trend_label, vmi_arrow = _trend_direction_lower_better(vmi_val, prior_vmi)
    drt_trend_label, drt_arrow = _trend_direction_lower_better(drt_val, prior_drt)

    # ECI trend — compare vs prior 30-day window (days -37 to -7)
    eci_trend_label = "Stable"
    eci_arrow = "—"
    if prior is not None:
        from tradelog.models import Trade
        prior_period_qs = Trade.objects.filter(
            user=user,
            deleted_at__isnull=True,
            trade_date__lt=date.today() - timedelta(days=7),
            trade_date__gte=date.today() - timedelta(days=37),
        )
        prior_total = prior_period_qs.count()
        if prior_total:
            prior_violated = (
                ViolationsLog.objects
                .filter(user=user, trade__in=prior_period_qs, violation_type="hard")
                .values("trade_id")
                .distinct()
                .count()
            )
            prior_eci = round((prior_total - prior_violated) / prior_total * 100, 1)
            eci_trend_label, eci_arrow = _trend_direction(eci, prior_eci)

    return {
        "DIS": {
            "value": dis_val,
            "trend": dis_trend_label,
            "arrow": dis_arrow,
        },
        "VMI": {
            "value": vmi_val,
            "trend": vmi_level,           # Low / Medium / High label kept for VMI
            "direction": vmi_trend_label, # Improving / Stable / Declining
            "arrow": vmi_arrow,
        },
        "DRT": {
            "value": drt_val,
            "trend": drt_trend_label,
            "arrow": drt_arrow,
        },
        "ECI": {
            "value": eci,
            "trend": eci_trend_label,
            "arrow": eci_arrow,
        },
    }


def _violations_timeline(user, filters) -> list[dict]:
    """
    Build a per-day violations timeline from DisciplineSession records.
    Each entry includes violations_count, hard_violations, soft_violations,
    and session_state so the frontend can colour-code days (green/yellow/red).
    Gaps (days with no session) are filled with zero-count entries.
    """
    from discipline.models import DisciplineSession

    from_date = filters.get("from")
    to_date   = filters.get("to")

    today = date.today()
    range_from = from_date if from_date else today - timedelta(days=6)
    range_to   = to_date   if to_date   else today

    qs = DisciplineSession.objects.filter(
        user=user,
        session_date__gte=range_from,
        session_date__lte=range_to,
    ).values(
        "session_date", "session_state", "peak_state",
        "violations_count", "hard_violations", "soft_violations",
    )

    sessions_by_date = {entry["session_date"]: entry for entry in qs}

    timeline = []
    current = range_from
    while current <= range_to:
        if current in sessions_by_date:
            entry = sessions_by_date[current]
            timeline.append({
                "date":             fmt_date(current),
                "session_state":    entry["session_state"],
                "peak_state":       entry["peak_state"],
                "violations":       entry["violations_count"],
                "hard_violations":  entry["hard_violations"],
                "soft_violations":  entry["soft_violations"],
            })
        else:
            timeline.append({
                "date":             fmt_date(current),
                "session_state":    None,
                "peak_state":       None,
                "violations":       0,
                "hard_violations":  0,
                "soft_violations":  0,
            })
        current += timedelta(days=1)

    return timeline


def _mistake_analysis(user, qs) -> tuple[list[dict], list[dict], float]:
    """
    Build mistake heatmap and top recurring mistakes from TradeMistake records.

    - Heatmap: {mistake_name -> {date -> count}}
    - Top recurring: sorted by occurrences desc, then loss%, then name.
    - Pads with ALL admin-defined mistakes (and any user-custom mistakes)
      that had zero occurrences so the frontend always shows a full list.
    """
    from mistakes.models import TradeMistake, Mistake

    trade_ids   = qs.values_list("id", flat=True)
    mistakes_qs = (
        TradeMistake.objects
        .filter(trade__in=trade_ids)
        .select_related("mistake", "trade")
    )

    heatmap_data:  dict[str, dict[str, int]] = {}
    mistake_stats: dict[str, dict]           = {}
    total_mistake_losses                      = 0.0

    for tm in mistakes_qs:
        name    = tm.mistake.mistake_name
        day_str = fmt_date(tm.trade.trade_date)
        pnl     = float(tm.trade.total_pnl or 0)

        # Heatmap: count occurrences per mistake per day
        heatmap_data.setdefault(name, {})
        heatmap_data[name][day_str] = heatmap_data[name].get(day_str, 0) + 1

        # Stats: count + loss per mistake
        stats = mistake_stats.setdefault(name, {"count": 0, "loss": 0.0})
        stats["count"] += 1
        if pnl < 0:
            loss = abs(pnl)
            stats["loss"]        += loss
            total_mistake_losses += loss

    formatted_heatmap = [
        {"mistake_type": name, "occurrences": dates}
        for name, dates in heatmap_data.items()
    ]

    # Build top_recurring from actual data
    top_recurring_map: dict[str, dict] = {
        name: {
            "name":        name,
            "occurrences": stats["count"],
            "loss_percent": round(stats["loss"] / total_mistake_losses * 100, 1)
            if total_mistake_losses else 0,
        }
        for name, stats in mistake_stats.items()
    }

    # Pad with ALL admin-defined mistakes that had zero occurrences
    # (replaces the old hardcoded DEFAULT_MISTAKES list)
    admin_mistakes = (
        Mistake.objects
        .filter(is_admin_defined=True, deleted_at__isnull=True)
        .values_list("mistake_name", flat=True)
    )
    for name in admin_mistakes:
        if name not in top_recurring_map:
            top_recurring_map[name] = {"name": name, "occurrences": 0, "loss_percent": 0}

    # Also pad with user-custom mistakes that had zero occurrences
    user_mistakes = (
        Mistake.objects
        .filter(user=user, is_admin_defined=False, deleted_at__isnull=True)
        .values_list("mistake_name", flat=True)
    )
    for name in user_mistakes:
        if name not in top_recurring_map:
            top_recurring_map[name] = {"name": name, "occurrences": 0, "loss_percent": 0}

    # Sort: highest occurrences first, then loss_percent, then alphabetical
    top_recurring = sorted(
        top_recurring_map.values(),
        key=lambda x: (-x["occurrences"], -x["loss_percent"], x["name"]),
    )

    return formatted_heatmap, top_recurring, total_mistake_losses


def _behavior_insight(eci: float, total_mistake_losses: float, top_recurring: list[dict]) -> str:
    """Generate a dynamic, contextual insight message."""
    has_mistakes = any(m["occurrences"] > 0 for m in top_recurring)
    top = next((m for m in top_recurring if m["occurrences"] > 0), None)

    if eci < 80:
        base = (
            "Most losses occurred on days with multiple rule violations. "
            "Mistakes cluster after the first loss of the session, suggesting emotional carry-over."
        )
        if top:
            base += (
                f" '{top['name']}' is your most frequent offender — "
                "consider adding a pre-trade checklist to catch it early."
            )
        return base

    if has_mistakes and top:
        return (
            f"Mistakes cluster heavily around '{top['name']}', "
            f"contributing to {top['loss_percent']}% of your mistake-related losses. "
            "Review your session triggers before the next trade."
        )

    return "Discipline is stable. Keep executing your edge consistently."


def _rule_adherence(user, qs, filters) -> dict:
    """
    Compute per-category rule adherence % from ViolationsLog.
    Each category starts at 100% and is reduced by the % of trades
    that had violations in that category.
    """
    from discipline.models import ViolationsLog

    from_date = filters.get("from")
    to_date   = filters.get("to")

    vqs = ViolationsLog.objects.filter(user=user)
    if from_date:
        vqs = vqs.filter(violated_at__gte=from_date)
    if to_date:
        vqs = vqs.filter(violated_at__lte=to_date)

    total_trades = qs.count()

    # Initialise all frontend category keys at 100%
    adherence: dict[str, float] = {cat: 100.0 for cat in ADHERENCE_CATEGORIES}

    if not total_trades:
        return adherence

    for row in vqs.values("rule__category").annotate(count=Count("id")):
        raw_cat     = (row["rule__category"] or "other").lower()
        display_cat = RULE_CATEGORY_MAP.get(raw_cat, "Exit Rules")  # fallback bucket

        pct_violated = (row["count"] / total_trades) * 100
        adherence[display_cat] = max(
            0.0, round(adherence[display_cat] - pct_violated, 1)
        )

    return adherence