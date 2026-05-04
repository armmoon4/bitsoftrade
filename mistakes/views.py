from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Count, Sum, Q
from accounts.permissions import HasToolSubscription
from .models import Mistake, TradeMistake
from .serializers import MistakeSerializer, MistakeSimpleSerializer, TradeMistakeSerializer


class MistakeListCreateView(generics.ListCreateAPIView):
    """GET /api/mistakes/ — admin global + user custom mistakes.
       POST /api/mistakes/ — create user custom mistake."""
    serializer_class = MistakeSerializer
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]

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
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]

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
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]

    def get_queryset(self):
        return TradeMistake.objects.filter(trade__user=self.request.user)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def mistakes_analytics_view(request):
    """
    GET /api/mistakes/analytics/
    Returns:
      - mistake_frequency_last_30  : ranked list of mistake_mode occurrences (last 30 days)
      - impact                     : trades with mistakes, loss, clean trades
      - severity_distribution      : high / medium / low counts across ALL mistake tags
    All calculations use every TradeMistake record for the authenticated user.
    """
    from datetime import date, timedelta
    from tradelog.models import Trade

    user = request.user
    today = date.today()
    last_30 = today - timedelta(days=30)

    # ── All TradeMistakes for this user (all time) ────────────────────────────
    user_trade_mistakes = TradeMistake.objects.filter(trade__user=user)

    # ── 1. Mistake Frequency (Last 30 Days) — grouped by mistake_mode ─────────
    last_30_qs = user_trade_mistakes.filter(tagged_at__date__gte=last_30)

    mode_counts = (
        last_30_qs
        .values('mistake__mistake_mode')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    MODE_LABELS = dict(Mistake.MISTAKE_MODE)

    mistake_frequency = []
    for rank, item in enumerate(mode_counts, start=1):
        raw_mode = item['mistake__mistake_mode']
        label = MODE_LABELS.get(raw_mode, raw_mode) if raw_mode else 'Unclassified'
        mistake_frequency.append({
            'rank': rank,
            'mistake_mode': raw_mode,
            'label': label,
            'count': item['count'],
        })

    # ── 2. Mistake Impact ─────────────────────────────────────────────────────
    all_user_trades = Trade.objects.filter(user=user, deleted_at__isnull=True)
    total_trades_count = all_user_trades.count()

    impacted_trade_ids = user_trade_mistakes.values_list('trade_id', flat=True).distinct()
    impacted_trades = all_user_trades.filter(id__in=impacted_trade_ids)
    impacted_count = impacted_trades.count()
    loss_from_mistake_trades = impacted_trades.aggregate(total=Sum('total_pnl'))['total'] or 0

    clean_trades = all_user_trades.exclude(id__in=impacted_trade_ids)
    clean_trades_count = clean_trades.count()

    if clean_trades_count > 0:
        clean_winning = clean_trades.filter(total_pnl__gt=0).count()
        clean_success_rate = round((clean_winning / clean_trades_count) * 100, 1)
    else:
        clean_success_rate = 0

    impacted_percentage = (
        round((impacted_count / total_trades_count) * 100, 1)
        if total_trades_count > 0 else 0
    )

    impact = {
        'trades_with_mistakes': impacted_count,
        'trades_with_mistakes_percentage': impacted_percentage,
        'loss_from_mistake_trades': round(float(loss_from_mistake_trades), 2),
        'clean_trades_count': clean_trades_count,
        'clean_success_rate': clean_success_rate,
    }

    # ── 3. Severity Distribution (all time) ───────────────────────────────────
    high_count = user_trade_mistakes.filter(mistake__severity_weight__gt=7).count()
    medium_count = user_trade_mistakes.filter(
        mistake__severity_weight__gt=4, mistake__severity_weight__lte=7
    ).count()
    low_count = user_trade_mistakes.filter(mistake__severity_weight__lte=4).count()

    severity_distribution = {
        'high': {
            'count': high_count,
            'range': '8-10',
            'label': 'Critical mistakes to eliminate',
        },
        'medium': {
            'count': medium_count,
            'range': '5-7',
            'label': 'Needs improvement',
        },
        'low': {
            'count': low_count,
            'range': '1-4',
            'label': 'Minor issues',
        },
    }

    return Response({
        'mistake_frequency_last_30': mistake_frequency,
        'impact': impact,
        'severity_distribution': severity_distribution,
    })


class MistakeSimpleListView(generics.ListAPIView):
    """GET /api/mistakes/simple/ — returns only id and mistake_name for dropdowns/quick lists."""
    serializer_class = MistakeSimpleSerializer
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]

    def get_queryset(self):
        # .only() optimizes the database query to fetch just these two fields
        return Mistake.objects.filter(
            deleted_at__isnull=True
        ).filter(
            Q(is_admin_defined=True) | Q(user=self.request.user)
        ).select_related('user').only('id', 'mistake_name', 'is_admin_defined', 'category', 'user').order_by('-is_admin_defined', 'category')