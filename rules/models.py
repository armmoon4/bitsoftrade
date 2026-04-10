import uuid
from django.db import models
from django.conf import settings


class Rule(models.Model):
    """Trading rules — either admin-global, user-custom, or user-level system rules."""

    CATEGORY_CHOICES = [
        ('risk', 'Risk'),
        ('process', 'Process'),
        ('psychology', 'Psychology'),
        ('time', 'Time'),
        ('other', 'Other'),
    ]
    RULE_TYPE_CHOICES = [
        ('hard', 'Hard'),
        ('soft', 'Soft'),
    ]
    TRIGGER_SCOPE_CHOICES = [
        ('per_day', 'Per Day'),
        ('per_trade', 'Per Trade'),
        ('post_trigger', 'Post Trigger'),
    ]
    ACTION_CHOICES = [
        ('lock', 'Lock'),
        ('warn', 'Warn'),
        ('require_journal', 'Require Journal'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by_admin = models.ForeignKey(
        'admin_panel.Admin', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_rules'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
        related_name='custom_rules'
    )
    rule_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    rule_type = models.CharField(max_length=10, choices=RULE_TYPE_CHOICES)
    trigger_scope = models.CharField(max_length=20, choices=TRIGGER_SCOPE_CHOICES)
    trigger_condition = models.JSONField(
        default=dict,
        help_text='e.g. {"maxLoss": 5000, "maxDailyPercent": 3}'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    is_active = models.BooleanField(default=True)
    is_admin_defined = models.BooleanField(default=False, help_text='Admin rules cannot be deleted by users')
    is_system_rule = models.BooleanField(
        default=False,
        help_text=(
            'System rules are seeded per-user on registration. '
            'Users can update thresholds and toggle is_active, '
            'but cannot delete them.'
        )
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rules'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.rule_name} [{self.rule_type.upper()}]"
    
class TradeRule(models.Model):
    """Junction: links a rule (user-custom or admin-defined) to a trade."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.ForeignKey('tradelog.Trade', on_delete=models.CASCADE, related_name='trade_rules')
    rule = models.ForeignKey(Rule, on_delete=models.CASCADE, related_name='tagged_trades')
    tagged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'trade_rules'
        unique_together = ('trade', 'rule')

    def __str__(self):
        return f"{self.rule.rule_name} → Trade {self.trade_id}"