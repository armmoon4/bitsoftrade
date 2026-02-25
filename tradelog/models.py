import uuid
from django.db import models
from django.conf import settings


class Trade(models.Model):
    """Trade model — the core data unit for all reports, insights and discipline."""

    MARKET_CHOICES = [
        ('indian_stocks', 'Indian Stocks'),
        ('forex', 'Forex'),
        ('crypto', 'Crypto'),
        ('options', 'Options'),
    ]
    DIRECTION_CHOICES = [
        ('long', 'Long'),
        ('short', 'Short'),
    ]
    EMOTIONAL_STATE_CHOICES = [
        ('calm', 'Calm'),
        ('anxious', 'Anxious'),
        ('confident', 'Confident'),
        ('fearful', 'Fearful'),
        ('fomo', 'FOMO'),
        ('angry', 'Angry'),
        ('overconfident', 'Overconfident'),
        ('uncertain', 'Uncertain'),
    ]
    IMPORT_SOURCE_CHOICES = [
        ('manual', 'Manual'),
        ('csv_import', 'CSV Import'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trades')
    session = models.ForeignKey(
        'discipline.DisciplineSession', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='trades'
    )
    strategy = models.ForeignKey(
        'strategies.Strategy', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='trades'
    )

    # ── General ──────────────────────────────────────────────────────────────
    trade_date = models.DateField()
    trade_time = models.TimeField(null=True, blank=True)
    symbol = models.CharField(max_length=100)
    market_type = models.CharField(max_length=20, choices=MARKET_CHOICES)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    entry_price = models.DecimalField(max_digits=15, decimal_places=4)
    exit_price = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    fees = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    stop_loss = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    target = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    leverage = models.DecimalField(max_digits=10, decimal_places=2, default=1, null=True, blank=True)
    total_pnl = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # ── Psychology ────────────────────────────────────────────────────────────
    entry_confidence = models.IntegerField(null=True, blank=True, help_text='1-10')
    satisfaction_rating = models.IntegerField(null=True, blank=True, help_text='1-10')
    emotional_state = models.CharField(max_length=20, choices=EMOTIONAL_STATE_CHOICES, null=True, blank=True)
    violation_modes = models.JSONField(default=list, blank=True)
    lessons_learned = models.TextField(blank=True)

    # ── Discipline ────────────────────────────────────────────────────────────
    rules_followed = models.JSONField(default=list, blank=True)
    is_disciplined = models.BooleanField(default=True)
    is_tagged_complete = models.BooleanField(default=False, help_text='True when strategy+psychology fully tagged')

    # ── Media ─────────────────────────────────────────────────────────────────
    screenshot_urls = models.JSONField(default=list, blank=True)

    # ── Import metadata ───────────────────────────────────────────────────────
    import_source = models.CharField(max_length=15, choices=IMPORT_SOURCE_CHOICES, default='manual')
    broker_name = models.CharField(max_length=100, blank=True, null=True)

    # ── Soft delete ───────────────────────────────────────────────────────────
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'trades'
        ordering = ['-trade_date', '-trade_time']
        indexes = [
            models.Index(fields=['user', 'trade_date']),
            models.Index(fields=['user', 'session']),
        ]

    def __str__(self):
        return f"{self.symbol} {self.direction.upper()} {self.trade_date}"

    def calculate_pnl(self):
        """Calculate and set total_pnl using the unified formula."""
        if not self.exit_price:
            self.total_pnl = None
            return
        qty = self.quantity or 0
        entry = self.entry_price or 0
        exit_p = self.exit_price or 0
        fees = self.fees or 0
        leverage = self.leverage or 1

        if self.direction == 'long':
            raw_pnl = (exit_p - entry) * qty * leverage
        else:
            raw_pnl = (entry - exit_p) * qty * leverage
        self.total_pnl = raw_pnl - fees

    @property
    def is_winner(self):
        return self.total_pnl is not None and self.total_pnl > 0