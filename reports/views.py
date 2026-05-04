"""
Reports Module — API Wrappers.
"""
from datetime import date, timedelta

from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import HasToolSubscription

from .services import (
    get_behavior_report_data,
    get_journal_report_data,
    get_mistakes_report_data,
    get_performance_report_data,
    get_risk_report_data,
    get_strategy_report_data,
)


# ---------------------------------------------------------------------------
# Shared filter helper
# ---------------------------------------------------------------------------

def _get_filtered_trades(user, request):
    """
    Apply the full tradelog-compatible filter set to the Trade queryset.

    Supported query parameters
    --------------------------
    Date range
        date_range      today | this_week | this_month | custom
        date_from       YYYY-MM-DD  (used when date_range=custom)
        date_to         YYYY-MM-DD  (used when date_range=custom)
        from            YYYY-MM-DD  legacy alias for date_from
        to              YYYY-MM-DD  legacy alias for date_to

    Instrument / account
        broker          broker_name (case-insensitive), e.g. zerodha
        market_type     indian_market | forex | crypto | options
        instrument_type alias for market_type (same DB field)
        market          legacy alias for market_type
        direction       long | short
        strategy        <strategy-uuid>

    Outcome
        outcome         win | loss | open
        filter          wins | losses | disciplined | violations  (quick-filter tab)
        pnl_min         decimal lower bound for total_pnl
        pnl_max         decimal upper bound for total_pnl

    Psychology / discipline
        emotional_state calm | anxious | confident | fearful | fomo |
                        angry | overconfident | uncertain
        discipline_status  disciplined | violations  → is_disciplined boolean
        review_status   tagged | untagged             → is_tagged_complete boolean

    JSON array fields
        rule_breach     comma-separated violation_modes values
        mistakes        comma-separated violation_modes values (alias)
        tags            comma-separated — searched in violation_modes AND
                        rules_followed JSON arrays

    Free-text
        search          matches symbol, broker_name, or lessons_learned
    """
    from tradelog.models import Trade

    # Only closed trades (total_pnl set) are meaningful for all reports
    qs = Trade.objects.filter(user=user, deleted_at__isnull=True, total_pnl__isnull=False)

    p = request.query_params  # shorthand

    # ------------------------------------------------------------------
    # 1. Date range
    # ------------------------------------------------------------------
    date_range = p.get("date_range")
    today = date.today()

    if date_range == "today":
        qs = qs.filter(trade_date=today)

    elif date_range == "this_week":
        week_start = today - timedelta(days=today.weekday())
        qs = qs.filter(trade_date__gte=week_start, trade_date__lte=today)

    elif date_range == "this_month":
        qs = qs.filter(trade_date__year=today.year, trade_date__month=today.month)

    else:
        # custom or legacy from/to params
        date_from = p.get("date_from") or p.get("from")
        date_to   = p.get("date_to")   or p.get("to")
        if date_from:
            try:
                qs = qs.filter(trade_date__gte=date_from)
            except (ValueError, TypeError):
                pass  # ignore malformed date strings
        if date_to:
            try:
                qs = qs.filter(trade_date__lte=date_to)
            except (ValueError, TypeError):
                pass  # ignore malformed date strings

    # ------------------------------------------------------------------
    # 2. Instrument / account
    # ------------------------------------------------------------------
    broker = p.get("broker")
    if broker and broker != "all":
        qs = qs.filter(broker_name__iexact=broker)

    # market_type / instrument_type / market — same DB field
    market_type = p.get("market_type") or p.get("instrument_type") or p.get("market")
    if market_type and market_type.lower() != "all":
        # Use iexact so 'Indian_Market' or 'FOREX' from frontend still match
        qs = qs.filter(market_type__iexact=market_type)

    direction = p.get("direction")
    if direction:
        direction = direction.lower()
    if direction in ("long", "short"):
        qs = qs.filter(direction=direction)

    strategy = p.get("strategy")
    if strategy:
        import uuid as _uuid
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            # Try treating it as a UUID directly
            strategy_uuid = _uuid.UUID(strategy)
            qs = qs.filter(strategy_id=strategy_uuid)
        except (ValueError, AttributeError, DjangoValidationError):
            # Fall back: look up strategy by name (case-insensitive)
            from strategies.models import Strategy as StrategyModel
            matched_ids = StrategyModel.objects.filter(
                strategy_name__iexact=strategy,
                deleted_at__isnull=True,
            ).values_list("id", flat=True)
            qs = qs.filter(strategy_id__in=list(matched_ids))

    # ------------------------------------------------------------------
    # 3. Outcome
    # ------------------------------------------------------------------
    outcome = p.get("outcome")
    if outcome:
        outcome = outcome.lower()
    if outcome == "win":
        qs = qs.filter(total_pnl__gt=0)
    elif outcome == "loss":
        qs = qs.filter(total_pnl__lt=0)
    elif outcome == "open":
        # NOTE: base queryset already requires total_pnl__isnull=False (closed trades).
        # open trades have no total_pnl so they are already excluded.
        # Re-filter on exit_price to be explicit, but result will naturally be empty
        # for a pure reports endpoint; harmless guard kept for forward-compatibility.
        qs = qs.filter(exit_price__isnull=True)

    # Quick-filter tab (wins / losses / disciplined / violations)
    quick = p.get("filter")
    if quick == "wins":
        qs = qs.filter(total_pnl__gt=0)
    elif quick == "losses":
        qs = qs.filter(total_pnl__lt=0)
    elif quick == "disciplined":
        qs = qs.filter(is_disciplined=True)
    elif quick == "violations":
        qs = qs.filter(is_disciplined=False)

    # P&L bounds
    pnl_min = p.get("pnl_min")
    pnl_max = p.get("pnl_max")
    if pnl_min is not None:
        try:
            qs = qs.filter(total_pnl__gte=float(pnl_min))
        except ValueError:
            pass
    if pnl_max is not None:
        try:
            qs = qs.filter(total_pnl__lte=float(pnl_max))
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # 4. Psychology / discipline
    # ------------------------------------------------------------------
    emotional_state = p.get("emotional_state")
    if emotional_state:
        qs = qs.filter(emotional_state__iexact=emotional_state)

    discipline_status = p.get("discipline_status")
    if discipline_status:
        discipline_status = discipline_status.lower()
    if discipline_status == "disciplined":
        qs = qs.filter(is_disciplined=True)
    elif discipline_status in ("violations", "violation"):  # accept both singular & plural
        qs = qs.filter(is_disciplined=False)

    review_status = p.get("review_status")
    if review_status:
        review_status = review_status.lower()
    if review_status == "tagged":
        qs = qs.filter(is_tagged_complete=True)
    elif review_status == "untagged":
        qs = qs.filter(is_tagged_complete=False)

    # ------------------------------------------------------------------
    # 5. JSON array fields
    # ------------------------------------------------------------------
    # rule_breach / mistakes → violation_modes JSON array (OR logic per value)
    rule_breach_raw = p.get("rule_breach") or p.get("mistakes")
    if rule_breach_raw:
        from django.db.models import Q
        values = [v.strip() for v in rule_breach_raw.split(",") if v.strip()]
        if values:
            q = Q()
            for v in values:
                q |= Q(violation_modes__icontains=v)
            qs = qs.filter(q)

    # tags → searched in violation_modes AND rules_followed
    tags_raw = p.get("tags")
    if tags_raw:
        from django.db.models import Q
        tag_values = [v.strip() for v in tags_raw.split(",") if v.strip()]
        if tag_values:
            q = Q()
            for v in tag_values:
                q |= Q(violation_modes__icontains=v)
                q |= Q(rules_followed__icontains=v)
            qs = qs.filter(q)

    # ------------------------------------------------------------------
    # 6. Free-text search
    # ------------------------------------------------------------------
    search = p.get("search")
    if search:
        from django.db.models import Q
        qs = qs.filter(
            Q(symbol__icontains=search)
            | Q(broker_name__icontains=search)
            | Q(lessons_learned__icontains=search)
        )

    return qs


# ---------------------------------------------------------------------------
# Report views
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def performance_report_view(request):
    """GET /api/reports/performance/"""
    qs = _get_filtered_trades(request.user, request)
    data = get_performance_report_data(qs)
    return Response(data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def risk_report_view(request):
    """GET /api/reports/risk/"""
    qs = _get_filtered_trades(request.user, request)
    capital = request.user.trading_capital
    data = get_risk_report_data(qs, capital_base_fallback=capital)
    return Response(data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def behavior_report_view(request):
    """GET /api/reports/behavior/"""
    qs = _get_filtered_trades(request.user, request)
    filters = _date_filters(request)
    data = get_behavior_report_data(request.user, qs, filters)
    return Response(data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def strategy_report_view(request):
    """GET /api/reports/strategy/"""
    qs = _get_filtered_trades(request.user, request)
    data = get_strategy_report_data(qs)
    return Response(data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def journal_report_view(request):
    """GET /api/reports/journal/"""
    qs = _get_filtered_trades(request.user, request)
    filters = _date_filters(request)
    data = get_journal_report_data(request.user, qs, filters)
    return Response(data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def mistake_report_view(request):
    """GET /api/reports/mistakes/"""
    qs = _get_filtered_trades(request.user, request)
    data = get_mistakes_report_data(qs)
    return Response(data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def overview_report_view(request):
    """GET /api/reports/overview/"""
    from .services import get_overview_report_data

    qs = _get_filtered_trades(request.user, request)
    filters = _date_filters(request)
    data = get_overview_report_data(request.user, qs, filters)
    return Response(data)


# ---------------------------------------------------------------------------
# Internal utility
# ---------------------------------------------------------------------------

def _date_filters(request) -> dict:
    """
    Return the resolved from/to strings that behavior/journal/overview
    sub-functions expect, honouring both the new date_range shortcut and
    the legacy from/to params.
    """
    p = request.query_params
    today = date.today()
    date_range = p.get("date_range")

    if date_range == "today":
        return {"from": str(today), "to": str(today)}

    if date_range == "this_week":
        week_start = today - timedelta(days=today.weekday())
        return {"from": str(week_start), "to": str(today)}

    if date_range == "this_month":
        month_start = today.replace(day=1)
        return {"from": str(month_start), "to": str(today)}

    # custom or legacy
    return {
        "from": p.get("date_from") or p.get("from"),
        "to":   p.get("date_to")   or p.get("to"),
    }