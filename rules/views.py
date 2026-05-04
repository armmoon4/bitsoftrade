from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q, Sum
from accounts.permissions import HasToolSubscription
from .models import Rule, TradeRule
from .serializers import RuleSerializer, RuleTitleSerializer, SystemRuleUpdateSerializer, TradeRuleSerializer


class RuleListCreateView(generics.ListCreateAPIView):
    """
    GET /api/rules/ — list current user's rules + admin defaults.
      Use ?is_active=true to see only active rules.
      Use ?is_active=false to see only inactive rules.
      Omit the parameter to see ALL non-deleted rules.
    POST /api/rules/ — create a user custom rule.
    """
    serializer_class = RuleSerializer
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]

    def get_queryset(self):
        qs = Rule.objects.filter(
            deleted_at__isnull=True
        ).filter(
            Q(is_admin_defined=True) | Q(user=self.request.user)
        )

        is_active_param = self.request.query_params.get('is_active')
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ['true', '1', 't', 'y', 'yes']
            qs = qs.filter(is_active=is_active_bool)

        return qs.order_by('-is_admin_defined', 'category', 'rule_name')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, is_admin_defined=False)


class RuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PUT / PATCH / DELETE /api/rules/<id>/"""
    serializer_class = RuleSerializer
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]

    def get_queryset(self):
        return Rule.objects.filter(
            deleted_at__isnull=True
        ).filter(
            Q(is_admin_defined=True) | Q(user=self.request.user)
        )

    def update(self, request, *args, **kwargs):
        rule = self.get_object()
        if rule.is_admin_defined:
            return Response(
                {'error': 'Admin-defined rules cannot be modified.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if rule.is_system_rule:
            return Response(
                {'error': 'System rules can only be updated via PATCH /api/rules/system/<id>/.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        rule = self.get_object()
        if rule.is_admin_defined:
            return Response(
                {'error': 'Admin-defined rules cannot be deleted.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if rule.is_system_rule:
            return Response(
                {'error': 'System rules cannot be deleted.'},
                status=status.HTTP_403_FORBIDDEN
            )
        rule.deleted_at = timezone.now()
        rule.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RuleTitleListView(generics.ListAPIView):
    """
    GET /api/rules/list/ — list only IDs and titles of current user's rules + admin defaults.
    """
    serializer_class = RuleTitleSerializer
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]

    def get_queryset(self):
        qs = Rule.objects.filter(
            deleted_at__isnull=True
        ).filter(
            Q(is_admin_defined=True) | Q(user=self.request.user)
        )

        is_active_param = self.request.query_params.get('is_active')
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ['true', '1', 't', 'y', 'yes']
            qs = qs.filter(is_active=is_active_bool)

        return qs.order_by('-is_admin_defined', 'category', 'rule_name')


# ── System Rules ──────────────────────────────────────────────────────────────

class SystemRuleListView(generics.ListAPIView):
    """
    GET /api/rules/system/

    List all system rules that belong to the authenticated user.
    Supports ?is_active=true/false filter.
    """
    serializer_class = SystemRuleUpdateSerializer
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]

    def get_queryset(self):
        qs = Rule.objects.filter(
            user=self.request.user,
            is_system_rule=True,
            deleted_at__isnull=True,
        )

        is_active_param = self.request.query_params.get('is_active')
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ['true', '1', 't', 'y', 'yes']
            qs = qs.filter(is_active=is_active_bool)

        return qs.order_by('created_at')


class SystemRuleUpdateView(APIView):
    """
    GET    /api/rules/system/<uuid:pk>/  — retrieve a single system rule.
    PATCH  /api/rules/system/<uuid:pk>/  — update threshold and/or is_active.

    Allowed PATCH fields
    --------------------
    * trigger_condition  — must keep the same condition key; only the numeric
                           threshold may change.
                           Example: {"trigger_condition": {"maxLoss": 3000}}
    * is_active          — boolean toggle.

    Forbidden operations
    --------------------
    * PUT / DELETE — always 405 Method Not Allowed.
    * Changing rule_name, category, rule_type, trigger_scope, action, etc.
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get_rule(self, pk, user):
        return get_object_or_404(
            Rule,
            pk=pk,
            user=user,
            is_system_rule=True,
            deleted_at__isnull=True,
        )

    def get(self, request, pk, *args, **kwargs):
        rule = self._get_rule(pk, request.user)
        serializer = SystemRuleUpdateSerializer(rule)
        return Response(serializer.data)

    def patch(self, request, pk, *args, **kwargs):
        rule = self._get_rule(pk, request.user)
        serializer = SystemRuleUpdateSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def put(self, request, pk, *args, **kwargs):
        return Response(
            {'error': 'Full replacement of system rules is not allowed. Use PATCH.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def delete(self, request, pk, *args, **kwargs):
        return Response(
            {'error': 'System rules cannot be deleted.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )
    
class TradeRuleListCreateView(generics.ListCreateAPIView):
    serializer_class = TradeRuleSerializer
    permission_classes = [permissions.IsAuthenticated, HasToolSubscription]

    def get_queryset(self):
        return TradeRule.objects.filter(trade__user=self.request.user)

    def perform_create(self, serializer):
        rule = serializer.validated_data['rule']

        # Block system rules from being tagged
        if rule.is_system_rule:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("System rules cannot be tagged to trades.")

        serializer.save()


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def rule_evaluate_debug(request):
    """
    GET /api/rules/evaluate-debug/

    Runs the full rule engine against the current active session and
    returns a structured diagnostic report — useful when "session stays green"
    despite obvious violations.

    Also force-triggers re-evaluation for the active session so any missed
    violations get detected immediately.
    """
    from decimal import Decimal
    from tradelog.models import Trade
    from discipline.models import DisciplineSession, ViolationsLog
    from rules.engine import get_active_locked_session, _evaluate_single_rule, _STATE_SEVERITY
    from django.utils.timezone import localdate

    user = request.user

    # Determine the session to evaluate
    active_session = get_active_locked_session(user)
    if active_session is None:
        active_session, _ = DisciplineSession.objects.get_or_create(
            user=user,
            session_date=localdate(),
            defaults={'session_state': 'green'},
        )
    active_session.refresh_from_db()

    session_date = active_session.session_date
    today_trades = Trade.objects.filter(
        user=user, trade_date=session_date, deleted_at__isnull=True
    )
    cycle_start = active_session.lock_cycle_started_at

    active_rules = Rule.objects.filter(
        deleted_at__isnull=True,
        is_active=True,
    ).filter(
        Q(is_admin_defined=True) | Q(user=user)
    )

    rule_results = []
    for rule in active_rules:
        triggered, violation_type = _evaluate_single_rule(
            rule, user, today_trades, trade=None, session=active_session
        )
        current_cycle = active_session.lock_cycle or 0
        already_logged = ViolationsLog.objects.filter(
            session=active_session,
            rule=rule,
            lock_cycle=current_cycle,
        ).exists()

        # For maxTrades: show cycle-filtered count
        cond = rule.trigger_condition or {}
        trades_in_cycle = None
        if 'maxTrades' in cond and cycle_start:
            trades_in_cycle = today_trades.filter(created_at__gte=cycle_start).count()

        rule_results.append({
            'rule_id': str(rule.id),
            'rule_name': rule.rule_name,
            'rule_type': rule.rule_type,
            'trigger_scope': rule.trigger_scope,
            'trigger_condition': cond,
            'is_active': rule.is_active,
            'triggered': triggered,
            'already_logged_this_cycle': already_logged,
            'would_escalate': triggered and not already_logged,
            'trades_in_cycle': trades_in_cycle,
        })

    # Aggregate trade data for diagnosis
    all_trade_count = today_trades.count()
    closed_trades = today_trades.filter(total_pnl__isnull=False)
    total_pnl_sum = closed_trades.aggregate(s=Sum('total_pnl'))['s'] or Decimal('0')
    cycle_trade_count = (
        today_trades.filter(created_at__gte=cycle_start).count()
        if cycle_start else all_trade_count
    )

    return Response({
        'session': {
            'id': str(active_session.id),
            'session_date': str(session_date),
            'session_state': active_session.session_state,
            'peak_state': active_session.peak_state,
            'lock_cycle': active_session.lock_cycle,
            'lock_cycle_started_at': active_session.lock_cycle_started_at,
            'violations_count': active_session.violations_count,
            'hard_violations': active_session.hard_violations,
            'soft_violations': active_session.soft_violations,
        },
        'trades': {
            'total_on_date': all_trade_count,
            'in_current_cycle': cycle_trade_count,
            'closed_trades': closed_trades.count(),
            'total_pnl_closed': float(total_pnl_sum),
        },
        'rules_evaluated': len(rule_results),
        'rules': rule_results,
        'diagnosis': (
            'Rules are triggering — re-evaluate to escalate session.'
            if any(r['would_escalate'] for r in rule_results)
            else (
                'No rules triggered. Check: (1) Are trades closed (have exit_price)? '
                '(2) Do losses exceed maxLoss threshold? '
                '(3) Does trade count exceed maxTrades in current cycle?'
            )
        ),
    })