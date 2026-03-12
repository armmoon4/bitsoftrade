from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Count, Sum, Q
from .models import Mistake, TradeMistake
from .serializers import MistakeSerializer, TradeMistakeSerializer


class MistakeListCreateView(generics.ListCreateAPIView):
    """GET /api/mistakes/ — admin global + user custom mistakes.
       POST /api/mistakes/ — create user custom mistake."""
    serializer_class = MistakeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Mistake.objects.filter(
            deleted_at__isnull=True
        ).filter(
            Q(is_admin_defined=True) | Q(user=self.request.user)
        ).order_by('-is_admin_defined', 'category')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, is_custom=True, is_admin_defined=False)


class MistakeDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MistakeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Mistake.objects.filter(user=self.request.user, deleted_at__isnull=True)

    def destroy(self, request, *args, **kwargs):
        mistake = self.get_object()
        if mistake.is_admin_defined:
            return Response({'error': 'Admin-defined mistakes cannot be deleted.'},
                            status=status.HTTP_403_FORBIDDEN)
        mistake.deleted_at = timezone.now()
        mistake.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TradeMistakeListCreateView(generics.ListCreateAPIView):
    """Link / unlink mistakes to trades."""
    serializer_class = TradeMistakeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TradeMistake.objects.filter(trade__user=self.request.user)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def mistakes_analytics_view(request):
    """
    GET /api/mistakes/analytics/
    Returns usage counts, trends, impact, severity distribution, and clustering detection.
    """
    user = request.user
    from datetime import date, timedelta
    today = date.today()
    last_30 = today - timedelta(days=30)
    prev_30 = today - timedelta(days=60)

    # All trade mistakes for this user
    user_trade_mistakes = TradeMistake.objects.filter(trade__user=user)

    # Usage count per mistake
    usage = user_trade_mistakes.values(
        'mistake__id', 'mistake__mistake_name', 'mistake__description',
        'mistake__category', 'mistake__severity_weight'
    ).annotate(count=Count('id')).order_by('-count')

    # Trend: last 30 vs previous 30
    last_30_counts = user_trade_mistakes.filter(
        tagged_at__date__gte=last_30
    ).values('mistake__id').annotate(count=Count('id'))
    prev_30_counts = user_trade_mistakes.filter(
        tagged_at__date__gte=prev_30, tagged_at__date__lt=last_30
    ).values('mistake__id').annotate(count=Count('id'))

    last_30_map = {str(x['mistake__id']): x['count'] for x in last_30_counts}
    prev_30_map = {str(x['mistake__id']): x['count'] for x in prev_30_counts}

    usage_with_trend = []
    for item in usage:
        mid = str(item['mistake__id'])
        l30 = last_30_map.get(mid, 0)
        p30 = prev_30_map.get(mid, 0)
        if l30 > p30:
            trend = 'Increasing'
        elif l30 < p30:
            trend = 'Decreasing'
        else:
            trend = 'Stable'
        usage_with_trend.append({**item, 'trend': trend, 'last_30': l30, 'prev_30': p30})

    # Impact metrics
    from tradelog.models import Trade
    all_user_trades = Trade.objects.filter(user=user, deleted_at__isnull=True)
    total_trades_count = all_user_trades.count()

    impacted_trade_ids = user_trade_mistakes.values_list('trade_id', flat=True).distinct()
    impacted_trades = all_user_trades.filter(id__in=impacted_trade_ids)
    impacted_count = impacted_trades.count()
    total_pnl_impact = impacted_trades.aggregate(total=Sum('total_pnl'))['total'] or 0

    clean_trades = all_user_trades.exclude(id__in=impacted_trade_ids)
    clean_trades_count = clean_trades.count()

    # Success rate for clean trades
    if clean_trades_count > 0:
        clean_winning_count = clean_trades.filter(total_pnl__gt=0).count()
        clean_success_rate = (clean_winning_count / clean_trades_count) * 100
    else:
        clean_success_rate = 0

    if total_trades_count > 0:
        impacted_percentage = (impacted_count / total_trades_count) * 100
    else:
        impacted_percentage = 0

    impact = {
        'impacted_count': impacted_count,
        'impacted_percentage': round(impacted_percentage, 1),
        'total_pnl_impact': round(float(total_pnl_impact), 2),
        'clean_trades_count': clean_trades_count,
        'clean_success_rate': round(clean_success_rate, 1)
    }

    # Clustering detection
    last_5_trades = all_user_trades.order_by('-trade_date', '-trade_time')[:5]
    last_5_ids = [t.id for t in last_5_trades]
    recent_mistakes_count = TradeMistake.objects.filter(trade_id__in=last_5_ids).count()

    if total_trades_count > 0:
        avg_mistakes_per_trade = user_trade_mistakes.count() / total_trades_count
        avg_per_5 = avg_mistakes_per_trade * 5
    else:
        avg_per_5 = 0

    is_above_average = recent_mistakes_count > avg_per_5

    clustering = {
        'recent_mistakes_count': recent_mistakes_count,
        'is_above_average': is_above_average,
        'average_per_5': round(avg_per_5, 1)
    }

    # Severity distribution
    severity_dist = {
        'low': user_trade_mistakes.filter(mistake__severity_weight__lte=4).count(),
        'medium': user_trade_mistakes.filter(mistake__severity_weight__gt=4, mistake__severity_weight__lte=7).count(),
        'high': user_trade_mistakes.filter(mistake__severity_weight__gt=7).count(),
    }

    return Response({
        'usage': list(usage_with_trend),
        'impact': impact,
        'clustering': clustering,
        'severity_distribution': severity_dist,
    })
