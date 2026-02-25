"""
Rule Evaluation Engine — runs after every trade save.
Evaluates all active rules for the user and updates the DisciplineSession.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal


@receiver(post_save, sender='tradelog.Trade')
def run_rule_evaluation(sender, instance, created, **kwargs):
    """Evaluate rules and update discipline session after every trade save."""
    from tradelog.models import Trade
    from discipline.models import DisciplineSession, ViolationsLog
    from rules.models import Rule

    trade = instance
    user = trade.user

    # Get or create today's session
    session, _ = DisciplineSession.objects.get_or_create(
        user=user,
        session_date=trade.trade_date,
        defaults={'session_state': 'green'}
    )

    # Attach trade to session
    if trade.session_id is None:
        Trade.objects.filter(pk=trade.pk).update(session=session)
        trade.session = session

    # Load all active rules for this user (admin defaults + user custom)
    from django.db.models import Q
    rules = Rule.objects.filter(
        is_active=True,
        deleted_at__isnull=True
    ).filter(
        Q(is_admin_defined=True) | Q(user=user)
    )

    hard_violated = []
    soft_violated = []

    for rule in rules:
        violated = _evaluate_rule(rule, user, trade, session)
        if violated:
            if rule.rule_type == 'hard':
                hard_violated.append(rule)
            else:
                soft_violated.append(rule)

    # Determine new session state (can only escalate)
    if hard_violated:
        new_state = 'red'
    elif soft_violated:
        new_state = 'yellow' if session.session_state == 'green' else session.session_state
    else:
        new_state = session.session_state

    # Session can only escalate within a day
    state_rank = {'green': 0, 'yellow': 1, 'red': 2}
    if state_rank.get(new_state, 0) > state_rank.get(session.session_state, 0):
        session.session_state = new_state

        # Set cooldown
        if new_state == 'yellow':
            session.cooldown_ends_at = timezone.now() + timedelta(minutes=45)
        elif new_state == 'red':
            session.cooldown_ends_at = timezone.now() + timedelta(hours=2)

    # Update counts
    for rule in hard_violated + soft_violated:
        if str(rule.id) not in (session.rules_violated or []):
            session.rules_violated = (session.rules_violated or []) + [str(rule.id)]
            session.violations_count = (session.violations_count or 0) + 1

            vtype = 'hard' if rule in hard_violated else 'soft'
            if vtype == 'hard':
                session.hard_violations = (session.hard_violations or 0) + 1
            else:
                session.soft_violations = (session.soft_violations or 0) + 1

            ViolationsLog.objects.create(
                user=user,
                session=session,
                trade=trade,
                rule=rule,
                violation_type=vtype,
                session_state_after=session.session_state,
            )

    session.save()

    # Update trade is_disciplined flag
    is_disciplined = len(hard_violated) == 0
    Trade.objects.filter(pk=trade.pk).update(is_disciplined=is_disciplined)


def models_filter(user):
    """Build Q filter: admin global rules OR this user's custom rules."""
    from django.db.models import Q
    return Q(is_admin_defined=True) | Q(user=user)


def _evaluate_rule(rule, user, trade, session):
    """
    Returns True if the rule is violated.
    Implements the 5 built-in rule types from the spec.
    """
    from tradelog.models import Trade
    condition = rule.trigger_condition or {}

    try:
        if rule.category == 'risk' and 'maxLoss' in condition:
            # Max Daily Loss Limit
            daily_pnl = _get_daily_pnl(user, trade.trade_date)
            max_loss = Decimal(str(condition.get('maxLoss', 0)))
            max_pct = condition.get('maxDailyPercent')
            if daily_pnl < -abs(max_loss):
                return True
            if max_pct and user.trading_capital:
                loss_pct = abs(daily_pnl) / user.trading_capital * 100
                if daily_pnl < 0 and loss_pct > Decimal(str(max_pct)):
                    return True

        elif rule.category == 'risk' and 'maxPositionPercent' in condition:
            # Position Size Limit
            if trade.entry_price and trade.quantity and user.trading_capital:
                position_value = trade.entry_price * trade.quantity
                position_pct = position_value / user.trading_capital * 100
                if position_pct > Decimal(str(condition['maxPositionPercent'])):
                    return True

        elif rule.category == 'process' and 'maxTrades' in condition:
            # Max Trades Per Day
            today_count = Trade.objects.filter(
                user=user,
                trade_date=trade.trade_date,
                deleted_at__isnull=True
            ).count()
            if today_count > int(condition['maxTrades']):
                return True

        elif rule.category == 'psychology' and 'consecutiveLosses' in condition:
            # Consecutive Loss Limit
            recent_trades = Trade.objects.filter(
                user=user,
                deleted_at__isnull=True
            ).order_by('-trade_date', '-trade_time')[:int(condition['consecutiveLosses']) + 1]
            streak = 0
            for t in recent_trades:
                if t.total_pnl is not None and t.total_pnl < 0:
                    streak += 1
                else:
                    break
            if streak >= int(condition['consecutiveLosses']):
                return True

    except Exception:
        pass

    return False


def _get_daily_pnl(user, date):
    from tradelog.models import Trade
    from django.db.models import Sum
    result = Trade.objects.filter(
        user=user, trade_date=date, deleted_at__isnull=True
    ).aggregate(total=Sum('total_pnl'))
    return result['total'] or Decimal('0')
