"""
Rule Evaluation Engine — BitsOfTrade
=====================================
Called after EVERY trade save or import.
Evaluates all active rules for the user, writes ViolationsLog entries,
and escalates the discipline session state: GREEN → YELLOW → RED.

Session state can only escalate within a lock cycle, never auto-downgrade.
On unlock, the lock_cycle increments so the same rule can re-fire.

IMPORTANT — Cooldown:
Cooldown timer is set ONLY in discipline/views.py unlock_session_view
when the user clicks complete_all. This engine does NOT set cooldown_ends_at.
This ensures the timer starts from the user's action, not from the violation.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# ─── State Severity Ordering ──────────────────────────────────────────────────
_STATE_SEVERITY = {'green': 0, 'yellow': 1, 'red': 2}

# NOTE: Cooldown minutes are defined in discipline/views.py unlock_session_view.
# They are not used here — the engine never sets cooldown_ends_at.
_COOLDOWN_YELLOW_MINUTES = 2   # kept for reference only — not used in engine
_COOLDOWN_RED_MINUTES = 5      # kept for reference only — not used in engine


def evaluate_rules_for_user(user, session, trade=None):
    """
    Main entry point — evaluate all active rules for the user against the
    current session and today's trades. Updates `session` in place.

    Args:
        user:    CustomUser instance
        session: DisciplineSession instance for today
        trade:   The specific Trade that just triggered this evaluation (optional).
                 Used for per_trade scope rules.
    """
    from rules.models import Rule
    from discipline.models import ViolationsLog
    from tradelog.models import Trade as TradeModel

    try:
        # Always reload the session from DB before evaluating.
        session.refresh_from_db()

        active_rules = Rule.objects.filter(
            deleted_at__isnull=True,
            is_active=True,
        ).filter(
            Q(is_admin_defined=True) | Q(user=user)
        )

        today = session.session_date
        today_trades = TradeModel.objects.filter(
            user=user, trade_date=today, deleted_at__isnull=True
        )

        rule_count = active_rules.count()
        trade_count = today_trades.count()
        logger.info(
            f"[RuleEngine] user={user.id} date={today} "
            f"rules={rule_count} trades_today={trade_count} "
            f"session_state={session.session_state}"
        )
        print(
            f"[RuleEngine] user={user.id} date={today} "
            f"rules={rule_count} trades_today={trade_count} "
            f"session_state={session.session_state}"
        )

        current_severity = _STATE_SEVERITY.get(session.session_state, 0)
        new_severity = current_severity   # only grows, never shrinks

        # Track whether any new violation was logged this evaluation
        newly_logged_count = 0

        for rule in active_rules:
            triggered, violation_type = _evaluate_single_rule(
                rule, user, today_trades, trade=trade, session=session
            )
            print(
                f"[RuleEngine]   rule='{rule.rule_name}' "
                f"triggered={triggered} type={violation_type}"
            )

            if triggered:
                current_cycle = session.lock_cycle or 0

                # For per_trade rules, scope duplicate check to this specific
                # trade so each trade can independently trigger the rule.
                if rule.trigger_scope == 'per_trade' and trade is not None:
                    already_logged = ViolationsLog.objects.filter(
                        session=session,
                        rule=rule,
                        trade=trade,
                        lock_cycle=current_cycle,
                    ).exists()
                else:
                    # per_day / per_session: one log per rule per cycle
                    already_logged = ViolationsLog.objects.filter(
                        session=session,
                        rule=rule,
                        lock_cycle=current_cycle,
                    ).exists()

                print(
                    f"[RuleEngine]   already_logged={already_logged} "
                    f"lock_cycle={current_cycle}"
                )

                if not already_logged:
                    new_state_for_log = 'red' if violation_type == 'hard' else 'yellow'

                    ViolationsLog.objects.create(
                        user=user,
                        session=session,
                        rule=rule,
                        trade=trade,
                        violation_type=violation_type,
                        session_state_after=new_state_for_log,
                        lock_cycle=current_cycle,
                    )
                    newly_logged_count += 1
                    print(f"[RuleEngine]   ViolationsLog CREATED → state={new_state_for_log}")

                    # ── Create rule violation notification ────────────────────
                    try:
                        from notifications.utils import create_rule_notification
                        create_rule_notification(
                            user=user,
                            rule=rule,
                            session=session,
                            trade=trade,
                            violation_type=violation_type,
                        )
                    except Exception as notif_err:
                        logger.error(f"[RuleEngine] Failed to create rule notification: {notif_err}")

                    # Track on session
                    if str(rule.id) not in (session.rules_violated or []):
                        session.rules_violated = (session.rules_violated or []) + [str(rule.id)]
                        session.violations_count = (session.violations_count or 0) + 1
                        if violation_type == 'hard':
                            session.hard_violations = (session.hard_violations or 0) + 1
                        else:
                            session.soft_violations = (session.soft_violations or 0) + 1

                if violation_type == 'hard':
                    new_severity = max(new_severity, _STATE_SEVERITY['red'])
                else:
                    new_severity = max(new_severity, _STATE_SEVERITY['yellow'])

        print(
            f"[RuleEngine] new_severity={new_severity} current_severity={current_severity} "
            f"newly_logged={newly_logged_count} "
            f"→ state_will_escalate={new_severity > current_severity}"
        )

        if new_severity > current_severity:
            new_state = _severity_to_state(new_severity)
            session.session_state = new_state

            # Update peak_state (highest state ever reached — never downgraded)
            peak_severity = _STATE_SEVERITY.get(session.peak_state, 0)
            if new_severity > peak_severity:
                session.peak_state = new_state

            # DO NOT set cooldown_ends_at here.
            # Cooldown is started exclusively in discipline/views.py
            # unlock_session_view when the user clicks complete_all.
            # This way the timer starts from the user's action, not the violation.

            session.required_actions_completed = False

            print(f"[RuleEngine] saving session → state={session.session_state}")
            session.save(update_fields=[
                'session_state',
                'peak_state',
                'required_actions_completed',
                'rules_violated',
                'violations_count',
                'hard_violations',
                'soft_violations',
            ])

            # ── Create session lock notification ──────────────────────────────
            try:
                from notifications.utils import create_session_notification
                if new_state in ('yellow', 'red'):
                    create_session_notification(user=user, session=session, event='locked')
            except Exception as notif_err:
                logger.error(f"[RuleEngine] Failed to create session notification: {notif_err}")

        elif newly_logged_count > 0:
            print(f"[RuleEngine] saving session counters only (no state change)")
            session.save(update_fields=[
                'rules_violated',
                'violations_count',
                'hard_violations',
                'soft_violations',
            ])
        else:
            print(f"[RuleEngine] no changes — skipping session save")

    except Exception as e:
        logger.error(f"Rule Evaluation Engine error for user {user.id}: {str(e)}")
        print(f"[RuleEngine] EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()


# ─── Individual Rule Evaluators ───────────────────────────────────────────────

def _evaluate_single_rule(rule, user, today_trades, trade=None, session=None):
    """
    Evaluate one rule against today's trade data.
    Respects rule.trigger_scope:
      - 'per_day'      → aggregate across all trades today
      - 'per_trade'    → evaluate only on the single triggering trade
      - 'per_session'  → only evaluate when session is already non-green

    Returns (triggered: bool, violation_type: 'hard'|'soft')
    """
    try:
        cond = rule.trigger_condition or {}
        triggered = False
        scope = rule.trigger_scope or 'per_day'

        # per_session scope: skip evaluation entirely if session is still green.
        # These rules only apply once the user has already triggered at least
        # one violation in the current session (state is yellow or red).
        if scope == 'per_session':
            if session is None or session.session_state == 'green':
                return False, rule.rule_type

        # ── 1. Max Daily Loss Limit ──────────────────────────────────────────
        if 'maxLoss' in cond:
            if scope == 'per_trade' and trade is not None:
                trade_pnl = trade.total_pnl or Decimal('0')
                max_loss = cond.get('maxLoss')
                if max_loss is not None and trade_pnl < 0 and abs(trade_pnl) >= Decimal(str(max_loss)):
                    triggered = True
            else:
                triggered = _check_daily_loss(user, today_trades, cond)

        # ── 2. Position Size Limit ───────────────────────────────────────────
        elif 'maxPositionSize' in cond:
            if scope == 'per_trade' and trade is not None:
                max_size = cond.get('maxPositionSize')
                if max_size is not None:
                    position_value = (trade.entry_price or 0) * (trade.quantity or 0)
                    if position_value > Decimal(str(max_size)):
                        triggered = True
            else:
                triggered = _check_position_size(user, today_trades, cond)

        # ── 3. Max Trades Per Day ────────────────────────────────────────────
        elif 'maxTrades' in cond:
            cycle_start = session.lock_cycle_started_at if session else None
            triggered = _check_max_trades(today_trades, cond, cycle_start=cycle_start)

        # ── 4. Consecutive Loss Limit ────────────────────────────────────────
        elif 'consecutiveLosses' in cond:
            triggered = _check_consecutive_losses(user, cond)

        return triggered, rule.rule_type

    except Exception as e:
        logger.warning(f"Could not evaluate rule {rule.id} ({rule.rule_name}): {str(e)}")
        return False, rule.rule_type


def _check_daily_loss(user, today_trades, cond):
    """Max Daily Loss — absolute INR amount only."""
    agg = today_trades.aggregate(daily_pnl=Sum('total_pnl'))
    daily_pnl = agg.get('daily_pnl') or Decimal('0')

    if daily_pnl >= 0:
        return False

    abs_loss = abs(daily_pnl)

    max_loss = cond.get('maxLoss')
    if max_loss is not None and abs_loss >= Decimal(str(max_loss)):
        return True

    return False


def _check_position_size(user, today_trades, cond):
    """Position Size — check if any trade exceeded the max absolute position value."""
    max_size = cond.get('maxPositionSize')
    if not max_size:
        return False

    threshold = Decimal(str(max_size))

    for trade in today_trades:
        position_value = (trade.entry_price or 0) * (trade.quantity or 0)
        if position_value > threshold:
            return True

    return False


def _check_max_trades(today_trades, cond, cycle_start=None):
    """
    Max Trades Per Day — count trades in the current lock cycle only.

    Args:
        today_trades: QuerySet of today's trades for this user.
        cond:         Rule trigger_condition dict containing 'maxTrades'.
        cycle_start:  datetime of when the current lock cycle began.
                      When provided, only trades created at or after this
                      timestamp are counted, giving each cycle a fresh quota.
    """
    max_trades = cond.get('maxTrades')
    if max_trades is None:
        return False

    qs = today_trades
    if cycle_start is not None:
        qs = qs.filter(created_at__gte=cycle_start)

    count = qs.count()
    print(
        f"[RuleEngine]   _check_max_trades: cycle_start={cycle_start} "
        f"count={count} max={max_trades}"
    )
    return count > int(max_trades)


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


def is_session_locked(user, date=None):
    """
    Returns (is_locked: bool, message: str).

    A session is locked when:
      - state is 'red' (always blocked until manually unlocked), OR
      - state is 'yellow' AND cooldown is still active, OR
      - state is 'yellow' AND cooldown has elapsed but required_actions_completed
        is still False (user hasn't clicked the Complete button yet).

    Used by tradelog views to block trade creation/import when locked.
    Note: For import, this is only checked ONCE before the import starts —
    never inside the per-trade loop.
    """
    from discipline.models import DisciplineSession
    from django.utils.timezone import localdate

    target_date = date or localdate()
    try:
        session = DisciplineSession.objects.get(user=user, session_date=target_date)
    except DisciplineSession.DoesNotExist:
        return False, ''

    date_str = '' if not date else f' for {target_date}'

    if session.session_state == 'red':
        return True, (
            f'Your trading session{date_str} is locked (RED). '
            'Complete the required actions in the Discipline section to unlock.'
        )

    if session.session_state == 'yellow':
        # Still in active cooldown window
        if session.cooldown_ends_at and timezone.now() < session.cooldown_ends_at:
            remaining = max(1, int((session.cooldown_ends_at - timezone.now()).total_seconds() // 60))
            return True, (
                f'Your trading session{date_str} is in cooldown (YELLOW). '
                f'{remaining} minute(s) remaining. '
                'Complete the Quick Journal in the Discipline section to unlock.'
            )

        # Cooldown elapsed but user hasn't completed required actions yet.
        if not session.required_actions_completed:
            return True, (
                f'Your trading session{date_str} is locked (YELLOW — cooldown elapsed). '
                'Please complete the Quick Journal in the Discipline section to unlock.'
            )

    return False, ''