"""
Rule Evaluation Engine — BitsOfTrade
=====================================
Called after EVERY trade save or import.
Evaluates all active rules for the user, writes ViolationsLog entries,
and escalates the discipline session state: GREEN → YELLOW → RED.

Session state can only escalate within a day, never auto-downgrade.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum, Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# ─── State Severity Ordering ──────────────────────────────────────────────────
_STATE_SEVERITY = {'green': 0, 'yellow': 1, 'red': 2}
_COOLDOWN_YELLOW_MINUTES = 45   # default cooldown for YELLOW
_COOLDOWN_RED_MINUTES = 120     # default cooldown for RED


def evaluate_rules_for_user(user, session):
    """
    Main entry point — evaluate all active rules for the user against the
    current session and today's trades. Updates `session` in place.

    Args:
        user:    CustomUser instance
        session: DisciplineSession instance for today
    """
    from rules.models import Rule
    from discipline.models import ViolationsLog
    from tradelog.models import Trade

    try:
        active_rules = Rule.objects.filter(
            deleted_at__isnull=True,
            is_active=True,
        ).filter(
            Q(is_admin_defined=True) | Q(user=user)
        )

        today = session.session_date
        today_trades = Trade.objects.filter(
            user=user, trade_date=today, deleted_at__isnull=True
        )

        current_severity = _STATE_SEVERITY.get(session.session_state, 0)
        new_severity = current_severity   # only grows, never shrinks

        for rule in active_rules:
            triggered, violation_type = _evaluate_single_rule(rule, user, today_trades)

            if triggered:
                # Log the violation (avoid duplicates per rule per session)
                already_logged = ViolationsLog.objects.filter(
                    session=session, rule=rule
                ).exists()

                if not already_logged:
                    required_severity = _STATE_SEVERITY['red' if violation_type == 'hard' else 'yellow']
                    new_state_for_log = 'red' if violation_type == 'hard' else 'yellow'

                    ViolationsLog.objects.create(
                        user=user,
                        session=session,
                        rule=rule,
                        violation_type=violation_type,
                        session_state_after=new_state_for_log,
                    )

                    # Track on session
                    if str(rule.id) not in session.rules_violated:
                        session.rules_violated = session.rules_violated + [str(rule.id)]
                        session.violations_count += 1
                        if violation_type == 'hard':
                            session.hard_violations += 1
                        else:
                            session.soft_violations += 1

                    # Escalate severity
                    if violation_type == 'hard':
                        new_severity = max(new_severity, _STATE_SEVERITY['red'])
                    else:
                        new_severity = max(new_severity, _STATE_SEVERITY['yellow'])

        # Apply state escalation (never downgrade within same session)
        if new_severity > current_severity:
            new_state = _severity_to_state(new_severity)
            session.session_state = new_state

            # Update peak_state (the highest state ever reached for this session)
            peak_severity = _STATE_SEVERITY.get(session.peak_state, 0)
            if new_severity > peak_severity:
                session.peak_state = new_state

            # Set cooldown if not already set
            if session.cooldown_ends_at is None or session.cooldown_ends_at < timezone.now():
                if new_state == 'yellow':
                    session.cooldown_ends_at = timezone.now() + timedelta(minutes=_COOLDOWN_YELLOW_MINUTES)
                elif new_state == 'red':
                    session.cooldown_ends_at = timezone.now() + timedelta(minutes=_COOLDOWN_RED_MINUTES)

        session.save()

    except Exception as e:
        logger.error(f"Rule Evaluation Engine error for user {user.id}: {str(e)}")


# ─── Individual Rule Evaluators ───────────────────────────────────────────────

def _evaluate_single_rule(rule, user, today_trades):
    """
    Evaluate one rule against today's trade data.
    Returns (triggered: bool, violation_type: 'hard'|'soft')
    """
    try:
        cond = rule.trigger_condition or {}
        triggered = False

        # ── 1. Max Daily Loss Limit ──────────────────────────────────────────
        if 'maxLoss' in cond or 'maxDailyPercent' in cond:
            triggered = _check_daily_loss(user, today_trades, cond)

        # ── 2. Position Size Limit ───────────────────────────────────────────
        elif 'maxPositionPercent' in cond:
            triggered = _check_position_size(user, today_trades, cond)

        # ── 3. Max Trades Per Day ────────────────────────────────────────────
        elif 'maxTrades' in cond:
            triggered = _check_max_trades(today_trades, cond)

        # ── 4. Consecutive Loss Limit ────────────────────────────────────────
        elif 'consecutiveLosses' in cond:
            triggered = _check_consecutive_losses(user, cond)

        return triggered, rule.rule_type

    except Exception as e:
        logger.warning(f"Could not evaluate rule {rule.id} ({rule.rule_name}): {str(e)}")
        return False, rule.rule_type


def _check_daily_loss(user, today_trades, cond):
    """Max Daily Loss — absolute INR or % of capital."""
    agg = today_trades.aggregate(daily_pnl=Sum('total_pnl'))
    daily_pnl = agg.get('daily_pnl') or Decimal('0')

    if daily_pnl >= 0:
        return False  # No loss today

    abs_loss = abs(daily_pnl)

    # Absolute loss check
    max_loss = cond.get('maxLoss')
    if max_loss is not None and abs_loss >= Decimal(str(max_loss)):
        return True

    # Percentage of capital check
    max_pct = cond.get('maxDailyPercent')
    if max_pct is not None and user.trading_capital:
        loss_pct = abs_loss / user.trading_capital * 100
        if loss_pct >= Decimal(str(max_pct)):
            return True

    return False


def _check_position_size(user, today_trades, cond):
    """Position Size — check if any trade exceeded max % of capital."""
    max_pct = cond.get('maxPositionPercent')
    if not max_pct or not user.trading_capital:
        return False

    threshold = Decimal(str(max_pct))
    capital = user.trading_capital

    for trade in today_trades:
        position_value = (trade.entry_price or 0) * (trade.quantity or 0)
        pct = (position_value / capital * 100) if capital else Decimal('0')
        if pct > threshold:
            return True

    return False


def _check_max_trades(today_trades, cond):
    """Max Trades Per Day — count total trades today."""
    max_trades = cond.get('maxTrades')
    if max_trades is None:
        return False
    return today_trades.count() > int(max_trades)


def _check_consecutive_losses(user, cond):
    """Consecutive Loss Limit — check the latest N trades for a loss streak."""
    from tradelog.models import Trade

    limit = cond.get('consecutiveLosses')
    if limit is None:
        return False

    limit = int(limit)
    last_trades = Trade.objects.filter(
        user=user,
        deleted_at__isnull=True,
        total_pnl__isnull=False,
    ).order_by('-trade_date', '-trade_time')[:limit + 1]

    # Count consecutive losses from the most recent trade
    streak = 0
    for trade in last_trades:
        if trade.total_pnl < 0:
            streak += 1
        else:
            break

    return streak >= limit


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _severity_to_state(severity: int) -> str:
    mapping = {0: 'green', 1: 'yellow', 2: 'red'}
    return mapping.get(severity, 'green')
