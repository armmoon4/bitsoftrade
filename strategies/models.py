import uuid
from django.db import models
from django.conf import settings


class Strategy(models.Model):
    """Trading strategies — user-created, admin templates, or community-shared."""

    TRADE_TYPE_CHOICES = [
        ('intraday', 'Intraday'),
        ('swing', 'Swing'),
        ('positional', 'Positional'),
    ]
    MATURITY_STATUS_CHOICES = [
        ('testing', 'Testing'),
        ('developing', 'Developing'),
        ('mature', 'Mature'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
        related_name='strategies'
    )
    created_by_admin = models.ForeignKey(
        'admin_panel.Admin', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_strategies'
    )
    source_strategy = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='copies', help_text='If copied from community, points to original'
    )

    strategy_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)
    market_types = models.JSONField(default=list, blank=True, help_text='Indian Stocks / Forex / Crypto / Options')
    trade_type = models.CharField(max_length=15, choices=TRADE_TYPE_CHOICES, null=True, blank=True)
    is_public = models.BooleanField(default=False)
    is_template = models.BooleanField(default=False)
    maturity_status = models.CharField(max_length=15, choices=MATURITY_STATUS_CHOICES, default='testing')
    sample_size_threshold = models.IntegerField(default=30)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'strategies'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.strategy_name} [{self.maturity_status}]"

    def update_maturity(self, total_trades):
        """Recalculate and save maturity status based on sample progress."""
        progress = (total_trades / self.sample_size_threshold) * 100
        if progress < 50:
            self.maturity_status = 'testing'
        elif progress < 90:
            self.maturity_status = 'developing'
        else:
            self.maturity_status = 'mature'
        self.save(update_fields=['maturity_status'])
