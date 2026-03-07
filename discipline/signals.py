"""
Rule Evaluation Engine (signal fallback) — runs after every trade save.
Primary evaluation is in rules/engine.py called from tradelog/views.py.
This signal acts as a safety net for any direct Trade model saves outside views.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta, datetime, time as dtime
from decimal import Decimal

# Fields that do NOT need rule re-evaluation (they don't affect trade counts or P&L)
_SKIP_EVAL_FIELDS = frozenset(['total_pnl', 'is_tagged_complete', 'is_disciplined', 'session'])


@receiver(post_save, sender='tradelog.Trade')
def run_rule_evaluation(sender, instance, created, **kwargs):
    """
    Rule evaluation triggered by the post_save signal.
    This is the SINGLE source of rule evaluation — views must NOT call
    evaluate_rules_for_user directly, as that causes stale session overwrites.

    Skips evaluation on partial update_fields saves that don't affect trade data.
    """
    from tradelog.models import Trade
    from discipline.models import DisciplineSession

    # Skip evaluation if only non-trade-significant fields were updated
    update_fields = kwargs.get('update_fields')
    if update_fields and set(update_fields).issubset(_SKIP_EVAL_FIELDS):
        return

    trade = instance
    user = trade.user

    # Get or create the DisciplineSession for this trade's date
    # Always fetch fresh from DB — never use a stale in-memory session object.
    session, created = DisciplineSession.objects.get_or_create(
        user=user,
        session_date=trade.trade_date,
        defaults={'session_state': 'green'},
    )

    # Ensure lock_cycle_started_at is set — it drives the per-cycle quota.
    # Use the start of the session day (midnight) so that ALL trades saved on
    # that day from the very first one are included in the cycle count.
    # (Using timezone.now() here would exclude the just-saved trade because
    # it was committed to DB before this signal runs.)
    if created or session.lock_cycle_started_at is None:
        day_start = timezone.make_aware(
            datetime.combine(session.session_date, dtime.min)
        )
        session.lock_cycle_started_at = day_start
        session.save(update_fields=['lock_cycle_started_at'])

    # Attach trade to session if not already linked
    if trade.session_id is None:
        Trade.objects.filter(pk=trade.pk).update(session=session)
        trade.session = session

    # Delegate to the central engine. Passing `trade` enables per_trade scope.
    from rules.engine import evaluate_rules_for_user
    evaluate_rules_for_user(user=user, session=session, trade=trade)

    # Update is_disciplined flag: True only if no hard violations this cycle
    from discipline.models import ViolationsLog
    current_cycle = session.lock_cycle or 0
    has_hard_violation = ViolationsLog.objects.filter(
        session=session,
        trade=trade,
        violation_type='hard',
        lock_cycle=current_cycle,
    ).exists()
    Trade.objects.filter(pk=trade.pk).update(is_disciplined=not has_hard_violation)

