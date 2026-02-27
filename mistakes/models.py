import uuid
from django.db import models
from django.conf import settings


class Mistake(models.Model):
    """Trading mistakes — admin-global or user-custom."""

    CATEGORY_CHOICES = [
        ('execution', 'Execution'),
        ('psychology', 'Psychology'),
        ('process', 'Process'),
        ('risk', 'Risk'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by_admin = models.ForeignKey(
        'admin_panel.Admin', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_mistakes'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
        related_name='custom_mistakes'
    )
    mistake_name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True)
    severity_weight = models.IntegerField(help_text='1-10 severity score')
    is_custom = models.BooleanField(default=False)
    is_admin_defined = models.BooleanField(default=False, help_text='Admin mistakes cannot be deleted by users')
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mistakes'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.mistake_name} (severity: {self.severity_weight})"


class TradeMistake(models.Model):
    """Junction: links a mistake to a trade."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.ForeignKey('tradelog.Trade', on_delete=models.CASCADE, related_name='trade_mistakes')
    mistake = models.ForeignKey(Mistake, on_delete=models.CASCADE, related_name='tagged_trades')
    tagged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'trade_mistakes'
        unique_together = ('trade', 'mistake')

    def __str__(self):
        return f"{self.mistake.mistake_name} → Trade {self.trade_id}"
