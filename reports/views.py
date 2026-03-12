"""
Reports Module — API Wrappers.
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions
from rest_framework.response import Response

from .services import (
    get_performance_report_data,
    get_risk_report_data,
    get_behavior_report_data,
    get_strategy_report_data,
    get_journal_report_data,
    get_mistakes_report_data
)

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


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def performance_report_view(request):
    """GET /api/reports/performance/"""
    qs = _get_filtered_trades(request.user, request)
    data = get_performance_report_data(qs)
    return Response(data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def risk_report_view(request):
    """GET /api/reports/risk/"""
    qs = _get_filtered_trades(request.user, request)
    capital = request.user.trading_capital
    data = get_risk_report_data(qs, capital_base_fallback=capital)
    return Response(data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def behavior_report_view(request):
    """GET /api/reports/behavior/"""
    qs = _get_filtered_trades(request.user, request)
    filters = {
        'from': request.query_params.get('from'),
        'to': request.query_params.get('to'),
    }
    data = get_behavior_report_data(request.user, qs, filters)
    return Response(data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def strategy_report_view(request):
    """GET /api/reports/strategy/"""
    qs = _get_filtered_trades(request.user, request)
    data = get_strategy_report_data(qs)
    return Response(data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def journal_report_view(request):
    """GET /api/reports/journal/"""
    qs = _get_filtered_trades(request.user, request)
    filters = {
        'from': request.query_params.get('from'),
        'to': request.query_params.get('to'),
    }
    data = get_journal_report_data(request.user, qs, filters)
    return Response(data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def mistake_report_view(request):
    """GET /api/reports/mistakes/"""
    qs = _get_filtered_trades(request.user, request)
    data = get_mistakes_report_data(qs)
    return Response(data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def overview_report_view(request):
    """GET /api/reports/overview/"""
    from .services import get_overview_report_data
    qs = _get_filtered_trades(request.user, request)
    filters = {
        'from': request.query_params.get('from'),
        'to': request.query_params.get('to'),
    }
    data = get_overview_report_data(request.user, qs, filters)
    return Response(data)

