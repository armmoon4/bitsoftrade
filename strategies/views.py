import logging
from decimal import Decimal

from django.apps import apps
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from django.utils.decorators import method_decorator

from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import HasToolSubscription
from .models import Strategy
from .serializers import StrategySerializer, StrategyMinimalSerializer

logger = logging.getLogger(__name__)


def _annotate_strategy_metrics(strategy, user_filter=None):
    """Calculate performance metrics for a strategy from its linked trades."""
    default_metrics = {
        'total_trades': 0,
        'win_rate': 0,
        'total_pnl': Decimal('0'),
        'profit_factor': 0,
        'sample_size_progress': 0,
        'max_drawdown': Decimal('0'),
        'max_drawdown_pct': 0,
        'avg_return': Decimal('0'),
        'risk_reward_ratio': 'N/A',
    }

    try:
        Trade = apps.get_model('tradelog', 'Trade')

        qs = Trade.objects.filter(strategy=strategy, deleted_at__isnull=True)
        if user_filter:
            qs = qs.filter(user=user_filter)

        total_trades = qs.count()
        if total_trades == 0:
            return default_metrics

        closed_qs = qs.filter(exit_price__isnull=False).order_by('trade_date', 'created_at')

        closed_trades = closed_qs.values(
            'total_pnl', 'direction', 'entry_price', 'exit_price',
            'quantity', 'fees', 'leverage'
        )

        gross_profit = Decimal('0')
        gross_loss = Decimal('0')
        total_pnl = Decimal('0')
        wins = 0
        losses = 0
        pnl_list = []  # for max drawdown and avg return

        for t in closed_trades:
            pnl = t['total_pnl']

            if pnl is None:
                qty = t['quantity'] or Decimal('0')
                entry = t['entry_price'] or Decimal('0')
                exit_p = t['exit_price'] or Decimal('0')
                fees = t['fees'] or Decimal('0')
                leverage = t['leverage'] or Decimal('1')

                if t['direction'] == 'long':
                    raw = (exit_p - entry) * qty * leverage
                else:
                    raw = (entry - exit_p) * qty * leverage
                pnl = raw - fees

            pnl = Decimal(str(pnl))
            total_pnl += pnl
            pnl_list.append(pnl)

            if pnl > 0:
                wins += 1
                gross_profit += pnl
            elif pnl < 0:
                losses += 1
                gross_loss += abs(pnl)

        closed_count = closed_qs.count()
        win_rate = round((wins / closed_count * 100), 2) if closed_count else 0
        profit_factor = round(float(gross_profit / gross_loss), 2) if gross_loss else 0

        threshold = getattr(strategy, 'sample_size_threshold', 0)
        sample_progress = min(round((total_trades / threshold) * 100, 2), 100) if threshold else 0

        # --- Max Drawdown ---
        # Build equity curve (cumulative PnL) and find the largest peak-to-trough drop
        max_drawdown = Decimal('0')
        max_drawdown_pct = 0
        if pnl_list:
            equity = Decimal('0')
            peak = Decimal('0')
            for pnl in pnl_list:
                equity += pnl
                if equity > peak:
                    peak = equity
                drawdown = peak - equity
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    if peak > 0:
                        max_drawdown_pct = round(float(drawdown / peak) * 100, 2)
                    else:
                        max_drawdown_pct = 0

        # --- Average Return per closed trade ---
        avg_return = round(total_pnl / closed_count, 2) if closed_count else Decimal('0')

        # --- Risk:Reward Ratio ---
        # avg_win / avg_loss  (e.g. 1:2.50 means you risk 1 to gain 2.5)
        avg_win = (gross_profit / wins) if wins else Decimal('0')
        avg_loss = (gross_loss / losses) if losses else Decimal('0')
        if avg_win > 0 and avg_loss > 0:
            rr_ratio = round(float(avg_win / avg_loss), 2)
            risk_reward_ratio = f"1:{rr_ratio}"
        elif avg_win > 0:
            risk_reward_ratio = "1:∞"   # no losses at all
        else:
            risk_reward_ratio = "N/A"

        return {
            'total_trades': total_trades,
            'closed_trades': closed_count,
            'win_rate': win_rate,
            'total_pnl': float(total_pnl),
            'profit_factor': profit_factor,
            'sample_size_progress': sample_progress,
            'max_drawdown': float(max_drawdown),
            'max_drawdown_pct': max_drawdown_pct,
            'avg_return': float(avg_return),
            'risk_reward_ratio': risk_reward_ratio,
        }

    except LookupError:
        logger.error("Trade model could not be found in the 'tradelog' app.")
        return default_metrics
    except Exception as e:
        logger.error(f"Error calculating metrics for strategy {strategy.id}: {str(e)}")
        return default_metrics


class StrategyListCreateView(generics.ListCreateAPIView):
    serializer_class = StrategySerializer
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]

    def get_queryset(self):
        qs = Strategy.objects.filter(user=self.request.user, deleted_at__isnull=True)
        
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(strategy_name__icontains=search) |  # search by name
                Q(tags__icontains=search) |            # search by tags
                Q(trade_type__icontains=search)        # search by segment (intraday/swing/positional)
            )
        return qs

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
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]

    def get_queryset(self):
        return Strategy.objects.filter(user=self.request.user, deleted_at__isnull=True)

    def retrieve(self, request, *args, **kwargs):
        strategy = self.get_object()
        s_data = StrategySerializer(strategy).data
        s_data.update(_annotate_strategy_metrics(strategy, user_filter=request.user))
        return Response(s_data)

    def destroy(self, request, *args, **kwargs):
        strategy = self.get_object()
        strategy.deleted_at = timezone.now()
        strategy.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
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
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def template_strategies_view(request):
    """GET /api/strategies/templates/ — admin-created templates."""
    strategies = Strategy.objects.filter(is_template=True, deleted_at__isnull=True)
    data = [StrategySerializer(s).data for s in strategies]
    return Response(data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def strategy_names_view(request):
    """GET /api/strategies/names/ — returns only id and strategy_name."""
    strategies = Strategy.objects.filter(user=request.user, deleted_at__isnull=True)
    serializer = StrategyMinimalSerializer(strategies, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
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
        entry_rules=original.entry_rules,
        exit_rules=original.exit_rules,
        risk_management_rules=original.risk_management_rules,
        trade_type=original.trade_type,
        sample_size_threshold=original.sample_size_threshold,
        is_public=False,
        is_template=False,
        maturity_status='testing',
    )
    return Response(StrategySerializer(copy).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def assign_trades_view(request, pk):
    """
    POST /api/strategies/<id>/assign-trades/
    Body options (mutually exclusive, first match wins):
      { "trade_ids": ["uuid1", "uuid2", ...] }
      { "assign_all_untagged": true }
      { "assign_all": true }
    """
    Trade = apps.get_model('tradelog', 'Trade')

    strategy = Strategy.objects.filter(
        pk=pk, user=request.user, deleted_at__isnull=True
    ).first()
    if not strategy:
        return Response(
            {'error': 'Strategy not found or does not belong to you.'},
            status=status.HTTP_404_NOT_FOUND
        )

    trade_ids = request.data.get('trade_ids')
    assign_all_untagged = request.data.get('assign_all_untagged', False)
    assign_all = request.data.get('assign_all', False)

    base_qs = Trade.objects.filter(user=request.user, deleted_at__isnull=True)

    if trade_ids:
        qs = base_qs.filter(id__in=trade_ids)
    elif assign_all_untagged:
        qs = base_qs.filter(strategy__isnull=True)
    elif assign_all:
        qs = base_qs
    else:
        return Response(
            {'error': 'Provide trade_ids, assign_all_untagged: true, or assign_all: true.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    count = qs.update(strategy=strategy)

    trades_missing_pnl = Trade.objects.filter(
        strategy=strategy,
        deleted_at__isnull=True,
        exit_price__isnull=False,
        total_pnl__isnull=True,
    )
    for trade in trades_missing_pnl:
        trade.calculate_pnl()
        trade.save(update_fields=['total_pnl'])

    total = Trade.objects.filter(strategy=strategy, deleted_at__isnull=True).count()
    strategy.update_maturity(total)

    s_data = StrategySerializer(strategy).data
    s_data.update(_annotate_strategy_metrics(strategy, user_filter=request.user))

    return Response({
        'assigned': count,
        'strategy': s_data,
    }, status=status.HTTP_200_OK)