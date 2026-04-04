from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Rule

SYSTEM_RULES_DEFAULTS = [
    {
        'rule_name': 'Max Daily Loss',
        'description': (
            'Locks the session when the sum of total_pnl across all trades '
            'today reaches a loss equal to or exceeding the set limit (INR).'
        ),
        'category': 'risk',
        'rule_type': 'hard',
        'trigger_scope': 'per_day',
        'trigger_condition': {'maxLoss': 5000},
        'action': 'lock',
    },
    {
        'rule_name': 'Position Size Limit',
        'description': (
            "Fires if any single trade's position value (entry_price × quantity) "
            'exceeds the set absolute amount (INR).'
        ),
        'category': 'risk',
        'rule_type': 'hard',
        'trigger_scope': 'per_trade',
        'trigger_condition': {'maxPositionSize': 50000},
        'action': 'warn',
    },
    {
        'rule_name': 'Max Trades Per Day',
        'description': (
            'Fires when the number of trades in the current lock cycle exceeds '
            'the limit. Each unlock cycle gets a fresh quota.'
        ),
        'category': 'process',
        'rule_type': 'soft',
        'trigger_scope': 'per_day',
        'trigger_condition': {'maxTrades': 5},
        'action': 'warn',
    },
    {
        'rule_name': 'Consecutive Loss Limit',
        'description': (
            'Fires if the last N closed trades (across all dates) are all losses.'
        ),
        'category': 'psychology',
        'rule_type': 'soft',
        'trigger_scope': 'per_day',
        'trigger_condition': {'consecutiveLosses': 3},
        'action': 'require_journal',
    },
]


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def seed_system_rules(sender, instance, created, **kwargs):
    """Auto-create the four system rules whenever a new user is registered."""
    if not created:
        return

    Rule.objects.bulk_create([
        Rule(
            user=instance,
            is_system_rule=True,
            is_admin_defined=False,
            is_active=True,
            **defaults,
        )
        for defaults in SYSTEM_RULES_DEFAULTS
    ])