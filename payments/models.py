import uuid
from django.db import models
from django.conf import settings


class PaymentTransaction(models.Model):
    """Razorpay payment record. Populated when webhook confirms success."""

    PLAN_TYPE_CHOICES = [
        ('tool', 'Tool Plan'),
        ('learning', 'Learning Plan'),
        ('both', 'Tool + Learning'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    razorpay_order_id = models.CharField(max_length=200)
    razorpay_payment_id = models.CharField(max_length=200, blank=True, null=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, help_text='In INR')
    currency = models.CharField(max_length=10, default='INR')
    plan_type = models.CharField(max_length=10, choices=PLAN_TYPE_CHOICES)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payment_transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} – {self.plan_type} – {self.status} – ₹{self.amount}"
