from django.db import models
from django.conf import settings
# Create your models here.
class Trade(models.Model):
    """Trade model for tracking trading activity"""
    
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
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trades')
    
    # Basic Trade Info
    market_type = models.CharField(max_length=20, choices=MARKET_CHOICES)
    symbol = models.CharField(max_length=50)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    
    # Pricing
    entry_price = models.DecimalField(max_digits=15, decimal_places=2)
    exit_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    stop_loss = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    target = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    # Fees and P&L
    fees = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_pnl = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    # Timing
    entry_date = models.DateTimeField()
    exit_date = models.DateTimeField(null=True, blank=True)
    
    # Strategy and Tags
    strategy = models.CharField(max_length=100)
    leverage = models.DecimalField(max_digits=5, decimal_places=2, default=1, null=True, blank=True)
    
    # Psychology
    entry_confidence = models.IntegerField(default=5, help_text="1-10 scale")
    satisfaction_rating = models.IntegerField(null=True, blank=True, help_text="1-10 scale")
    emotional_state = models.CharField(max_length=50, null=True, blank=True)  # calm, anxious, confident, fearful
    
    # Violation tracking
    violation_modes = models.JSONField(default=list, blank=True)  # List of violations
    
    # Rules and discipline
    rules_followed = models.JSONField(default=list, blank=True)  # List of rule IDs
    is_disciplined = models.BooleanField(default=True)
    
    # Additional notes
    lessons_learned = models.TextField(blank=True)
    screenshots = models.JSONField(default=list, blank=True)  # List of screenshot URLs
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'trades'
        ordering = ['-entry_date']
    
    def __str__(self):
        return f"{self.symbol} - {self.direction} - {self.entry_date.date()}"
    
    @property
    def is_closed(self):
        return self.exit_price is not None
    