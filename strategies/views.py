import logging
from decimal import Decimal

from django.apps import apps
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone

from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Strategy
from .serializers import StrategySerializer

# Set up logging for error tracking
logger = logging.getLogger(__name__)


def _annotate_strategy_metrics(strategy, user_filter=None):
    """Calculate performance metrics for a strategy from its linked trades."""
    # Default fallback values
    default_metrics = {
        'total_trades': 0,
        'win_rate': 0,
        'total_pnl': Decimal('0'),
        'profit_factor': 0,
        'sample_size_progress': 0,
    }

    try:
        # Use apps.get_model to avoid potential circular import issues
        Trade = apps.get_model('tradelog', 'Trade')
        
        qs = Trade.objects.filter(strategy=strategy, deleted_at__isnull=True)
        if user_filter:
            qs = qs.filter(user=user_filter)

        total_trades = qs.count()
        
        # EARLY EXIT: If no trades are linked, return defaults to save DB queries
        if total_trades == 0:
            return default_metrics

        wins = qs.filter(total_pnl__gt=0).count()
        win_rate = round((wins / total_trades * 100), 2)

        agg = qs.aggregate(
            total_pnl=Sum('total_pnl'),
            gross_profit=Sum('total_pnl', filter=Q(total_pnl__gt=0)),
            gross_loss=Sum('total_pnl', filter=Q(total_pnl__lt=0)),
        )
        
        total_pnl = agg.get('total_pnl') or Decimal('0')
        gross_profit = agg.get('gross_profit') or Decimal('0')
        gross_loss = abs(agg.get('gross_loss') or Decimal('0'))
        
        profit_factor = round(float(gross_profit / gross_loss), 2) if gross_loss else 0

        # Safely get the threshold, defaulting to 0 if not set
        threshold = getattr(strategy, 'sample_size_threshold', 0)
        sample_progress = min(round((total_trades / threshold) * 100, 2), 100) if threshold else 0

        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'profit_factor': profit_factor,
            'sample_size_progress': sample_progress,
        }

    except LookupError:
        logger.error("Trade model could not be found in the 'tradelog' app.")
        return default_metrics
    except Exception as e:
        logger.error(f"Error calculating metrics for strategy {strategy.id}: {str(e)}")
        return default_metrics


class StrategyListCreateView(generics.ListCreateAPIView):
    """GET /api/strategies/ — user's strategies.
       POST /api/strategies/ — create new."""
    serializer_class = StrategySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Strategy.objects.filter(user=self.request.user, deleted_at__isnull=True)

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        data = []
        for s in qs:
            s_data = StrategySerializer(s).data
            s_data.update(_annotate_strategy_metrics(s, user_filter=request.user))
            data.append(s_data)
        return Response(data)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class StrategyDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = StrategySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Strategy.objects.filter(user=self.request.user, deleted_at__isnull=True)

    def destroy(self, request, *args, **kwargs):
        strategy = self.get_object()
        strategy.deleted_at = timezone.now()
        strategy.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def community_strategies_view(request):
    """GET /api/strategies/community/ — all public strategies excluding own."""
    strategies = Strategy.objects.filter(
        is_public=True, deleted_at__isnull=True
    ).exclude(user=request.user)
    data = []
    for s in strategies:
        s_data = StrategySerializer(s).data
        s_data.update(_annotate_strategy_metrics(s))
        data.append(s_data)
    return Response(data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def template_strategies_view(request):
    """GET /api/strategies/templates/ — admin-created templates."""
    strategies = Strategy.objects.filter(is_template=True, deleted_at__isnull=True)
    data = [StrategySerializer(s).data for s in strategies]
    return Response(data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def add_to_mine_view(request, pk):
    """POST /api/strategies/<id>/add-to-mine/ — copy community strategy."""
    original = Strategy.objects.filter(pk=pk, is_public=True, deleted_at__isnull=True).first()
    if not original:
        return Response({'error': 'Strategy not found or not public.'}, status=status.HTTP_404_NOT_FOUND)

    copy = Strategy.objects.create(
        user=request.user,
        source_strategy=original,
        strategy_name=f"{original.strategy_name} (Copy)",
        description=original.description,
        tags=original.tags,
        market_types=original.market_types,
        trade_type=original.trade_type,
        sample_size_threshold=original.sample_size_threshold,
        is_public=False,
        is_template=False,
        maturity_status='testing',
    )
    return Response(StrategySerializer(copy).data, status=status.HTTP_201_CREATED)