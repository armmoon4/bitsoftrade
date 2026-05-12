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

from datetime import datetime
DISCIPLINE_GUARD_URL = "https://bitsoftrade.com/user-dashboard"
 
REPORT_DATA = {
    "low": {
        "subject": "Your discipline is strong — here's what usually breaks it",
        "title": "Your discipline patterns are currently stable.",
        "intro": (
            "Your Discipline Test results show something rare: "
            "you currently operate with strong control and awareness. "
            "Most traders never reach this stage."
        ),
        "points": [
            "Respect limits",
            "Pause after losses",
            "Avoid emotional escalation",
        ],
        "bridge": (
            "But here's the uncomfortable truth: discipline doesn't collapse during losses. "
            "It erodes quietly during success.\n\n"
            "After green days, rules feel optional, trade frequency increases, and size creeps up. "
            "This isn't a mindset issue — it's a structural one.\n\n"
            "Institutions don't trust discipline to memory. They build systems around it. "
            "BitsOfTrade exists to do the same for retail traders."
        ),
        "advice": "This already puts you ahead of most retail traders.",
        "discipline_guard_features": [],
        "cta_label": "Explore Discipline Guard",
        "cta_url": DISCIPLINE_GUARD_URL,
    },
    "moderate": {
        "subject": "This is where overtrading usually begins",
        "title": "Your discipline holds — until pressure increases.",
        "intro": (
            "Your Discipline Test results show a common pattern: "
            "you know the rules — but under pressure, they weaken."
        ),
        "points": [
            "Rules exist, but aren't always enforced",
            "Trade behavior changes after wins or losses",
            "Limits are sometimes flexible",
        ],
        "bridge": (
            "Overtrading doesn't start as chaos. It starts as small exceptions — "
            "usually after a losing streak, after a strong win, or during long trading sessions.\n\n"
            "Retail traders are told to 'be more disciplined.' "
            "Institutions do something else: they build systems that intervene "
            "before damage compounds.\n\n"
            "BitsOfTrade is designed for this exact gap. "
            "You don't need better strategies. You need better guardrails."
        ),
        "advice": "This is where overtrading usually begins.",
        "discipline_guard_features": [],
        "cta_label": "See Discipline Guard",
        "cta_url": DISCIPLINE_GUARD_URL,
    },
    "high": {
        "subject": "This isn't a strategy problem — it's a structure problem",
        "title": "Your trading behavior is likely harming your results.",
        "intro": (
            "Your Discipline Test results indicate elevated risk. "
            "Not because you lack knowledge — "
            "but because your trading behavior is being driven by emotional cycles. "
            "This is not a judgment. It's a pattern we see repeatedly."
        ),
        "points": [
            "Rules are often overridden",
            "Trading continues after emotional triggers",
            "Loss recovery attempts increase activity",
        ],
        "bridge": (
            "Overtrading isn't caused by bad strategies. "
            "It's caused by the absence of enforced limits.\n\n"
            "Retail traders are told to control emotions. "
            "Professionals remove decision-making when emotions peak. "
            "That's what BitsOfTrade helps you do."
        ),
        "advice": (
            "Structure creates safety. Discipline Guard introduces the guardrails "
            "that protect your account when it matters most."
        ),
        "discipline_guard_features": [
            "Session limits",
            "Loss-streak awareness",
            "Trade frequency alerts",
            "Reflection before continuation",
        ],
        "cta_label": "Start Discipline Guard",
        "cta_url": DISCIPLINE_GUARD_URL,
    },
}
 
 
def send_discipline_report_email(email: str, first_name: str, risk_level: str) -> None:
    """
    Send the personalised Discipline Profile Report email.
 
    Args:
        email:      Recipient email address.
        first_name: Recipient's first name for greeting.
        risk_level: One of "low" | "moderate" | "high".
    """
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.conf import settings
 
    data = REPORT_DATA.get(risk_level, REPORT_DATA["moderate"])
 
    context = {
        "first_name": first_name or "there",
        "risk_level": risk_level,
        "current_year": datetime.now().year,
        **data,
    }
 
    html_message = render_to_string(
        "notifications/discipline_report_email.html",
        context,
    )
 
    send_mail(
        subject=data["subject"],
        message=data["title"],          # plain-text fallback
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        html_message=html_message,
        fail_silently=False,
    )


# ─── Onboarding welcome email ─────────────────────────────────────────────────

DASHBOARD_LINK = "https://bitsoftrade.com/user-dashboard"


def send_welcome_email(user) -> None:
    """
    Send the onboarding welcome email immediately after a successful payment.

    Args:
        user: The Django User instance whose subscription was just activated.
    """
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.conf import settings

    first_name = (getattr(user, 'first_name', '') or user.email.split('@')[0]).strip()
    plan_type  = getattr(user, 'subscription_type', '')

    context = {
        "first_name":     first_name,
        "dashboard_link": DASHBOARD_LINK,
        "has_learning":   plan_type in ('learning', 'both'),
        "current_year":   datetime.now().year,
    }

    html_message = render_to_string(
        "notifications/welcome_email.html",
        context,
    )

    plain_text = (
        f"Hi {first_name},\n\n"
        "Welcome to BitsOfTrade. Your access has been successfully activated.\n\n"
        "BitsOfTrade is designed to help traders reduce overtrading, build structured "
        "discipline, review behaviour honestly, and learn trading without chasing outcomes.\n\n"
        f"Go to your dashboard: {DASHBOARD_LINK}\n\n"
        "No predictions. Only structure.\n\n"
        "— Team BitsOfTrade"
    )

    try:
        send_mail(
            subject="Welcome to BitsOfTrade — your access is active",
            message=plain_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info("[Welcome Email] Sent to user=%s", user.email)
    except Exception as exc:
        # Never let an email failure crash the payment flow
        logger.error("[Welcome Email] Failed to send to user=%s: %s", user.email, exc)
