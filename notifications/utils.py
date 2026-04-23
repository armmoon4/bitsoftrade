"""
notifications/utils.py
─────────────────────
Helper called by the rule engine (rules/engine.py) to create Notification
records whenever a rule violation is logged.

Usage:
    from notifications.utils import create_rule_notification
    create_rule_notification(
        user=user,
        rule=rule,
        session=session,
        trade=trade,           # may be None for per_day rules
        violation_type='hard', # 'hard' | 'soft'
    )
"""
import logging

logger = logging.getLogger(__name__)


def create_rule_notification(user, rule, session, trade=None, violation_type='soft'):
    """
    Create a Notification when a rule is triggered / violated.

    - Hard rule → type='rule_violated', severity='error'
    - Soft rule → type='rule_triggered', severity='warning'
    """
    try:
        from notifications.models import Notification, NotificationSettings

        is_hard = violation_type == 'hard'

        # Check user settings — skip if user has disabled this type
        settings_obj, _ = NotificationSettings.objects.get_or_create(user=user)
        type_field = 'notify_rule_violated' if is_hard else 'notify_rule_triggered'
        if not getattr(settings_obj, type_field):
            logger.info(f"[Notifications] Skipped — user has disabled {type_field}")
            return

        notification_type = 'rule_violated' if is_hard else 'rule_triggered'
        severity = 'error' if is_hard else 'warning'

        title = _build_title(rule, is_hard)
        message = _build_message(rule, session, trade, is_hard)

        Notification.objects.create(
            user=user,
            notification_type=notification_type,
            severity=severity,
            title=title,
            message=message,
            rule=rule,
            session=session,
            trade=trade,
        )

        logger.info(
            f"[Notifications] Created {notification_type} notification "
            f"for user={user.id} rule='{rule.rule_name}'"
        )

    except Exception as e:
        # Never let notification creation crash the rule engine
        logger.error(f"[Notifications] Failed to create notification: {str(e)}")


def create_session_notification(user, session, event='locked'):
    """
    Create a Notification when a session is locked or unlocked.

    event: 'locked' | 'unlocked'
    """
    try:
        from notifications.models import Notification, NotificationSettings

        # Check user settings — skip if user has disabled this type
        settings_obj, _ = NotificationSettings.objects.get_or_create(user=user)
        type_field = 'notify_session_locked' if event == 'locked' else 'notify_session_unlocked'
        if not getattr(settings_obj, type_field):
            logger.info(f"[Notifications] Skipped — user has disabled {type_field}")
            return

        if event == 'locked':
            state = session.session_state.upper()
            notification_type = 'session_locked'
            severity = 'error' if state == 'RED' else 'warning'
            title = f'Trading Session {state} — Locked'
            message = (
                f'Your trading session has been locked ({state}). '
                'Please complete the required actions in the Discipline '
                'section to resume trading.'
            )
        else:
            notification_type = 'session_unlocked'
            severity = 'info'
            title = 'Trading Session Unlocked'
            message = (
                'Your trading session has been unlocked. '
                'You can now resume trading. Stay disciplined!'
            )

        Notification.objects.create(
            user=user,
            notification_type=notification_type,
            severity=severity,
            title=title,
            message=message,
            session=session,
        )

        logger.info(
            f"[Notifications] Created {notification_type} notification "
            f"for user={user.id} session={session.id}"
        )

    except Exception as e:
        logger.error(f"[Notifications] Failed to create session notification: {str(e)}")


# ─── Private helpers ──────────────────────────────────────────────────────────

def _build_title(rule, is_hard):
    action_word = 'Violated' if is_hard else 'Triggered'
    return f'Rule {action_word}: {rule.rule_name}'


def _build_message(rule, session, trade, is_hard):
    """
    Build a human-readable notification message.

    NOTE: We intentionally do NOT read session.session_state here.
    The session state is updated by the rule engine *after* this
    notification is created, so reading it would give a stale/wrong
    value (e.g. showing GREEN when the session is about to be locked RED).
    Instead we derive the consequence purely from is_hard.
    """
    parts = []

    if is_hard:
        parts.append(
            f'The hard rule "{rule.rule_name}" has been violated '
            f'and your session has been locked.'
        )
    else:
        parts.append(
            f'The soft rule "{rule.rule_name}" has been triggered. '
            f'Review your trading activity to avoid further violations.'
        )

    if rule.description:
        parts.append(f'Rule: {rule.description}')

    if trade is not None:
        trade_label = getattr(trade, 'symbol', None) or str(trade.id)
        parts.append(f'Associated trade: {trade_label}')

    return ' '.join(parts)


# ─── Discipline test email ────────────────────────────────────────────────────

def send_discipline_report_email(email, risk_level):
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.conf import settings

    report_data = {
        "low": {
            "title": "Your discipline patterns are currently stable.",
            "points": ["Respect limits", "Pause after losses", "Avoid emotional escalation"],
            "advice": "This already puts you ahead of most retail traders.",
        },
        "moderate": {
            "title": "Your discipline holds — until pressure increases.",
            "points": ["Rules exist, but aren't always enforced", "Trade behavior changes after wins or losses", "Limits are sometimes flexible"],
            "advice": "This is where overtrading usually begins.",
        },
        "high": {
            "title": "Your trading behavior is likely harming your results.",
            "points": ["Rules are often overridden", "Trading continues after emotional triggers", "Loss recovery attempts increase activity"],
            "advice": "This is a behavior pattern — not a strategy problem.",
        },
    }

    data = report_data.get(risk_level, report_data["moderate"])

    html_message = render_to_string("notifications/discipline_report_email.html", {
        "risk_level": risk_level,
        **data,
    })

    send_mail(
        subject="Your Discipline Profile Report",
        message=data["title"],  # plain text fallback
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        html_message=html_message,
        fail_silently=False,
    )