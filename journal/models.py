from django.db import models
from django.conf import settings
from tradelog.models import Trade
# Create your models here.

class DailyJournal(models.Model):
    """Daily trading journal entries"""
    
    SESSION_STATUS_CHOICES = [
        ('green', 'Green - Normal'),
        ('yellow', 'Yellow - Caution'),
        ('red', 'Red - Restricted'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_journals')
    date = models.DateField(unique=True)

    # unclear seassion status
    # session_status = models.CharField(max_length=10, choices=SESSION_STATUS_CHOICES, default='green')
    daily_prompt = models.TextField(blank=True)
    reflection = models.TextField()
    intention_next_session = models.TextField(blank=True)
    limits_followed = models.CharField(max_length=10, choices=[('yes', 'Yes'), ('mostly', 'Mostly'), ('no', 'No')])
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'daily_journals'
        ordering = ['-date']
    
    def __str__(self):
        return f"Journal - {self.date}"


class TradeNote(models.Model):
    """Per-trade narrative and analysis"""
    
    TRADE_TYPE_CHOICES = [
        ('win', 'Win'),
        ('loss', 'Loss'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='trade_notes'
    )
    trade = models.ForeignKey(
        Trade, 
        on_delete=models.CASCADE, 
        related_name='notes',
        null=True,
        blank=True
    )
    
    # Trade details (can be independent of Trade model)
    trade_type = models.CharField(
        max_length=10, 
        choices=TRADE_TYPE_CHOICES,
        null=True,
        blank=True
    )
    symbol = models.CharField(max_length=20, null=True, blank=True)
    trade_date = models.DateField(null=True, blank=True)
    trade_time = models.TimeField(null=True, blank=True)
    pnl_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Profit/Loss amount"
    )
    
    # Note content
    note = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'trade_notes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['trade_type']),
            models.Index(fields=['symbol']),
        ]
    
    def __str__(self):
        if self.trade:
            return f"Note for {self.trade.symbol}"
        return f"Note for {self.symbol or 'Unknown'}"
    
    def clean(self):
        """Ensure either trade is linked or manual fields are provided"""
        from django.core.exceptions import ValidationError
        
        if not self.trade and not self.symbol:
            raise ValidationError("Either link a trade or provide symbol manually")
    
    @property
    def display_symbol(self):
        """Get symbol from trade or manual entry"""
        return self.symbol if self.symbol else (self.trade.symbol if self.trade else None)
    
    @property
    def display_pnl(self):
        """Get P&L from trade or manual entry"""
        return self.pnl_amount if self.pnl_amount is not None else (self.trade.pnl if self.trade else None)


class PsychologyLog(models.Model):
    """Psychology log for emotional tracking"""
    
    EMOTIONAL_STATE_CHOICES = [
        ('calm', 'Calm'),
        ('anxious', 'Anxious'),
        ('fomo', 'FOMO'),
        ('angry', 'Angry'),
        ('overconfident', 'Overconfident'),
        ('uncertain', 'Uncertain'),
    ]
    
    PRESSURE_SOURCE_CHOICES = [
        ('money', 'Money'),
        ('time', 'Time'),
        ('missed_move', 'Missed Move'),
        ('angry', 'Angry'),
        ('overconfident', 'Overconfident'),
        ('uncertain', 'Uncertain'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='psychology_logs')
    
    emotional_state = models.CharField(max_length=20, choices=EMOTIONAL_STATE_CHOICES)
    confidence_before_trade = models.IntegerField(help_text="1-10 scale")
    satisfaction_after_trade = models.IntegerField(help_text="1-10 scale")
    pressure_source = models.CharField(max_length=20, choices=PRESSURE_SOURCE_CHOICES)
    
    linked_trades = models.ManyToManyField(Trade, related_name='psychology_logs', blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'psychology_logs'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.emotional_state} - {self.created_at.date()}"


    #mistakes class will be linked here with trade 

class SessionRecap(models.Model):
    """End-of-day session intelligence"""
    
    SESSION_OUTCOME_CHOICES = [
        ('good', 'Good'),
        ('neutral', 'Neutral'),
        ('bad', 'Bad'),
    ]
    
    SESSION_STATUS_CHOICES = [
        ('green', 'Green'),
        ('yellow', 'Yellow'),
        ('red', 'Red'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='session_recaps')
    date = models.DateField()
    
    #maybe come from the status
    session_status = models.CharField(max_length=10, choices=SESSION_STATUS_CHOICES)
    session_outcome = models.CharField(max_length=10, choices=SESSION_OUTCOME_CHOICES)
    
    what_went_right = models.JSONField(default=list, blank=True)
    what_slipped = models.JSONField(default=list, blank=True)
    
    one_rule_to_focus = models.TextField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'session_recaps'
        ordering = ['-date']
    
    def __str__(self):
        return f"Session {self.date} - {self.session_outcome}"


class LearningNote(models.Model):
    """Learning notes to close the learning loop"""
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_notes')
    
    lesson_watched_read = models.CharField(max_length=255)
    key_takeaway = models.TextField()
    how_to_apply = models.TextField()
    
    # Links
    linked_mistake = models.ForeignKey('Mistake', on_delete=models.SET_NULL, null=True, blank=True)
    linked_rule = models.ForeignKey('Rule', on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'learning_notes'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Learning: {self.lesson_watched_read[:50]}"


